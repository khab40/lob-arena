import hashlib
import json
import shutil

import pytest

pytest.importorskip("lightgbm")
mlflow = pytest.importorskip("mlflow")

from app.ml.lightgbm import g8_scored_checkpoint as checkpoint  # noqa: E402
from app.ml.lightgbm import g8_mlflow_recovery as tracking  # noqa: E402
from app.nebius.object_storage import TransferLimits  # noqa: E402
from serverless.jobs.g8_checkpoint_rehearsal import prepare, rehearse_checkpoint, _target  # noqa: E402


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    output = tmp_path_factory.mktemp("g8-prelog") / "source"
    receipt = prepare(output)
    return output, receipt, _target(output)


@pytest.fixture
def copied(sealed, tmp_path, monkeypatch):
    output, receipt, target = sealed
    root = tmp_path / "checkpoint"
    shutil.copytree(output / "durable/checkpoint", root)
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    return root, receipt["checkpoint_sha256"], target


def verify(copied):
    root, digest, target = copied
    return checkpoint.verify_scored_checkpoint(root, expected_sha256=digest, target=target)


def reseal(root):
    model = checkpoint.ScoredCheckpoint.model_validate_json((root / "checkpoint.json").read_bytes())
    model = model.model_copy(update={"inventory": checkpoint._inventory(root / "payload", TransferLimits())})
    content = checkpoint._canonical(model)
    (root / "checkpoint.json").write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_checkpoint_precedes_logging_and_keeps_original_context(sealed, monkeypatch):
    output, receipt, target = sealed
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    model = checkpoint.verify_scored_checkpoint(
        output / "durable/checkpoint", expected_sha256=receipt["checkpoint_sha256"], target=target,
    )
    client = mlflow.MlflowClient(tracking_uri=target.spec.tracking_uri)
    run = client.get_run(receipt["mlflow_run_id"])
    assert run.info.status == "RUNNING"
    assert not run.data.metrics and not run.inputs.dataset_inputs
    assert not client.list_artifacts(run.info.run_id)
    assert not (target.ledger_root / target.spec.identity() / "logging-plan.json").exists()
    assert model.context.dataset_source_uri.startswith("s3://")
    assert len(model.inventory.files) > 300  # Complete original checkpoint/replay payloads retained.
    assert not any("workspace" in entry.path for entry in model.inventory.files)


@pytest.mark.parametrize("change", ["missing", "extra", "symlink", "predictions", "report", "comparison"])
def test_corrupt_payload_rejected_before_mlflow(copied, monkeypatch, change):
    root, _, _ = copied
    payload = root / "payload"
    if change == "extra":
        (payload / "extra.json").write_text("{}")
    elif change == "missing":
        (payload / "metadata/profile.json").unlink()
    elif change == "symlink":
        path = payload / "metadata/profile.json"
        content = path.read_bytes()
        path.unlink()
        (root.parent / "outside.json").write_bytes(content)
        path.symlink_to(root.parent / "outside.json")
    else:
        relative = {
            "predictions": "artifacts/prediction/prediction-manifest.json",
            "report": "artifacts/c4-evaluation.json",
            "comparison": "comparison/comparison.json",
        }[change]
        with (payload / relative).open("ab") as stream:
            stream.write(b" ")
    monkeypatch.setattr(tracking, "_client", lambda *a: pytest.fail("invalid checkpoint reached MLflow"))
    with pytest.raises(ValueError, match="inventory|symlinks"):
        checkpoint.recover_scored_checkpoint(root, expected_sha256=copied[1], target=copied[2])


