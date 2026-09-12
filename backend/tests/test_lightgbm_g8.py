from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("lightgbm", reason="Wave 1 G8 tests require the ml extra")

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import (
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
    Wave1FinalAuthorization,
    Wave1TabularProjectionInput,
)
from app.ml.lightgbm.g8_evaluation import (
    G8InjectedFile,
    G8PreflightReceipt,
    verify_g8_preflight,
)
from app.nebius.object_storage import inventory_directory, write_checksum_file
from serverless.jobs import run_lightgbm_g8 as runner


IMAGE = "ghcr.io/khab40/lob-arena-jobs@sha256:" + "d" * 64
FINAL_URI = (
    "s3://aimada-wave1-final-e00g6zvxpr00/"
    "releases/nasdaq-public-sample-v1-c4-test/staging"
)
CANDIDATE_URI = (
    "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
    "wave1-g8-test/development/selected"
)
RESULT_URI = (
    "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
    "wave1-g8-test/final/wave1-g8-final"
)


def test_g8_preflight_package_is_immutable_and_final_only(tmp_path: Path) -> None:
    package, request = _g8_package(tmp_path)

    receipt = verify_g8_preflight(package)

    assert receipt.request_sha256 == request.canonical_hash()
    assert receipt.development_jobs_consumed == 20
    assert receipt.final_jobs_submitted_before == 0
    assert receipt.test_fold_accessed is False
    assert receipt.cloud_resources_mutated is False
    assert request.mode == "final-evaluation"
    assert request.input_release_uri == FINAL_URI

    (package / "request.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory checksum mismatch"):
        verify_g8_preflight(package)


def test_g8_injected_destination_must_exactly_mirror_local_name() -> None:
    with pytest.raises(ValueError, match="exactly mirror"):
        G8InjectedFile(
            local_name="request.json",
            container_path="/job/g8/subdirectory/request.json",
            sha256="a" * 64,
            size_bytes=1,
        )


@pytest.mark.parametrize(
    "final_uri,candidate_uri",
    [
        (
            "s3://aimada-wave1-final-e00g6zvxpr00/releases/../escape/staging",
            CANDIDATE_URI,
        ),
        (
            FINAL_URI,
            "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/x/development/../final/x",
        ),
    ],
)
def test_g8_runner_rejects_noncanonical_release_paths(
    tmp_path: Path,
    final_uri: str,
    candidate_uri: str,
) -> None:
    _package, request = _g8_package(tmp_path)
    request = request.model_copy(update={"input_release_uri": final_uri})
    with pytest.raises(ValueError, match="escaped an approved Object Storage boundary"):
        runner._validate_request(request, final_uri, candidate_uri)


def test_g8_runner_checks_authorization_mlflow_and_empty_result_before_final_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package, request = _g8_package(tmp_path)
    events: list[str] = []

    def fake_download(source: str, destination: Path, **_kwargs: object) -> None:
        events.append(f"download:{source}")
        destination.mkdir(parents=True)
        if source == CANDIDATE_URI:
            (destination / "candidate.json").write_bytes(b"candidate")

    monkeypatch.setattr(runner, "download_s3_release", fake_download)
    monkeypatch.setattr(
        runner,
        "_verify_signature",
        lambda *_args, **_kwargs: events.append("authorization"),
    )
    monkeypatch.setattr(runner, "_verify_mlflow_ready", lambda _uri: events.append("mlflow"))
    monkeypatch.setattr(
        runner, "_require_empty_result", lambda *_args: events.append("empty-result")
    )
    monkeypatch.setattr(
        runner.FrozenCandidate,
        "model_validate_json",
        lambda _value: SimpleNamespace(
            campaign_id=request.campaign_id,
            experiment=request.experiment,
            test_fold_accessed=False,
        ),
    )
    result = tmp_path / "local-result"
    result.mkdir()
    monkeypatch.setattr(runner, "execute_wave1_request", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        runner,
        "publish_s3_result",
        lambda *_args, **_kwargs: events.append("publish"),
    )
    _set_runtime_environment(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_lightgbm_g8.py",
            "--request",
            str(package / "request.json"),
            "--authorization",
            str(package / "authorization/authorization.json"),
            "--authorization-signature",
            str(package / "authorization/authorization.sig"),
            "--authorization-public-key",
            str(package / "authorization/authorization-public.pem"),
            "--dataset-lineage",
            str(package / "manifests/c4-mlflow-dataset-release.json"),
            "--final-input-uri",
            FINAL_URI,
            "--candidate-uri",
            CANDIDATE_URI,
            "--work-root",
            str(tmp_path / "work"),
        ],
    )

    assert runner.main() == 0
    assert events[:5] == [
        "authorization",
        "mlflow",
        "empty-result",
        f"download:{CANDIDATE_URI}",
        f"download:{FINAL_URI}",
    ]
    assert events[-1] == "publish"


