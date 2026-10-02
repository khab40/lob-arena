from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")
from app.ml.transformer import role_execution_readback as readback
from app.ml.transformer.role_execution_context import context_for_job
from app.ml.transformer.role_execution_transport import claim, publish, put_new
from app.ml.transformer.verification_spec import INVENTORY_SHA, canonical, digest
from transformer_role_execution_fixtures import MemoryStore, job_for, request_and_key


@pytest.fixture
def package(monkeypatch):
    request, key = request_and_key()
    context = context_for_job(job_for(request), request)
    envelope = {"context": context, "signature": key.sign(canonical(context)).hex()}
    monkeypatch.setattr(readback, "verify_package", lambda *args: {"class_support_passed": False})
    monkeypatch.setattr(readback, "load_inventory", lambda *args: [])
    artifacts = {n: canonical({}) for n in readback.AUDIT_FILES}
    artifacts.update({"configuration.json": canonical(request), "source-separation.json": canonical({}),
        "measurements.json": canonical({"elapsed_seconds": 5.0, "cpu_seconds": 1.0,
            "peak_rss_kib": 1024, "measurement_scope": "linux_worker_before_publication",
            "gpu_count": 0, "model_runs": 0, "cost": "unknown_operator_managed"}),
        "lineage.json": canonical({"run_id": request["run_id"], "context": context,
            "transfer": {"get_attempts": 0, "response_bytes": 0}, "inventory_sha256": INVENTORY_SHA,
            "source_commit": request["source_commit"], "completed_at": datetime.now(UTC).isoformat(),
            "scope": "development_role_audit_only", "model_runs": 0, "final_test_access": False})})
    return request, envelope, artifacts


def published(package):
    request, envelope, artifacts = package
    s3 = MemoryStore()
    claim(s3, request)
    put_new(s3, request, "execution-context.json", canonical(envelope))
    success = publish(s3, request, artifacts)
    return s3, success


def test_independent_readback_retains_negative_audit(package, tmp_path):
    request, _, _ = package
    s3, success = published(package)
    result = readback.collect(s3, request, "aijob-fixture", success["sha256"], b"bundle",
                              Path("inert"), tmp_path / "readback")
    assert result["audit"]["class_support_passed"] is False
    assert result["gpu_ready"] is False
    gets = [args for kind, args in s3.calls if kind == "get"]
    assert len(gets) == 12 and all(a.get("VersionId") == "1" for a in gets[3:])
    assert (tmp_path / "readback" / "verification.json").exists()


def test_provider_log_hash_is_required_before_artifact_reads(package, tmp_path):
    request, _, _ = package
    s3, _ = published(package)
    with pytest.raises(ValueError, match="provider Job log"):
        readback.collect(s3, request, "aijob-fixture", "0" * 64, b"bundle", Path("inert"), tmp_path / "out")
    assert len([1 for kind, _ in s3.calls if kind == "get"]) == 1


@pytest.mark.parametrize("name,field,value", [
    ("lineage.json", "model_runs", 1), ("lineage.json", "final_test_access", True),
    ("lineage.json", "scope", "training"), ("lineage.json", "source_commit", "c" * 40),
    ("lineage.json", "completed_at", "2026-10-02T04:00:00"),
    ("measurements.json", "elapsed_seconds", 2940), ("measurements.json", "cpu_seconds", -1),
    ("measurements.json", "gpu_count", 1), ("measurements.json", "peak_rss_kib", True),
])
def test_readback_rejects_changed_lineage_or_bounds(package, name, field, value):
    request, envelope, artifacts = deepcopy(package)
    changed = json.loads(artifacts[name])
    changed[field] = value
    artifacts[name] = canonical(changed)
    with pytest.raises(ValueError):
        readback.verify_artifacts(artifacts, request, envelope["context"], "aijob-fixture", b"bundle", [])


def test_changed_aggregate_is_checked_by_independent_row_verifier(package, monkeypatch):
    request, envelope, artifacts = package
    def reject(audit, bundle, source):
        assert set(audit) == readback.AUDIT_FILES and source == artifacts["source-separation.json"]
        raise ValueError("independent row mismatch")
    monkeypatch.setattr(readback, "verify_package", reject)
    with pytest.raises(ValueError, match="independent row"):
        readback.verify_artifacts(artifacts, request, envelope["context"], "aijob-fixture", b"bundle", [])


@pytest.mark.parametrize("value", ["", "null", None])
def test_unversioned_checksum_manifest_rejected(package, tmp_path, value):
    request, _, _ = package
    s3, _ = published(package)
    key = request["output_prefix"] + "SUCCESS"
    terminal = json.loads(s3.objects[key])
    terminal["checksums_version_id"] = value
    s3.objects[key] = canonical(terminal)
    with pytest.raises(ValueError, match="checksum version"):
        readback.collect(s3, request, "aijob-fixture", digest(s3.objects[key]), b"bundle",
                         Path("inert"), tmp_path / "out")


@pytest.mark.parametrize("fault", ["write", "short", "flush", "fsync", "close", "link"])
def test_failed_verification_publication_keeps_only_diagnostic_artifacts(package, tmp_path, monkeypatch, fault):
    from app.ml.transformer import receipt_publication
    from test_transformer_receipt_publication import inject_stream

    request, _, artifacts = package
    s3, success = published(package)
    output = tmp_path / "readback"
    receipt = output / "verification.json"
    created, _ = inject_stream(monkeypatch, receipt, fault)

    def fail(*_):
        raise OSError("injected " + fault + " failure")

    if fault in ("fsync", "link"):
        monkeypatch.setattr(receipt_publication.os, fault, fail)
    with pytest.raises(OSError):
        readback.collect(s3, request, "aijob-fixture", success["sha256"], b"bundle",
                         Path("inert"), output)
    assert not receipt.exists() and len(created) == 1 and not created[0].exists()
    assert all((output / name).read_bytes() == raw for name, raw in artifacts.items())
    assert (output / "SUCCESS").exists() and (output / "checksums.json").exists()