@pytest.mark.parametrize("change", ["wrong_hash", "unsealed", "extra_root", "noncanonical", "binding"])
def test_marker_boundary_fails_closed(copied, change):
    root, digest, target = copied
    if change == "wrong_hash":
        digest = "0" * 64
    elif change == "unsealed":
        (root / "checkpoint.json").rename(root / ".checkpoint.pending")
    elif change == "extra_root":
        (root / "SUCCESS").write_text("not a completed release")
    else:
        raw = json.loads((root / "checkpoint.json").read_bytes())
        if change == "binding":
            raw["reservation"]["candidate_sha256"] = "0" * 64
        content = (json.dumps(raw) + "\n").encode()
        (root / "checkpoint.json").write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
    with pytest.raises(ValueError, match="retained hash|unsealed|noncanonical|mismatched"):
        checkpoint.verify_scored_checkpoint(root, expected_sha256=digest, target=target)


def test_resealed_forged_report_still_requires_original_c4_provenance(copied, monkeypatch):
    root, _, target = copied
    path = root / "payload/artifacts/c4-evaluation.json"
    report = json.loads(path.read_bytes())
    report["metrics"]["lightgbm.row_f1"] = 0.12345
    path.write_text(json.dumps(report))
    digest = reseal(root)
    monkeypatch.setattr(tracking, "_client", lambda *a: pytest.fail("forged report reached MLflow"))
    with pytest.raises(ValueError, match="verified evaluator output"):
        checkpoint.recover_scored_checkpoint(root, expected_sha256=digest, target=target)


def test_resealed_changed_comparison_checkpoint_is_rejected(copied):
    root, _, target = copied
    path = next((root / "payload/comparison").rglob("alerts.jsonl"))
    path.write_bytes(path.read_bytes() + b"{}\n")
    with pytest.raises(ValueError, match="checksum"):
        checkpoint.verify_scored_checkpoint(root, expected_sha256=reseal(root), target=target)


@pytest.mark.parametrize("limits", [TransferLimits(max_files=1), TransferLimits(max_bytes=1)])
def test_verification_enforces_resource_bounds(copied, limits):
    root, digest, target = copied
    with pytest.raises(ValueError, match="limits"):
        checkpoint.verify_scored_checkpoint(root, expected_sha256=digest, target=target, limits=limits)


def test_missing_reservation_cannot_be_recreated(copied, tmp_path, monkeypatch):
    root, digest, target = copied
    bad = tracking.ResumeTarget(tmp_path / "missing-ledger", target.spec)
    monkeypatch.setattr(tracking, "_client", lambda *a: pytest.fail("missing ledger reached MLflow"))
    with pytest.raises(ValueError, match="ledger"):
        checkpoint.recover_scored_checkpoint(root, expected_sha256=digest, target=bad)
    assert not bad.ledger_root.exists()


def test_checkpoint_cannot_be_rebound_to_another_run(copied, tmp_path):
    root, digest, target = copied
    ledger = tmp_path / "different-ledger"
    shutil.copytree(target.ledger_root, ledger)
    record_path = ledger / target.spec.identity() / "run.json"
    record = json.loads(record_path.read_bytes())
    record["run_id"] = "f" * 32
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="different reserved MLflow run"):
        checkpoint.verify_scored_checkpoint(
            root, expected_sha256=digest, target=tracking.ResumeTarget(ledger, target.spec),
        )


def test_retention_refuses_after_logging_started(copied, tmp_path):
    root, _, target = copied
    model = verify(copied)
    ledger = tmp_path / "late-ledger"
    shutil.copytree(target.ledger_root, ledger)
    (ledger / target.spec.identity() / "logging-plan.json").write_text("{}")
    late_target = tracking.ResumeTarget(ledger, target.spec)
    args = checkpoint._arguments(root / "payload", model.context, late_target)
    with pytest.raises(ValueError, match="precede the first"):
        checkpoint.retain_scored_checkpoint(
            tmp_path / "late-checkpoint", target=late_target,
            request_path=root / "payload/metadata/request.json", workspace_root=root / "payload", **args,
        )
    assert not (tmp_path / "late-checkpoint").exists()


def test_fifo_marker_is_rejected_without_reading(copied):
    import os

    root, _, _ = copied
    (root / "checkpoint.json").unlink()
    os.mkfifo(root / "checkpoint.json")
    with pytest.raises(ValueError, match="invalid scored checkpoint marker"):
        verify(copied)