def test_g8_runner_does_not_read_final_when_mlflow_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package, _request = _g8_package(tmp_path)
    downloads: list[str] = []
    monkeypatch.setattr(runner, "_verify_signature", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_verify_mlflow_ready",
        lambda _uri: (_ for _ in ()).throw(RuntimeError("MLflow unavailable")),
    )
    monkeypatch.setattr(
        runner,
        "download_s3_release",
        lambda source, *_args, **_kwargs: downloads.append(source),
    )
    _set_runtime_environment(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_lightgbm_g8.py",
            "--request",
            str(package / "request.json"),
            "--authorization",
            str(package / "authorization/authorization.json"),
            "--authorization-signature",
            str(package / "authorization/authorization.sig"),
            "--authorization-public-key",
            str(package / "authorization/authorization-public.pem"),
            "--dataset-lineage",
            str(package / "manifests/c4-mlflow-dataset-release.json"),
            "--final-input-uri",
            FINAL_URI,
            "--candidate-uri",
            CANDIDATE_URI,
        ],
    )

    with pytest.raises(RuntimeError, match="MLflow unavailable"):
        runner.main()
    assert downloads == []


def test_g8_result_guard_atomically_claims_exact_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def claimed(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/bin/aws")
    monkeypatch.setattr(runner.subprocess, "run", claimed)
    _package, request = _g8_package(tmp_path)

    runner._require_empty_result(request, "https://storage.eu-north1.nebius.cloud")

    assert len(commands) == 1
    command = commands[0]
    assert "put-object" in command
    assert "list-objects-v2" not in command
    assert "head-object" not in command
    assert command[command.index("--key") + 1] == (
        "campaigns/wave1-g8-test/final/.intents/wave1-g8-final.json"
    )
    assert command[command.index("--if-none-match") + 1] == "*"


def test_g8_result_guard_fails_closed_on_denied_or_existing_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _package, request = _g8_package(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/bin/aws")
    denied = subprocess.CompletedProcess([], 255, "", "AccessDenied")
    monkeypatch.setattr(runner.subprocess, "run", lambda *_args, **_kwargs: denied)
    with pytest.raises(RuntimeError, match="could not acquire"):
        runner._require_empty_result(request, "https://storage.eu-north1.nebius.cloud")

    present = subprocess.CompletedProcess([], 255, "", "PreconditionFailed (412)")
    monkeypatch.setattr(runner.subprocess, "run", lambda *_args, **_kwargs: present)
    with pytest.raises(FileExistsError, match="intent already exists"):
        runner._require_empty_result(request, "https://storage.eu-north1.nebius.cloud")


def test_submitter_accepts_g8_only_at_consumed_development_ceiling(tmp_path: Path) -> None:
    package, _request = _g8_package(tmp_path)
    script = Path(__file__).resolve().parents[2] / "scripts" / "submit_nebius_job.py"
    environment = {
        **os.environ,
        "NEBIUS_SUBNET_ID": "subnet-test",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID": "final-access-selector",
        "NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID": "final-secret-selector",
        "NEBIUS_MLFLOW_USERNAME_SECRET_ID": "mlflow-user-selector",
        "NEBIUS_MLFLOW_PASSWORD_SECRET_ID": "mlflow-password-selector",
        "NEBIUS_OBJECT_STORAGE_ENDPOINT_URL": "https://storage.eu-north1.nebius.cloud",
        "NEBIUS_WAVE1_INPUT_URI": FINAL_URI,
        "NEBIUS_WAVE1_REQUEST_EVIDENCE": str(package / "g8-preflight.json"),
        "NEBIUS_WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256": "a" * 64,
        "WAVE1_SPEND_TO_DATE_USD": "28.65",
        "WAVE1_DEVELOPMENT_JOBS_CONSUMED": "20",
    }
    for name in (
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN",
    ):
        environment.pop(name, None)
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--workload",
            "lightgbm-wave1",
            "--image",
            IMAGE,
            "--evidence-output",
            str(tmp_path / "dry-run.json"),
            "--dry-run",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    )
    payload = json.loads(completed.stdout)
    command = payload["command"]
    assert payload["development_jobs_consumed"] == 20
    assert command.count("--inject-file") == 6
    assert "run_lightgbm_g8.py" in " ".join(command)
    assert "final-access-selector" not in completed.stdout
    assert "mlflow-password-selector" not in completed.stdout

    rejected = subprocess.run(
        [sys.executable, str(script), "--workload", "lightgbm-wave1", "--image", IMAGE, "--dry-run"],
        check=False,
        text=True,
        capture_output=True,
        env={**environment, "WAVE1_DEVELOPMENT_JOBS_CONSUMED": "19"},
    )
    assert rejected.returncode != 0
    assert "exact reconciled development Job count" in rejected.stderr


def _g8_package(tmp_path: Path) -> tuple[Path, LightGbmCloudJobRequest]:
    package = tmp_path / "package"
    package.mkdir()
    (package / "run_lightgbm_g8.py").write_text("print('g8')\n", encoding="utf-8")
    authorization = package / "authorization"
    authorization.mkdir()
    manifests = package / "manifests"
    manifests.mkdir()
    (manifests / "c4-mlflow-dataset-release.json").write_bytes(b"lineage")
    candidate_hash = sha256_file(_write(tmp_path / "candidate.json", b"candidate"))
    signed_at = datetime(2026, 9, 12, 13, 8, 31, tzinfo=UTC)
    final_authorization = Wave1FinalAuthorization(
        campaign_id="wave1-g8-test",
        candidate_hash=candidate_hash,
        signer="Alexey Khabalov — Wave 1 Release Approver",
        signed_at=signed_at,
        statement=(
            f"APPROVE WAVE1 FINAL TEST {candidate_hash} {signed_at.isoformat()}"
        ),
    )
    (authorization / "authorization.json").write_bytes(final_authorization.canonical_bytes())
    (authorization / "authorization.sig").write_bytes(b"signature")
    (authorization / "authorization-public.pem").write_bytes(b"public-key")

    request = LightGbmCloudJobRequest(
        campaign_id="wave1-g8-test",
        run_id="wave1-g8-final",
        mode="final-evaluation",
        project_id="project-e00g6zvxpr00waz8t3y51k",
        image=IMAGE,
        created_at=signed_at,
        git_commit="a" * 40,
        experiment=Wave1ExperimentSpec(calibration_method="isotonic"),
        input=Wave1TabularProjectionInput(
            frozen_root=_artifact("manifests/frozen-root.json", "f" * 64, 10, "frozen_root"),
            projection=_artifact(
                "manifests/tabular-projection.json", "e" * 64, 10, "final_projection"
            ),
            dataset_lineage_receipt=_file_artifact(
                manifests / "c4-mlflow-dataset-release.json", package, "dataset_lineage"
            ),
            projection_artifact_root="projection-artifacts",
        ),
        result_uri=RESULT_URI,
        input_release_uri=FINAL_URI,
        candidate=_artifact("candidate/candidate.json", candidate_hash, 9, "candidate"),
        authorization=_file_artifact(
            authorization / "authorization.json", package, "authorization"
        ),
        authorization_signature=_file_artifact(
            authorization / "authorization.sig", package, "authorization_signature"
        ),
        authorization_public_key=_file_artifact(
            authorization / "authorization-public.pem", package, "authorization_public_key"
        ),
        mlflow_tracking_uri="http://10.4.0.54:5500",
    )
    (package / "request.json").write_bytes(request.canonical_bytes())
    injected = tuple(
        G8InjectedFile(
            local_name=path.relative_to(package).as_posix(),
            container_path=f"/job/g8/{path.relative_to(package).as_posix()}",
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in (
            package / "run_lightgbm_g8.py",
            package / "request.json",
            authorization / "authorization.json",
            authorization / "authorization.sig",
            authorization / "authorization-public.pem",
            manifests / "c4-mlflow-dataset-release.json",
        )
    )
    receipt = G8PreflightReceipt(
        created_at=request.created_at,
        tool_git_commit="b" * 40,
        campaign_id=request.campaign_id,
        run_id=request.run_id,
        candidate_hash=candidate_hash,
        authorization_receipt_sha256="c" * 64,
        trusted_authorization_public_key_sha256="a" * 64,
        final_input_uri=FINAL_URI,
        candidate_release_uri=CANDIDATE_URI,
        result_uri=RESULT_URI,
        request_sha256=request.canonical_hash(),
        image=IMAGE,
        injected_files=injected,
    )
    (package / "g8-preflight.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    inventory = inventory_directory(package, exclude_markers=True)
    write_checksum_file(package, inventory)
    (package / "SUCCESS").write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    return package, request


def _artifact(uri: str, sha256: str, size: int, logical_name: str) -> CloudArtifact:
    return CloudArtifact(logical_name=logical_name, uri=uri, sha256=sha256, size_bytes=size)


def _file_artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    return _artifact(path.relative_to(root).as_posix(), sha256_file(path), path.stat().st_size, logical_name)


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _set_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "WAVE1_ACTUAL_PROJECT_ID": "project-e00g6zvxpr00waz8t3y51k",
        "WAVE1_ACTUAL_IMAGE_REPOSITORY": IMAGE.rsplit("@sha256:", 1)[0],
        "WAVE1_ACTUAL_IMAGE_SHA256": IMAGE.rsplit("@sha256:", 1)[1],
        "WAVE1_ACTUAL_PLATFORM": "cpu-d3",
        "WAVE1_ACTUAL_PRESET": "4vcpu-16gb",
        "WAVE1_ACTUAL_DISK_SIZE_GIB": "100",
        "WAVE1_ACTUAL_TIMEOUT_SECONDS": "3600",
        "WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256": "a" * 64,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
