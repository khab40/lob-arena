"""Synthetic package signatures and actual live recovery, no production access."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("mlflow")

from app.ml.lightgbm import g8_replacement as replacement  # noqa: E402
from app.ml.lightgbm import g8_live_recovery as live  # noqa: E402
from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile  # noqa: E402
from app.ml.lightgbm.g8_production_transport import BOOTSTRAP, PACKAGE, build_archives  # noqa: E402
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, CloudArtifact  # noqa: E402
from serverless.jobs.g8_checkpoint_rehearsal import prepare  # noqa: E402
from serverless.jobs.g8_live_rehearsal import rehearse_live  # noqa: E402


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    output = tmp_path_factory.mktemp("replacement-inputs") / "source"
    prepare(output)
    return output


@pytest.fixture
def package(tmp_path, synthetic, monkeypatch):
    root = tmp_path / "package"
    root.mkdir()
    source = synthetic / "durable/checkpoint/payload/metadata"
    workspace = synthetic / "workspace"
    for name in ("candidate.json", "profile.json", "frozen-root.json", "projection.json", "request.json"):
        shutil.copyfile(source / name, root / name)
    request = LightGbmCloudJobRequest.model_validate_json((root / "request.json").read_bytes())
    shutil.copyfile(workspace / request.input.dataset_lineage_receipt.uri, root / "dataset-lineage.json") if (
        workspace / request.input.dataset_lineage_receipt.uri).exists() else shutil.copyfile(
            Path(json.loads((workspace / "c4-inputs.json").read_bytes())["projection"]).parent
            / "c4-mlflow-dataset-release.json", root / "dataset-lineage.json")
    private = tmp_path / "private.pem"
    for args in (["genpkey", "-algorithm", "Ed25519", "-out", str(private)],
                 ["pkey", "-in", str(private), "-pubout", "-out", str(root / "authorization-public.pem")]):
        subprocess.run(["openssl", *args], check=True, capture_output=True)
    auth = json.loads((workspace / request.authorization.uri).read_bytes())
    auth["signed_at"] = datetime.now(UTC).isoformat()
    # The synthetic authorization schema binds the timestamp in its statement.
    auth["statement"] = f"APPROVE WAVE1 FINAL TEST {request.candidate.sha256} {auth['signed_at']}"
    (root / "authorization.json").write_text(json.dumps(auth))
    subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-rawin", "-in",
                    str(root / "authorization.json"), "-out", str(root / "authorization.sig")], check=True)
    refs = {}
    for key, name in (("authorization", "authorization.json"), ("authorization_signature", "authorization.sig"),
                      ("authorization_public_key", "authorization-public.pem")):
        refs[key] = CloudArtifact(logical_name=key, uri="authorization/" + name, sha256=sha256_file(root / name),
                                  size_bytes=(root / name).stat().st_size)
    request = request.model_copy(update=refs)
    (root / "request.json").write_bytes(request.canonical_bytes())
    # Freeze the synthetic identities for this unit test only. No production bypass flag exists.
    monkeypatch.setattr(replacement, "CANDIDATE", request.candidate.sha256)
    monkeypatch.setattr(replacement, "FINAL_RELEASE", request.input_release_uri)
    monkeypatch.setattr(replacement, "FROZEN_ROOT", request.input.frozen_root.sha256)
    monkeypatch.setattr(replacement, "FINAL_PROJECTION", request.input.projection.sha256)
    profile = C4EvaluationProfile.model_validate_json((root / "profile.json").read_bytes())
    inputs = {name: f"{PACKAGE}/{file}" for name, file in (("candidate", "candidate.json"),
        ("profile", "profile.json"), ("projection", "projection.json"), ("frozen_root", "frozen-root.json"))}
    inputs["comparison"] = "/g8-durable/comparison/original/comparison.json"
    (root / "c4-inputs.json").write_text(json.dumps(inputs))
    now = datetime.now(UTC)
    receipts = {
        "native-durability": {"filesystem_id": "computefilesystem-synthetic", "mount_source": "synthetic-volume",
            "mount_type": "virtiofs", "capacity_gib": 10, "job_loss_reattachment_verified": True},
        "remote-roundtrip": {"authenticated_mlflow_artifact_readback": True, "authenticated_s3_readback": True,
                             "tracking_uri": request.mlflow_tracking_uri, "image": request.image},
        "comparison-inventory": {"comparison_sha256": profile.comparison_evidence_sha256,
                                 "original_checkpoint_count": 27, "metadata_inventory_verified": True},
    }
    for name, value in receipts.items():
        (root / f"{name}.json").write_text(json.dumps({**value, "verified_at": now.isoformat()}))
    repo = Path(__file__).resolve().parents[2]
    for name in replacement.CODE_PATHS:
        source_file = (repo / "backend/app/ml/lightgbm" if name.removesuffix(".py") in replacement.MODULES
                       else repo / "serverless/jobs") / name
        shutil.copyfile(source_file, root / name)
    for name, raw in build_archives({name: (root / name).read_bytes() for name in replacement.CODE_PATHS},
                                    replacement.CODE_PATHS).items():
        (root / name).write_bytes(raw)
    shutil.copyfile(repo / "serverless/jobs" / BOOTSTRAP, root / BOOTSTRAP)
    files = {path.name: replacement.PackageFile(sha256=sha256_file(path), size_bytes=path.stat().st_size)
             for path in root.iterdir()}
    plan = replacement.ReplacementPlan(source_commit="a" * 40, run_id=request.run_id, request_sha256=request.canonical_hash(),
        candidate_sha256=request.candidate.sha256, filesystem_id="computefilesystem-synthetic",
        mount_source="synthetic-volume", capacity_gib=10, max_checkpoint_bytes=1024**3, max_checkpoint_files=10000,
        comparison_relative_path="comparison/original/comparison.json",
        evaluation_profile_sha256=profile.canonical_hash(), comparison_sha256=profile.comparison_evidence_sha256,
        candidate_release_uri="s3://aimada-wave1-results-e00g6zvxpr00/campaigns/synthetic/development/selected",
        secret_selectors={name: "mbsec-synthetic@mbsecver-synthetic" for name in
                          ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD")},
        verified_at=now,
        prior_monitor_sha256="e6975dcd517dda25b91a0b6bea9a786c87f7d82a451fcb71a8dcc34355016b72",
        prior_log_sha256="eadddbdbac943939a9b8243398584ac8866352b30117ef7ea0e3fb9ed9ac2a8c",
        native_durability_receipt_sha256=files["native-durability.json"].sha256,
        authenticated_remote_receipt_sha256=files["remote-roundtrip.json"].sha256,
        comparison_inventory_receipt_sha256=files["comparison-inventory.json"].sha256,
        files=files)
    sign(root, private, plan)
    return root, private, plan, sha256_file(root / "authorization-public.pem")


def sign(root, private, plan):
    (root / "replacement.json").write_bytes(replacement.canonical(plan))
    subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-rawin", "-in",
                    str(root / "replacement.json"), "-out", str(root / "replacement.sig")], check=True)


def test_signed_complete_package_verifies_without_remote_access(package):
    root, _, plan, trusted = package
    verified, request = replacement.verify_package(root, trusted_key=trusted)
    assert verified == plan and request.canonical_hash() == plan.request_sha256
    command = replacement.job_command(plan, root, trusted)
    assert command.count("--volume") == 2 and "--public" not in command
    assert command[command.index("--volume") + 1] == "computefilesystem-synthetic:/g8-durable:rw"
    assert "MLFLOW_HTTP_REQUEST_MAX_RETRIES=0" in command
    assert command.count("--inject-file") == 1
    assert command[command.index("--inject-file") + 1].endswith(":/job/g8/" + BOOTSTRAP)
    assert "computefilesystem-synthetic:/g8-package:ro" in command


@pytest.mark.parametrize("mode,delayed", [
    ("--command", False), ("--recovery-command", False), ("--recovery-command", True),
])
def test_cli_renders_exact_operation_without_entering_lifecycle(package, monkeypatch, capsys, mode, delayed):
    import sys
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, _, plan, trusted = package
    monkeypatch.setenv("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", trusted)
    monkeypatch.setattr(sys, "argv", ["replacement", "--package", str(root), mode])
    verify = replacement.verify_package
    monkeypatch.setattr(cli, "verify_package", lambda *a, **kw: verify(
        *a, **kw, now=plan.verified_at + timedelta(days=7) if delayed else plan.verified_at))
    monkeypatch.setattr(cli, "verify_mount", lambda *a: pytest.fail("rendering inspected live mount"))
    monkeypatch.setattr(cli, "observed_context", lambda *a, **kw: pytest.fail("rendering waited for context"))
    monkeypatch.setattr(live, "run_live", lambda *a, **kw: pytest.fail("rendering entered scoring"))
    monkeypatch.setattr(live, "finish_retained", lambda *a, **kw: pytest.fail("rendering entered recovery"))
    cli.main()
    command = json.loads(capsys.readouterr().out)
    recovery = mode == "--recovery-command"
    operation = "--recover" if recovery else "--execute"
    assert command[command.index("--args") + 1] == (
        f"/job/g8/{BOOTSTRAP} {operation} --package {PACKAGE}")
    assert command[command.index("--name") + 1] == plan.run_id + ("-recovery" if recovery else "")
    assert command == replacement.job_command(plan, root, trusted, recovery=recovery)
    assert command[command.index("--volume") + 1] == f"{plan.filesystem_id}:{plan.mount_path}:rw"
    assert not (root / "__pycache__").exists()


@pytest.mark.parametrize("mode", ["--command", "--recovery-command"])
def test_cli_rendering_rejects_future_package(package, monkeypatch, mode):
    import sys
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, _, plan, trusted = package
    monkeypatch.setenv("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", trusted)
    monkeypatch.setattr(sys, "argv", ["replacement", "--package", str(root), mode])
    verify = replacement.verify_package
    monkeypatch.setattr(cli, "verify_package", lambda *a, **kw: verify(
        *a, **kw, now=plan.verified_at - timedelta(seconds=1)))
    monkeypatch.setattr(cli, "job_command", lambda *a, **kw: pytest.fail("future package rendered"))
    with pytest.raises(ValueError, match="future"):
        cli.main()


def test_cli_rechecks_package_without_creating_bytecode_members(package, monkeypatch):
    import sys
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, _, _, trusted = package
    monkeypatch.setenv("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", trusted)
    monkeypatch.setattr(sys, "argv", ["replacement", "--package", str(root), "--execute"])
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.setattr(cli, "verify_runtime", lambda *a: None)  # Tested separately without model work.
    events = []
    monkeypatch.setattr(cli, "verify_mount", lambda plan: events.append("mount") or ("31", "20", "0:44", "/"))
    from types import SimpleNamespace
    monkeypatch.setattr(cli, "observed_context", lambda *a: events.append("context") or SimpleNamespace(
        nebius_job_id="aijob-synthetic"))
    called = []
    monkeypatch.setattr(live, "run_live", lambda *a: events.append("run") or called.append(1) or {})
    cli.main()
    assert called == [1]
    assert events == ["mount", "context", "mount", "run"]
    assert not (root / "__pycache__").exists()


@pytest.mark.parametrize("mode", ["--execute", "--recover"])
@pytest.mark.parametrize("change", ["detached", "replaced", "source_changed"])
def test_cli_rechecks_native_mount_after_context_wait(package, monkeypatch, mode, change):
    import sys
    from types import SimpleNamespace
    from app.ml.lightgbm import cloud_runner
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, _, _, trusted = package
    monkeypatch.setenv("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", trusted)
    monkeypatch.setattr(sys, "argv", ["replacement", "--package", str(root), mode])
    monkeypatch.setattr(cli, "verify_runtime", lambda *a: None)
    line = "31 20 0:44 / /g8-durable rw,relatime - virtiofs synthetic-volume rw"
    current = [line]
    observations = []

    def mount(plan):
        observations.append(current[0])
        return replacement.verify_mount(plan, current[0])

    def context(*a, **kw):
        current[0] = {"detached": "", "replaced": line.replace("31 20", "32 20"),
                      "source_changed": line.replace("synthetic-volume", "other")}[change]
        return SimpleNamespace(nebius_job_id="aijob-synthetic")

    monkeypatch.setattr(cli, "verify_mount", mount)
    monkeypatch.setattr(cli, "observed_context", context)
    monkeypatch.setattr(cloud_runner, "_validate_execution_context", lambda *a: None)
    monkeypatch.setattr(live, "execution_lock", lambda *a, **kw: pytest.fail("changed mount reached lock"))
    monkeypatch.setattr(live, "run_live", lambda *a, **kw: pytest.fail("changed mount reached scoring"))
    monkeypatch.setattr(live, "finish_retained", lambda *a, **kw: pytest.fail("changed mount reached recovery"))
    with pytest.raises(ValueError, match="durable mount"):
        cli.main()
    assert observations == [line, current[0]]


def test_signed_job_context_is_purpose_bound_and_uses_actual_job_id(package, tmp_path):
    from types import SimpleNamespace
    from app.ml.lightgbm.cloud_contracts import Wave1ExecutionContext
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, private, plan, trusted = package
    mount = tmp_path / "mount"
    (mount / "contexts").mkdir(parents=True)
    local_plan = SimpleNamespace(**{**plan.model_dump(), "mount_path": str(mount), "identity": plan.identity})
    path = mount / "contexts" / (plan.run_id + "-recovery.json")
    context = Wave1ExecutionContext(project_id="project-e00g6zvxpr00waz8t3y51k", image=plan.image,
        platform="cpu-d3", preset="4vcpu-16gb", disk_size_gib=100, timeout_seconds=3600,
        nebius_job_id="aijob-synthetic-recovery")
    raw = {"purpose": "recover", "execution_package_sha256": plan.identity(), "filesystem_id": plan.filesystem_id,
           "context": context.model_dump(mode="json"), "job_readback_sha256": "a" * 64}
    path.write_text(json.dumps(raw))
    subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-rawin", "-in", str(path),
                    "-out", str(path.with_suffix(".sig"))], check=True)
    assert cli.observed_context(local_plan, root, trusted, recovery=True) == context
    original = mount / "contexts" / (plan.run_id + ".json")
    shutil.copyfile(path, original)
    shutil.copyfile(path.with_suffix(".sig"), original.with_suffix(".sig"))
    with pytest.raises(ValueError, match="differs"):
        cli.observed_context(local_plan, root, trusted)
    path.write_text(json.dumps({**raw, "job_readback_sha256": "b" * 64}))
    with pytest.raises(ValueError, match="signature"):
        cli.observed_context(local_plan, root, trusted, recovery=True)


def test_missing_signed_job_context_times_out_without_final_access(package, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from serverless.jobs import run_lightgbm_g8_replacement as cli

    root, _, plan, trusted = package
    local_plan = SimpleNamespace(**{**plan.model_dump(), "mount_path": str(tmp_path)})
    ticks = iter([0, 301])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="unavailable"):
        cli.observed_context(local_plan, root, trusted)


@pytest.mark.parametrize("field,value", [("prior_final_jobs_submitted", 0), ("prior_test_fold_accessed", False),
    ("run_id", "nasdaq-g8-final-r4-20260913"), ("candidate_sha256", "0" * 64), ("capacity_gib", 1), ("filesystem_id", "storagebucket-synthetic"),
    ("mount_path", "/job"), ("max_checkpoint_bytes", 0)])
def test_replacement_boundaries_reject(package, field, value):
    _, _, plan, _ = package
    with pytest.raises(ValueError):
        replacement.ReplacementPlan.model_validate({**plan.model_dump(), field: value})


@pytest.mark.parametrize("name", ["g8_live_recovery.py", "profile.json", "request.json", "remote-roundtrip.json"])
def test_package_tamper_fails_before_signature_or_remote(package, name):
    root, _, _, trusted = package
    with (root / name).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="changed"):
        replacement.verify_package(root, trusted_key=trusted)


def test_changed_signed_plan_and_untrusted_key_rejected(package):
    root, _, plan, trusted = package
    with pytest.raises(ValueError, match="trusted"):
        replacement.verify_package(root, trusted_key="0" * 64)
    (root / "replacement.json").write_bytes(replacement.canonical(plan.model_copy(update={"capacity_gib": 11})))
    with pytest.raises(ValueError, match="signature"):
        replacement.verify_package(root, trusted_key=trusted)


def test_delayed_package_keeps_authorization_without_billing(package):
    root, _, plan, trusted = package
    assert not (root / "billing.json").exists()
    for recovery in (False, True):
        verified, _ = replacement.verify_package(root, trusted_key=trusted,
            now=plan.verified_at + timedelta(days=7), recovery=recovery)
        assert verified.identity() == plan.identity()


def test_signed_but_failed_remote_receipt_rejected(package):
    root, private, plan, trusted = package
    path = root / "remote-roundtrip.json"
    raw = json.loads(path.read_bytes())
    raw["authenticated_s3_readback"] = False
    path.write_text(json.dumps(raw))
    files = {**plan.files, path.name: replacement.PackageFile(sha256=sha256_file(path), size_bytes=path.stat().st_size)}
    plan = plan.model_copy(update={"files": files, "authenticated_remote_receipt_sha256": sha256_file(path)})
    sign(root, private, plan)
    with pytest.raises(ValueError, match="incomplete"):
        replacement.verify_package(root, trusted_key=trusted)


@pytest.mark.parametrize("change", ["absent", "overlay", "fuse", "readonly", "wrongsource", "duplicate", "nested"])
def test_native_mount_fail_closed(package, change):
    plan = package[2]
    line = "31 20 0:44 / /g8-durable rw,relatime - virtiofs synthetic-volume rw"
    replacement.verify_mount(plan, line)
    bad = {"absent": "", "overlay": line.replace("virtiofs", "overlay"),
        "fuse": line.replace("virtiofs", "fuse.s3fs"), "readonly": line.replace("rw", "ro"),
        "wrongsource": line.replace("synthetic-volume", "other"), "duplicate": line + "\n" + line,
        "nested": line + "\n" + line.replace("/g8-durable ", "/g8-durable/workspace ")}[change]
    with pytest.raises(ValueError):
        replacement.verify_mount(plan, bad)


def test_occupied_run_and_missing_recovery_never_reexecute(tmp_path):
    root = tmp_path / "run"
    with pytest.raises(ValueError):
        with live.execution_lock(root, create=False):
            pytest.fail("missing workspace entered recovery")
    with live.execution_lock(root, create=True):
        pass
    with pytest.raises(FileExistsError):
        with live.execution_lock(root, create=True):
            pytest.fail("occupied run reentered scoring")


@pytest.fixture(scope="module")
def completed_live(tmp_path_factory):
    root = tmp_path_factory.mktemp("live-proof") / "live"
    return root, rehearse_live(root)


def test_actual_live_lifecycle_recovers_after_workspace_loss(completed_live):
    _, receipt = completed_live
    assert receipt["final_scoring_call_count"] == 1
    assert receipt["original_workspace_absent"] and receipt["original_job_identity_verified"]
    assert receipt["marker_failure_recovered"] and receipt["completed_repeat_writes"] == 0
    assert not receipt["native_storage_verified"] and not receipt["remote_authentication_verified"]


@pytest.mark.parametrize("mutation", ["job", "resource", "report"])
def test_resealed_publication_cannot_substitute_original_scored_evidence(completed_live, tmp_path, monkeypatch, mutation):
    from app.ml.lightgbm import g8_publication_recovery as publication
    from app.ml.lightgbm.g8_mlflow_recovery import ReservationSpec, ResumeTarget
    from app.nebius import object_storage as storage

    original, _ = completed_live
    root = tmp_path / "run"
    shutil.copytree(original / "durable/synthetic-final", root)
    pointer = root / "publication-checkpoint.json"
    record = json.loads(pointer.read_bytes())
    checkpoint = root / record["directory"]
    payload = checkpoint / "payload"
    if mutation == "report":
        report = payload / "artifacts/c4-evaluation.json"
        report.write_bytes(report.read_bytes() + b" ")
        record["binding"]["c4_report_sha256"] = sha256_file(report)
    else:
        path = payload / "cloud-run.json"
        run = json.loads(path.read_bytes())
        if mutation == "job":
            run["nebius_job_id"] = "aijob-wrong-original"
        else:
            run["resource"]["peak_rss_bytes"] += 1
        path.write_text(json.dumps(run))
    inventory = storage.inventory_directory(payload, exclude_markers=True)
    storage.write_checksum_file(payload, inventory)
    (payload / "SUCCESS").write_text(inventory.model_dump_json(indent=2))
    model = publication.PublicationCheckpoint.model_validate_json((checkpoint / "checkpoint.json").read_bytes())
    model = model.model_copy(update={"binding": publication.RecoveryBinding.model_validate(record["binding"]),
                                     "inventory": publication._inventory(payload, storage.TransferLimits())})
    (checkpoint / "checkpoint.json").write_bytes(publication._canonical(model))
    record["sha256"] = sha256_file(checkpoint / "checkpoint.json")
    pointer.write_text(json.dumps(record))
    target = ResumeTarget(root / "ledger", ReservationSpec.model_validate_json((root / "reservation.json").read_bytes()))
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setattr(live, "resume_publication", lambda *a, **kw: pytest.fail("substitution reached S3"))
    with pytest.raises(ValueError, match="original scor"):
        live.finish_retained(root, target)
