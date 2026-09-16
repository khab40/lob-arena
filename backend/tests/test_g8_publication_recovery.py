"""Post-MLflow recovery only: never retry the final evaluation or create a run."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("lightgbm")
mlflow = pytest.importorskip("mlflow")

from app.ml.lightgbm import cloud_runner, g8_publication_recovery as recovery  # noqa: E402
from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest  # noqa: E402
from serverless.jobs.g8_rehearsal import rehearse  # noqa: E402
from serverless.jobs.g8_publication_rehearsal import FakeS3  # noqa: E402


def fake_transport(monkeypatch, fake):
    monkeypatch.setattr(recovery.storage, "_aws_json", fake.aws)
    monkeypatch.setattr(recovery.shutil, "which", lambda _: "/synthetic/aws")
    monkeypatch.setattr(recovery.subprocess, "run", fake.run)


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    output = tmp_path_factory.mktemp("g8-publication") / "rehearsal"
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    previous = mlflow.get_tracking_uri()
    try:
        receipt = rehearse(output, runner, c4=True)
    finally:
        mlflow.set_tracking_uri(previous)
    source = output / "published"
    request = LightGbmCloudJobRequest.model_validate_json((source / "request.json").read_bytes())
    binding = recovery.RecoveryBinding(
        execution_package_sha256="e" * 64,  # Synthetic package identity, not live approval.
        request_sha256=request.canonical_hash(), candidate_sha256=request.candidate.sha256,
        c4_report_sha256=receipt["c4_report_sha256"], mlflow_run_id=receipt["mlflow_run_id"], result_uri=request.result_uri,
    )
    return source, binding


@pytest.fixture
def checkpoint(tmp_path, completed):
    source, binding = completed
    target = tmp_path / "checkpoint"
    digest = recovery.retain_completed_release(source, target, binding=binding)
    return target, digest, binding


def test_checkpoint_survives_source_loss_and_verifies_in_new_process(tmp_path, completed):
    source, binding = completed
    disposable = tmp_path / "original"
    shutil.copytree(source, disposable)
    destination = tmp_path / "retained"
    digest = recovery.retain_completed_release(disposable, destination, binding=binding)
    shutil.rmtree(disposable)
    binding_file = tmp_path / "reviewed-binding.json"
    binding_file.write_text(binding.model_dump_json())
    cli = Path(__file__).resolve().parents[2] / "serverless/jobs/recover_lightgbm_g8_publication.py"
    process = subprocess.run(
        [sys.executable, str(cli), "--checkpoint", str(destination), "--checkpoint-sha256", digest,
         "--binding", str(binding_file)], capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert json.loads(process.stdout)["remote_accessed"] is False
    assert sha256_file(destination / "payload/artifacts/c4-evaluation.json") == binding.c4_report_sha256


@pytest.mark.parametrize("damage", ["bytes", "extra", "missing", "symlink", "binding", "hash"])
def test_checkpoint_tamper_rejected_before_remote_access(checkpoint, monkeypatch, damage):
    root, digest, binding = checkpoint
    if damage == "bytes":
        (root / "payload/metrics.json").write_text("{}")
    elif damage == "extra":
        (root / "payload/extra").write_text("unexpected")
    elif damage == "missing":
        (root / "payload/metrics.json").unlink()
    elif damage == "symlink":
        (root / "payload/extra").symlink_to(root / "checkpoint.json")
    elif damage == "binding":
        binding = binding.model_copy(update={"mlflow_run_id": "f" * 32})
    else:
        digest = "f" * 64
    monkeypatch.setattr(recovery.storage, "_aws_json", lambda *a: pytest.fail("unexpected remote access"))
    with pytest.raises(ValueError):
        recovery.resume_publication(root, expected_sha256=digest, binding=binding)


def test_interrupted_checkpoint_has_no_seal_and_cannot_be_reused(tmp_path, completed, monkeypatch):
    source, binding = completed
    target = tmp_path / "interrupted"
    original = recovery._directory_sync

    def interrupted(path):
        if path == target / "payload":
            raise OSError("injected filesystem failure")
        original(path)

    monkeypatch.setattr(recovery, "_directory_sync", interrupted)
    with pytest.raises(OSError):
        recovery.retain_completed_release(source, target, binding=binding)
    assert not (target / "checkpoint.json").exists()
    with pytest.raises(FileExistsError):
        recovery.retain_completed_release(source, target, binding=binding)


@pytest.mark.parametrize("fault", ["middle_put", "lost_response", "marker"])
def test_publication_fault_recovers_without_scoring_or_mlflow(checkpoint, completed, monkeypatch, fault):
    root, digest, binding = checkpoint
    fake = FakeS3(completed[0], binding)
    checkpoint_inventory = recovery.verify_checkpoint(root, expected_sha256=digest, binding=binding).inventory.files
    key = fake.prefix + "/" + checkpoint_inventory[3].path
    if fault == "lost_response":
        fake.lose_response = key
    else:
        fake.fail_put = fake.prefix + "/SUCCESS" if fault == "marker" else key
    fake_transport(monkeypatch, fake)
    monkeypatch.setattr(cloud_runner, "predict_governed_fold", lambda *a, **k: pytest.fail("rescoring"))
    monkeypatch.setattr(mlflow, "start_run", lambda *a, **k: pytest.fail("new MLflow run"))
    if fault != "lost_response":
        with pytest.raises(RuntimeError):
            recovery.resume_publication(root, expected_sha256=digest, binding=binding)
        preserved = dict(fake.objects)
        assert len(preserved) > 1
        assert fake.prefix + "/SUCCESS" not in preserved
        fake.fail_put = None
    else:
        preserved = {}
    receipt = recovery.resume_publication(root, expected_sha256=digest, binding=binding)
    assert all(fake.objects[key] == value for key, value in preserved.items())
    assert receipt["scoring_invocations"] == receipt["mlflow_writes"] == 0
    assert receipt["mlflow_run_id"] == binding.mlflow_run_id
    puts = [a[a.index("--key") + 1] for a in fake.calls if a[1] == "put-object"]
    assert puts[-1] == fake.prefix + "/SUCCESS"
    if fault == "lost_response":
        assert puts.count(key) == 1
    count = len(puts)
    again = recovery.resume_publication(root, expected_sha256=digest, binding=binding)
    assert again["conditionally_published_objects"] == 0
    assert len([a for a in fake.calls if a[1] == "put-object"]) == count
    for item in checkpoint_inventory:
        assert fake.objects[fake.prefix + "/" + item.path] == (root / "payload" / item.path).read_bytes()


@pytest.mark.parametrize("conflict", ["bytes", "metadata", "unexpected", "premature_success", "intent"])
def test_remote_conflicts_fail_without_writes(checkpoint, completed, monkeypatch, conflict):
    root, digest, binding = checkpoint
    fake = FakeS3(completed[0], binding)
    path = "SUCCESS" if conflict == "premature_success" else "metrics.json"
    key = fake.prefix + "/" + path
    fake.objects[key] = (root / "payload" / path).read_bytes()
    fake.metadata[key] = {"sha256": sha256_file(root / "payload" / path)}
    if conflict == "bytes":
        fake.objects[key] = b"x" * len(fake.objects[key])  # Spoof metadata, same size.
    elif conflict == "metadata":
        fake.metadata[key]["sha256"] = "f" * 64
    elif conflict == "unexpected":
        fake.objects[fake.prefix + "/FAILED"] = b"incident"
    elif conflict == "intent":
        fake.metadata[fake.intent]["request-sha256"] = "f" * 64
    fake_transport(monkeypatch, fake)
    with pytest.raises(ValueError):
        recovery.resume_publication(root, expected_sha256=digest, binding=binding)
    assert not any(args[1] == "put-object" for args in fake.calls)


def test_checkpoint_mutation_during_put_cannot_poison_the_prefix(checkpoint, completed, monkeypatch):
    root, digest, binding = checkpoint
    fake = FakeS3(completed[0], binding)
    fake.mutate_source = root / "payload"
    fake_transport(monkeypatch, fake)
    with pytest.raises(ValueError, match="checkpoint payload differs"):
        recovery.resume_publication(root, expected_sha256=digest, binding=binding)
    assert fake.prefix + "/SUCCESS" not in fake.objects
    source, original = fake.mutated
    key = fake.prefix + "/" + source.relative_to(root / "payload").as_posix()
    assert fake.objects[key] == original
    source.write_bytes(original)
    receipt = recovery.resume_publication(root, expected_sha256=digest, binding=binding)
    assert receipt["object_count"] == 60
    assert sum(a[1] == "put-object" and a[a.index("--key") + 1] == key for a in fake.calls) == 1


def test_unlisted_source_file_rejected_before_checkpoint_creation(tmp_path, completed):
    source, binding = completed
    altered = tmp_path / "source"
    shutil.copytree(source, altered)
    (altered / "unlisted-secret").write_text("must not be retained or published")
    with pytest.raises(ValueError, match="unlisted"):
        recovery.retain_completed_release(altered, tmp_path / "checkpoint", binding=binding)
    assert not (tmp_path / "checkpoint").exists()


def test_nonprogressing_remote_pagination_fails_closed(monkeypatch):
    calls = []

    def aws(endpoint, *args):
        calls.append(args)
        return {"Contents": [], "IsTruncated": True, "NextContinuationToken": str(len(calls))}

    monkeypatch.setattr(recovery.storage, "_aws_json", aws)
    with pytest.raises(ValueError, match="pagination"):
        recovery._listed_keys("fixture", "exact/prefix", {"exact/prefix/a"})
    assert len(calls) == 1


@pytest.mark.parametrize("status", ["verified", "failed"])
@pytest.mark.parametrize("stage", ["retain", "resume"])
def test_non_succeeded_cloud_run_rejected_even_with_regenerated_inventories(
    tmp_path, completed, checkpoint, monkeypatch, status, stage,
):
    source, binding = completed
    root, _, _ = checkpoint
    if stage == "retain":
        source = shutil.copytree(source, tmp_path / "altered")
    else:
        source = root / "payload"
    cloud_run = source / "cloud-run.json"
    data = json.loads(cloud_run.read_bytes())
    data["status"] = status
    if status == "failed":
        data["error_type"] = "SyntheticFailure"
    recovery.LightGbmCloudRun.model_validate(data)  # A valid schema must still be rejected by recovery.
    cloud_run.write_text(json.dumps(data))
    inventory = recovery.storage.inventory_directory(source, exclude_markers=True)
    recovery.storage.write_checksum_file(source, inventory)
    (source / "SUCCESS").write_text(inventory.model_dump_json(indent=2))
    monkeypatch.setattr(recovery.storage, "_aws_json", lambda *a: pytest.fail("unexpected remote access"))
    if stage == "retain":
        with pytest.raises(ValueError, match="completed G8 release differs"):
            recovery.retain_completed_release(source, tmp_path / "rejected", binding=binding)
        assert not (tmp_path / "rejected").exists()
    else:
        seal = recovery.PublicationCheckpoint(binding=binding, inventory=recovery.storage.inventory_directory(source))
        (root / "checkpoint.json").write_bytes(recovery._canonical(seal))
        with pytest.raises(ValueError, match="completed G8 release differs"):
            recovery.resume_publication(root, expected_sha256=sha256_file(root / "checkpoint.json"), binding=binding)


@pytest.mark.parametrize("operation", ["put-object", "get-object"])
@pytest.mark.parametrize("size,expected_timeout", [(0, 300), (1024**3, 325), (5 * 1024**3, 1144)])
def test_transfer_uses_sealed_size_timeout_without_calling_frozen_helper(monkeypatch, operation, size, expected_timeout):
    calls = []
    monkeypatch.setattr(recovery.shutil, "which", lambda _: "/synthetic/aws")
    monkeypatch.setattr(recovery.storage, "_aws_json", lambda *a: pytest.fail("frozen helper has no timeout keyword"))

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(recovery.subprocess, "run", run)
    assert recovery._transfer_json(size, "s3api", operation) == {}
    assert calls[0][0] == ["/synthetic/aws", "--endpoint-url", recovery.ENDPOINT, "s3api", operation, "--output", "json"]
    assert calls[0][1]["timeout"] == expected_timeout
    assert calls[0][1]["env"]["AWS_PAGER"] == ""


def test_changed_bytes_during_snapshot_copy_never_reach_upload(tmp_path, monkeypatch):
    source = tmp_path / "checkpoint-object"
    source.write_bytes(b"sealed bytes")
    entry = recovery.storage.InventoryEntry(path=source.name, size_bytes=source.stat().st_size, sha256=sha256_file(source))
    original_copy = recovery.shutil.copyfileobj

    def changed(original, output):
        source.write_bytes(b"changed data")
        original_copy(original, output)

    monkeypatch.setattr(recovery.shutil, "copyfileobj", changed)
    with pytest.raises(ValueError, match="upload snapshot"):
        with recovery._upload_snapshot(source, entry):
            pytest.fail("unverified copy reached the upload path")


@pytest.mark.parametrize("failure", ["timeout", "exit", "json"])
def test_transfer_errors_are_sanitized(monkeypatch, failure):
    monkeypatch.setattr(recovery.shutil, "which", lambda _: "/synthetic/aws")

    def run(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr="sensitive fixture text")
        return subprocess.CompletedProcess(command, 1 if failure == "exit" else 0, "sensitive fixture text", "secret")

    monkeypatch.setattr(recovery.subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        recovery._transfer_json(5 * 1024**3, "s3api", "put-object")
    assert "sensitive" not in str(error.value) and "secret" not in str(error.value)
