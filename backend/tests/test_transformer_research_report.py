"""Report inert saved JSON only; no model, provider or object-store execution."""
import hashlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
spec = importlib.util.spec_from_file_location("research_report_test", SCRIPTS / "transformer_research_report.py")
report = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(SCRIPTS))
try:
    spec.loader.exec_module(report)
finally:
    sys.path.pop(0)
SLOT = "search-64-0003"


def dump(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "version_id": "1"}


def evidence(base, change=None):
    directory = base / SLOT
    artifacts = directory / "artifacts"
    artifacts.mkdir(parents=True)
    request = {"slot": SLOT, "run_id": "inert-report-fixture", "source_commit": "a" * 40,
               "image_digest": "sha256:" + "b" * 64, "output_bucket": "fixture-bucket", "output_prefix": "runs/fixture/"}
    request_hash = dump(directory / "request.json", request)["sha256"]
    rows = [{"target_id": str(i), "label": label, "logit": logit}
            for i, (label, logit) in enumerate([(0, -2.), (0, 0.), (1, -1.), (1, 2.)])]
    loss = sum(max(r["logit"], 0) + math.log1p(math.exp(-abs(r["logit"])))
               - r["label"] * r["logit"] for r in rows) / 4
    result = {"status": "verified", "kind": "trial", "job_id": "aijob-fixture", "request_sha256": request_hash,
        "bindings": {key: request[key] for key in ("source_commit", "image_digest")},
        "trial": {"width": 64, "learning_rate": .0003, "seed": 42, "batch_size": 64, "max_epochs": 30, "patience": 5},
        "selected_epoch": 1, "selection_f1_at_half": .5, "selection_log_loss": loss, "parameter_count": 107905,
        "selected_checkpoint": {"object_name": "epoch-01.pt", "version_id": "1", "sha256": "c" * 64},
        "progress": {"epoch": 2, "history": [
            {"epoch": 1, "weighted_train_loss": .7, "selection_log_loss": loss, "selection_f1_at_half": .5},
            {"epoch": 2, "weighted_train_loss": .4, "selection_log_loss": loss + .2, "selection_f1_at_half": .25}]},
        "duration_seconds": 2., "measurements": {"elapsed_seconds": 10., "cpu_seconds": 9., "peak_rss_kib": 1024},
        "peak_allocated_gpu_bytes": 1024, "peak_reserved_gpu_bytes": 2048}
    if change:
        change(result, rows)
    inventory = {name: dump(artifacts / name, value) for name, value in (
        ("configuration.json", request), ("result.json", {**result, "status": "completed_pending_independent_verification"}),
        ("selection-predictions.json", rows), ("normalization.json", {"fitting_rows": 100}))}
    dump(directory / "verification.json", {"status": "verified", "result": result,
         "context": {"job_id": result["job_id"]}, "inventory": inventory})
    dump(directory / "provider-terminal.json", {"metadata": {"id": result["job_id"]}, "status": {
        "state": "COMPLETED", "started_at": "2026-10-03T10:00:00Z", "finished_at": "2026-10-03T10:00:10Z"}})
    return directory