def retain(copied, destination, **changes):
    root, _, target = copied
    model = verify(copied)
    args = checkpoint._arguments(root / "payload", model.context, target)
    args.update(changes)
    return checkpoint.retain_scored_checkpoint(
        destination, target=target, request_path=root / "payload/metadata/request.json",
        workspace_root=root / "payload", **args,
    )


def test_occupied_destination_is_preserved(copied):
    root, digest, _ = copied
    with pytest.raises((FileExistsError, ValueError)):
        retain(copied, root)
    assert hashlib.sha256((root / "checkpoint.json").read_bytes()).hexdigest() == digest


def test_failed_copy_never_seals_or_logs(copied, tmp_path, monkeypatch):
    destination = tmp_path / "interrupted"
    original = checkpoint._copy_file
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("synthetic storage loss")
        return original(*args, **kwargs)

    monkeypatch.setattr(checkpoint, "_copy_file", fail)
    monkeypatch.setattr(tracking, "_client", lambda *a: pytest.fail("retention wrote MLflow"))
    with pytest.raises(OSError, match="storage loss"):
        retain(copied, destination)
    assert destination.exists()
    assert not (destination / "checkpoint.json").exists()
    assert not (destination / "SUCCESS").exists()


def test_original_dataset_source_is_mandatory(copied, tmp_path):
    with pytest.raises(ValueError, match="explicit dataset source URI"):
        retain(copied, tmp_path / "no-source", dataset_source_uri=None)


def test_checkpoint_cannot_be_a_sibling_inside_ephemeral_workspace(copied):
    root, _, _ = copied
    destination = root / "payload/unsafe-checkpoint"
    with pytest.raises(ValueError, match="disjoint from workspace"):
        retain(copied, destination)
    assert not destination.exists()


def test_copy_cannot_outgrow_inventoried_size(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"ab")
    with pytest.raises(ValueError, match="grew beyond"):
        checkpoint._copy_file(source, tmp_path / "grown", size_bytes=1)
    assert (tmp_path / "grown").stat().st_size == 1
    with pytest.raises(ValueError, match="truncated"):
        checkpoint._copy_file(source, tmp_path / "short", size_bytes=3)


def test_recovery_snapshot_rejects_mutation_before_any_remote_write(copied, monkeypatch):
    root, digest, target = copied
    original = checkpoint._copy_file
    changed = []

    def mutate(source, destination, **kwargs):
        if not changed:
            content = source.read_bytes()
            source.write_bytes(bytes([content[0] ^ 1]) + content[1:])
            changed.append(source)
        return original(source, destination, **kwargs)

    monkeypatch.setattr(checkpoint, "_copy_file", mutate)
    monkeypatch.setattr(tracking, "_client", lambda *a: pytest.fail("mutable checkpoint reached MLflow"))
    with pytest.raises(ValueError, match="changed while creating private recovery snapshot"):
        checkpoint.recover_scored_checkpoint(root, expected_sha256=digest, target=target)


def test_full_fresh_process_recovery_after_workspace_loss(tmp_path):
    receipt = rehearse_checkpoint(tmp_path / "fresh-process-proof")
    assert receipt["workspace_removed_before_recovery"]
    assert receipt["pre_logging_checkpoint_verified"]
    assert receipt["fresh_process_recovery_verified"]
    assert receipt["worker_exit_before_logging"] == 73
    assert receipt["recovery_exit_after_artifact_upload"] == 74
    assert receipt["final_scoring_call_count"] == 1
    assert receipt["mlflow_status"] == "FINISHED"
    assert receipt["verified_metric_count"] == 24
    assert receipt["verified_dataset_input_count"] == 30
    assert receipt["repeat_process"]["mlflow_write_calls"] == 0
    assert receipt["artifact_readback_verified"]
    assert not receipt["native_storage_verified"]
    assert not receipt["production_g8_complete"]
