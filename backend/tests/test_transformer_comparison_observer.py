"""Inert provider snapshots and clock fixtures; never spawn a workload."""
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import transformer_comparison_observer as observer  # noqa: E402
from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY  # noqa: E402
from app.ml.transformer.research_execution_spec import comparison_template, provider_spec  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402


def setup(tmp_path):
    request = comparison_template("a" * 40, "sha256:" + "b" * 64, CONTEXT_PUBLIC_KEY, "c" * 32)
    path = tmp_path / "request.json"
    path.write_bytes(canonical(request))
    output = tmp_path / "observer"
    def job(state="RUNNING"):
        return {"metadata": {"name": request["run_id"], "parent_id": observer.PROJECT,
            "id": "aijob-test", "created_at": "1970-01-01T00:00:00Z"},
            "spec": provider_spec(request), "status": {"state": state}}
    return request, path, output, job


def run(request, path, output, snapshots, *, step=10):
    clock = [0]
    snapshots = iter(snapshots)
    def read(*args):
        assert args[:3] == ("ai", "job", "get-by-name")
        return next(snapshots)
    def pause(seconds):
        assert seconds == 10
        clock[0] += step
    return observer.observe(request, path, output, read=read, now=lambda: clock[0],
                            pause=pause, identity=lambda _: "fixture-process")


def test_observes_before_creation_and_closes_admission_permanently(tmp_path):
    request, path, output, job = setup(tmp_path)
    assert run(request, path, output, [None, job("STARTING"), job(), job("COMPLETED")]) == 0
    records = [json.loads(line) for line in (output / "observations.jsonl").read_text().splitlines()]
    assert [r["state"] for r in records] == ["absent", "STARTING", "RUNNING", "COMPLETED"]
    assert [r["admission_closed"] for r in records] == [False, True, True, True]
    assert not observer.inspect(output, observer.sha(path))["admission_ready"]
    with pytest.raises(FileExistsError):
        run(request, path, output, [])


@pytest.mark.parametrize("failure", ["disappeared", "identity", "resources", "startup", "accounting", "absent"])
def test_provider_drift_or_expiry_stops_observer(tmp_path, failure):
    request, path, output, job = setup(tmp_path)
    first, second, step = job(), job(), 10
    if failure == "disappeared":
        second = None
    elif failure == "identity":
        second["metadata"]["id"] = "aijob-other"
    elif failure == "resources":
        second["spec"]["timeout"] = "7200s"
    elif failure == "startup":
        first, second, step = job("STARTING"), job("STARTING"), 601
    elif failure == "accounting":
        step = 7201
    else:
        first, second, step = None, None, 121
    with pytest.raises((ValueError, TimeoutError)):
        run(request, path, output, [first, second], step=step)
    status = observer.inspect(output, observer.sha(path))
    assert status["state"] == "failed" and not status["admission_ready"]
    assert status["admission_closed"]


@pytest.mark.parametrize("change", ["stale", "dead", "bytes", "foreign"])
def test_admission_requires_fresh_live_bound_observer(tmp_path, change):
    request, path, output, _ = setup(tmp_path)
    output.mkdir()
    status = {"state": "absent", "request_sha256": observer.sha(path), "request_path": str(path),
              "observed_at": 10, "process_start": "live", "pid": 123, "admission_closed": False}
    observer.save(output / "status.json", status)
    assert observer.inspect(output, observer.sha(path), now=lambda: 20, identity=lambda _: "live")["admission_ready"]
    expected, now, identity = observer.sha(path), lambda: 20, lambda _: "live"
    if change == "stale":
        def now():
            return 41
    elif change == "dead":
        def identity(_):
            return ""
    elif change == "bytes":
        path.write_text("{}")
    else:
        expected = "f" * 64
    with pytest.raises(ValueError):
        observer.inspect(output, expected, now=now, identity=identity)