def test_selected_metrics_recomputed_including_zero_threshold(tmp_path):
    data = report.load(evidence(tmp_path))
    assert data["counts"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert data["metrics"] == pytest.approx({"precision": .5, "recall": .5, "f1": .5,
        "log_loss": (2 * math.log1p(math.exp(-2)) + math.log(2) + math.log1p(math.exp(1))) / 4})


@pytest.mark.parametrize("failure", ["missing", "failed", "tampered"])
def test_rejects_unverified_or_altered_artifacts_before_output(tmp_path, failure):
    directory = evidence(tmp_path)
    receipt = directory / "verification.json"
    if failure == "missing":
        receipt.unlink()
    elif failure == "failed":
        value = json.loads(receipt.read_bytes())
        value["status"] = "failed"
        dump(receipt, value)
    else:
        (directory / "artifacts/result.json").write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        report.generate(directory, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("failure", ["epoch", "duplicate", "nan_prediction", "nan_metric"])
def test_rejects_invalid_epoch_rows_and_nonfinite_values(tmp_path, failure):
    def change(result, rows):
        if failure == "epoch":
            result["selected_epoch"] = 3
        elif failure == "duplicate":
            rows.append(rows[0].copy())
        elif failure == "nan_prediction":
            rows[0]["logit"] = float("nan")
        else:
            result["progress"]["history"][0]["weighted_train_loss"] = float("nan")
    with pytest.raises(ValueError):
        report.generate(evidence(tmp_path, change), tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_real_png_markdown_manifest_idempotence_and_damage_detection(tmp_path):
    directory, output = evidence(tmp_path), tmp_path / "output"
    markdown = report.generate(directory, output)
    text = markdown.read_text()
    assert "| Precision / recall / F1 at 0.5 | 0.500000 / 0.500000 / 0.500000 |" in text
    assert "| Selected / stopped epoch | 1 / 2 |" in text
    assert "| Negative | 1 | 1 |" in text and "| Positive | 1 | 1 |" in text
    manifest = json.loads((output / "report-manifest.json").read_bytes())
    before = {path.name: path.stat().st_mtime_ns for path in output.iterdir()}
    for name, checksum in manifest["files"].items():
        raw = (output / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == checksum
        if name.endswith(".png"):
            assert raw.startswith(b"\x89PNG\r\n\x1a\n")
            assert all(size >= 700 for size in struct.unpack(">II", raw[16:24]))
    assert report.generate(directory, output) == markdown
    assert before == {path.name: path.stat().st_mtime_ns for path in output.iterdir()}
    markdown.write_text("damaged")
    with pytest.raises(ValueError, match="damaged"):
        report.generate(directory, output)


def test_render_failure_publishes_no_success_directory(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("inert renderer failure")
    monkeypatch.setattr(report, "render", fail)
    with pytest.raises(RuntimeError, match="renderer failure"):
        report.generate(evidence(tmp_path), tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".report-*"))


def collect_args(base):
    return ["--evidence", str(base), "--slot", SLOT, "--output", str(base / "reports" / SLOT),
            "--collect", "--operator-python", "python-fixture",
            "--bundle", "bundle-fixture", "--source-receipt", "source-fixture"]


def test_wrapper_collects_once_then_reuses_verified_receipt(tmp_path, monkeypatch):
    (tmp_path / SLOT).mkdir()
    calls = []
    def collect(command, **kwargs):
        calls.append(command)
        assert kwargs == {"check": True} and command[2] == "collect"
        evidence(tmp_path)
    monkeypatch.setattr(report.subprocess, "run", collect)
    monkeypatch.setattr(report, "generate", lambda directory, output: output / "report.md")
    assert report.main(collect_args(tmp_path))["report_status"] == "ready"
    assert report.main(collect_args(tmp_path))["report_status"] == "ready"
    assert len(calls) == 1


@pytest.mark.parametrize("partial", ["artifacts", "provider-terminal.json"])
def test_partial_collection_is_not_retried(tmp_path, monkeypatch, partial):
    directory = tmp_path / SLOT
    directory.mkdir()
    (directory / partial).mkdir() if partial == "artifacts" else (directory / partial).write_text("{}")
    monkeypatch.setattr(report.subprocess, "run", lambda *a, **k: pytest.fail("collector repeated"))
    with pytest.raises(ValueError, match="partial collection"):
        report.main(collect_args(tmp_path))


def test_failed_collector_is_not_repeated_before_any_artifact(tmp_path, monkeypatch):
    (tmp_path / SLOT).mkdir()
    calls = []
    def fail(command, **kwargs):
        calls.append(command)
        raise report.subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(report.subprocess, "run", fail)
    with pytest.raises(report.subprocess.CalledProcessError):
        report.main(collect_args(tmp_path))
    with pytest.raises(ValueError, match="collection"):
        report.main(collect_args(tmp_path))
    assert len(calls) == 1
    assert not (tmp_path / SLOT / "artifacts").exists()
