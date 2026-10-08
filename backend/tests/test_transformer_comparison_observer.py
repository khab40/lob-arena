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
from app.ml.transformer.research_execution_spec import (  # noqa: E402
    comparison_replacement_template, comparison_template, provider_spec,
)
from app.ml.transformer.verification_spec import canonical  # noqa: E402


def setup(tmp_path, replacement=False):
    builder = comparison_replacement_template if replacement else comparison_template
    request = builder("a" * 40, "sha256:" + "b" * 64, CONTEXT_PUBLIC_KEY, "c" * 32)
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


@pytest.mark.parametrize("replacement", [False, True])
def test_observes_before_creation_and_closes_admission_permanently(tmp_path, replacement):
    request, path, output, job = setup(tmp_path, replacement)
    snapshots = [None, job("PROVISIONING"), job("STARTING"), job("IMAGE_PULLING"), job(), job("COMPLETED")]
    assert run(request, path, output, snapshots) == 0
    records = [json.loads(line) for line in (output / "observations.jsonl").read_text().splitlines()]
    assert [r["state"] for r in records] == ["absent", "PROVISIONING", "STARTING", "IMAGE_PULLING", "RUNNING", "COMPLETED"]
    assert [r["admission_closed"] for r in records] == [False, True, True, True, True, True]
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


def test_real_image_pulling_snapshot_matches_approved_request():
    root = Path(__file__).resolve().parents[2]
    request = json.loads((root / "docs/evidence/transformer-comparison-request-20261004.json").read_bytes())
    job = json.loads((Path(__file__).parent / "fixtures/transformer_comparison_image_pulling.json").read_bytes())
    context = observer.observed(job, request, allowed_states=observer.STATES)
    assert context["job_id"] == "aijob-e00ma26ee5bavrb8nb"
    assert observer.STATES - observer.TERMINAL == observer.LIVE_STATES


@pytest.mark.parametrize("states", [
    ["STARTING", "IMAGE_PULLING", "STARTING"],
    ["IMAGE_PULLING", "STARTING", "IMAGE_PULLING"],
    ["IMAGE_PULLING", "IMAGE_PULLING", "IMAGE_PULLING"],
])
def test_startup_timer_spans_image_pull_transitions(tmp_path, states):
    request, path, output, job = setup(tmp_path)
    with pytest.raises(TimeoutError):
        run(request, path, output, [job(s) for s in states], step=301)
    status = observer.inspect(output, observer.sha(path))
    assert status["state"] == "failed" and status["admission_closed"]
    assert status["received_provider_state"] == states[-1]


def test_unrecognized_provider_state_is_rejected_without_logging_arbitrary_value(tmp_path):
    request, path, output, job = setup(tmp_path)
    with pytest.raises(ValueError):
        run(request, path, output, [job("unexpected provider response")])
    status = observer.inspect(output, observer.sha(path))
    assert status["state"] == "failed" and status["admission_closed"]
    assert status["received_provider_state"] == "UNRECOGNIZED"
