from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("lightgbm", reason="Wave 1 tests require the ml extra")

from app.ml.lightgbm.cloud_contracts import (  # noqa: E402
    APPROVED_FIXTURE_FEATURE_RELEASE_SHA256,
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExecutionContext,
    Wave1ExperimentSpec,
    Wave1FixtureInput,
)
from app.ml.lightgbm.cloud_runner import execute_wave1_request  # noqa: E402
from app.ml.lightgbm import cloud_runner, cloud_transport  # noqa: E402
from app.nebius import object_storage  # noqa: E402
from app.nebius.object_storage import (  # noqa: E402
    S3ObjectEvidence,
    download_s3_release,
    publish_local_result,
    publish_s3_result,
    verify_complete_result,
)
from scripts import lightgbm_wave1 as wave1_script  # noqa: E402
from scripts.lightgbm_wave1 import LOCAL_IMAGE, PROJECT_ID, local_e2e  # noqa: E402


SHA = "0" * 64


def _request(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "campaign_id": "wave1-test",
        "run_id": "wave1-test-development",
        "mode": "development",
        "project_id": PROJECT_ID,
        "image": LOCAL_IMAGE,
        "created_at": datetime(2026, 8, 16, tzinfo=UTC).isoformat(),
        "git_commit": "0" * 40,
        "input": Wave1FixtureInput(
            feature_release_sha256=APPROVED_FIXTURE_FEATURE_RELEASE_SHA256
        ).model_dump(mode="json"),
        "result_uri": Path("/tmp/wave1-test-result").as_uri(),
    }
    payload.update(updates)
    return payload


def test_request_forbids_unknown_fields_and_mutable_images() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        LightGbmCloudJobRequest.model_validate({**_request(), "surprise": True})
    with pytest.raises(ValidationError, match="image"):
        LightGbmCloudJobRequest.model_validate(_request(image="ghcr.io/acme/jobs:latest"))


def test_request_rejects_secret_serialization_and_development_test_access() -> None:
    with pytest.raises(ValidationError, match="secret-shaped"):
        LightGbmCloudJobRequest.model_validate(
            _request(mlflow_tracking_uri="https://user:password@example.test/mlflow")
        )
    with pytest.raises(ValidationError, match="final/test"):
        LightGbmCloudJobRequest.model_validate(
            _request(result_uri=Path("/tmp/test/result").as_uri())
        )
    with pytest.raises(ValidationError, match="exact approved"):
        LightGbmCloudJobRequest.model_validate(
            _request(
                result_uri=(
                    "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                    "wave1-test/development/a-different-run"
                )
            )
        )


def test_final_request_requires_all_authorization_artifacts() -> None:
    candidate = CloudArtifact(logical_name="candidate", uri="candidate.json", sha256=SHA, size_bytes=1)
    with pytest.raises(ValidationError, match="signed authorization"):
        LightGbmCloudJobRequest.model_validate(
            _request(mode="final-evaluation", run_id="wave1-test-final", candidate=candidate.model_dump())
        )


def test_artifact_paths_reject_escape() -> None:
    with pytest.raises(ValidationError, match="normalized relative"):
        CloudArtifact(logical_name="candidate", uri="../candidate.json", sha256=SHA, size_bytes=1)


def test_publish_is_atomic_rejects_partial_and_duplicate_run(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "artifact.txt").write_text("verified", encoding="utf-8")
    destination = tmp_path / "result"
    published = publish_local_result(staging, destination.as_uri())
    verify_complete_result(published)
    with pytest.raises(FileExistsError, match="already exists"):
        second = tmp_path / "second"
        second.mkdir()
        publish_local_result(second, destination.as_uri())
    (published / "SUCCESS").unlink()
    with pytest.raises(ValueError, match="partial"):
        verify_complete_result(published)


def test_local_fixture_lifecycle_is_independently_verifiable(tmp_path: Path) -> None:
    output = tmp_path / "wave1"
    local_e2e(output)
    assert (output / "LOCAL-G2-SUCCESS").read_text(encoding="utf-8") == "verified\n"
    exit_record = json.loads((output / "exit-record.json").read_text(encoding="utf-8"))
    assert exit_record["cloud_resources_created"] is False
    assert exit_record["local_gates"] == {
        "authorization": True,
        "checksums": True,
        "release": True,
        "schemas": True,
    }


def test_s3_download_lists_only_requested_prefix_and_verifies_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "source-staging"
    staging.mkdir()
    (staging / "request.json").write_text("{}\n", encoding="utf-8")
    package = publish_local_result(staging, (tmp_path / "source").as_uri())
    calls: list[tuple[str, ...]] = []

    def fake_aws_json(endpoint_url: str, *args: str) -> dict[str, object]:
        calls.append(args)
        if args[:2] == ("s3api", "list-objects-v2"):
            prefix = args[args.index("--prefix") + 1]
            files = [path for path in sorted(package.rglob("*")) if path.is_file()]
            if "--continuation-token" not in args:
                selected = files[:1]
                truncated = len(files) > 1
            else:
                assert args[args.index("--continuation-token") + 1] == "page-2"
                selected = files[1:]
                truncated = False
            return {
                "Contents": [
                    {"Key": prefix + path.relative_to(package).as_posix(), "Size": path.stat().st_size}
                    for path in selected
                ],
                "IsTruncated": truncated,
                **({"NextContinuationToken": "page-2"} if truncated else {}),
            }
        if args[:2] == ("s3api", "get-object"):
            key = args[args.index("--key") + 1]
            target = Path(args[-1])
            target.write_bytes((package / key.removeprefix("releases/rel1/staging/")).read_bytes())
            return {}
        raise AssertionError(f"unexpected S3 call: {args}")

    monkeypatch.setattr(object_storage, "_aws_json", fake_aws_json)
    downloaded = tmp_path / "downloaded"
    download_s3_release(
        "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
        downloaded,
        endpoint_url="https://storage.eu-north1.nebius.cloud",
    )

    list_calls = [call for call in calls if call[:2] == ("s3api", "list-objects-v2")]
    assert len(list_calls) == 2
    list_call = list_calls[0]
    assert list_call[list_call.index("--prefix") + 1] == "releases/rel1/staging/"
    assert not any("head-bucket" in call for call in calls)
    verify_complete_result(downloaded)


def test_repeat_comparison_uses_stable_reproducibility_hash(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    local_e2e(first)
    local_e2e(second)

    comparison = tmp_path / "comparison.json"
    wave1_script.compare_results(
        [first / "development", second / "development"], comparison
    )
    payload = json.loads(comparison.read_text(encoding="utf-8"))

    assert payload["reproducible"] is True
    assert payload["runs"][0]["reproducibility_hash"] == payload["runs"][1][
        "reproducibility_hash"
    ]


def test_final_rejects_untrusted_key_and_tampered_candidate_artifact(tmp_path: Path) -> None:
    output = tmp_path / "wave1"
    local_e2e(output)
    request_path = output / "inputs" / "final-request.json"
    final_inputs = output / "final-inputs"

    with pytest.raises(ValueError, match="trusted hash"):
        execute_wave1_request(
            request_path,
            input_root=final_inputs,
            trusted_authorization_public_key_sha256="0" * 64,
        )

    training_manifest = final_inputs / "candidate" / "artifacts" / "training" / "training-run.json"
    training_manifest.write_text("{}\n", encoding="utf-8")
    public_key = final_inputs / "authorization" / "authorization-public.pem"
    with pytest.raises(ValueError, match="integrity failed"):
        execute_wave1_request(
            request_path,
            input_root=final_inputs,
            trusted_authorization_public_key_sha256=wave1_script.sha256_file(public_key),
        )


def test_experiment_config_controls_training_and_calibration(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    result = tmp_path / "result"
    experiment = Wave1ExperimentSpec(
        hyperparameters={
            "num_boost_round": 7,
            "learning_rate": 0.05,
            "num_leaves": 4,
            "min_data_in_leaf": 2,
        },
        early_stopping_rounds=3,
        calibration_method="raw",
        excluded_features=("spread",),
    )
    request = wave1_script._request(
        campaign_id="wave1-experiment-test",
        run_id="wave1-experiment-development",
        mode="development",
        created_at=datetime.now(UTC),
        result=result,
        experiment=experiment,
    )
    request_path = inputs / "request.json"
    request_path.write_bytes(request.canonical_bytes())

    execute_wave1_request(request_path, input_root=inputs)

    training = json.loads(
        (result / "artifacts" / "training" / "training-run.json").read_text(encoding="utf-8")
    )
    calibration = json.loads(
        (result / "artifacts" / "calibration" / "calibration-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert training["hyperparameters"]["num_boost_round"] == 7
    assert training["early_stopping"]["stopping_rounds"] == 3
    assert "spread" not in training["ordered_feature_columns"]
    assert calibration["parameters"]["method"] == "raw"


def test_development_run_binds_mlflow_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    result = tmp_path / "result"
    request = wave1_script._request(
        campaign_id="wave1-mlflow-test",
        run_id="wave1-mlflow-development",
        mode="development",
        created_at=datetime.now(UTC),
        result=result,
    ).model_copy(update={"mlflow_tracking_uri": "http://10.4.0.54:5500"})
    request_path = inputs / "request.json"
    request_path.write_bytes(request.canonical_bytes())
    monkeypatch.setattr(cloud_runner, "log_development_run", lambda **_kwargs: "mlflow-run-1")

    execute_wave1_request(request_path, input_root=inputs)
    run = json.loads((result / "cloud-run.json").read_text(encoding="utf-8"))

    assert run["mlflow_run_id"] == "mlflow-run-1"


def test_cloud_collection_requires_job_identity_context_and_cost(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    result = tmp_path / "result"
    request = LightGbmCloudJobRequest.model_validate(
        _request(
            result_uri=(
                "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                "wave1-test/development/wave1-test-development"
            )
        )
    )
    request_path = inputs / "request.json"
    request_path.write_bytes(request.canonical_bytes())
    context = Wave1ExecutionContext(
        project_id=PROJECT_ID,
        image=LOCAL_IMAGE,
        platform="cpu-d3",
        preset="4vcpu-16gb",
        disk_size_gib=100,
        timeout_seconds=3600,
    )
    execute_wave1_request(
        request_path,
        input_root=inputs,
        local_result_root=result,
        execution_context=context,
    )

    with pytest.raises(ValueError, match="Job ID and actual Job context"):
        wave1_script.collect_result(result, tmp_path / "missing.json")
    with pytest.raises(ValueError, match="does not match"):
        wave1_script.collect_result(
            result,
            tmp_path / "wrong.json",
            nebius_job_id="job-test",
            actual_project_id=PROJECT_ID,
            actual_image=LOCAL_IMAGE,
            actual_platform="cpu-d3",
            actual_preset="wrong-preset",
            actual_disk_size_gib=100,
            actual_timeout_seconds=3600,
            estimated_cost_usd=0.01,
        )
    collection = tmp_path / "collection.json"
    wave1_script.collect_result(
        result,
        collection,
        nebius_job_id="job-test",
        actual_project_id=PROJECT_ID,
        actual_image=LOCAL_IMAGE,
        actual_platform="cpu-d3",
        actual_preset="4vcpu-16gb",
        actual_disk_size_gib=100,
        actual_timeout_seconds=3600,
        estimated_cost_usd=0.01,
    )
    payload = json.loads(collection.read_text(encoding="utf-8"))
    assert payload["nebius_job_id"] == "job-test"
    assert payload["estimated_cost_usd"] == 0.01


def test_s3_result_publication_writes_success_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "result-staging"
    staging.mkdir()
    (staging / "metrics.json").write_text("{}\n", encoding="utf-8")
    result = publish_local_result(staging, (tmp_path / "result").as_uri())
    uploaded: list[str] = []

    monkeypatch.setattr(object_storage, "_list_s3_keys", lambda *args, **kwargs: ())

    def fake_put(
        source: Path, *, bucket: str, key: str, expected_sha256: str, endpoint_url: str
    ) -> S3ObjectEvidence:
        uploaded.append(key)
        return S3ObjectEvidence(
            key=key,
            sha256=expected_sha256,
            size_bytes=source.stat().st_size,
            etag="test",
        )

    monkeypatch.setattr(object_storage, "_put_and_verify_s3_object", fake_put)
    publish_s3_result(
        result,
        "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/c1/development/r1",
        endpoint_url="https://storage.eu-north1.nebius.cloud",
    )

    assert uploaded[-1].endswith("/SUCCESS")
    assert uploaded.count(uploaded[-1]) == 1


def test_cloud_transport_stages_executes_and_publishes_without_mounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mysterybox-injected-access-id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mysterybox-injected-secret-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("WAVE1_ACTUAL_PROJECT_ID", PROJECT_ID)
    monkeypatch.setenv("WAVE1_ACTUAL_IMAGE", LOCAL_IMAGE)
    monkeypatch.setenv("WAVE1_ACTUAL_PLATFORM", "cpu-d3")
    monkeypatch.setenv("WAVE1_ACTUAL_PRESET", "4vcpu-16gb")
    monkeypatch.setenv("WAVE1_ACTUAL_DISK_SIZE_GIB", "100")
    monkeypatch.setenv("WAVE1_ACTUAL_TIMEOUT_SECONDS", "3600")
    request = LightGbmCloudJobRequest.model_validate(
        _request(
            result_uri=(
                "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                "wave1-test/development/wave1-test-development"
            ),
            mlflow_tracking_uri="http://10.4.0.54:5500",
        )
    )
    input_staging = tmp_path / "input-staging"
    input_staging.mkdir()
    (input_staging / "request.json").write_bytes(request.canonical_bytes())
    input_package = publish_local_result(input_staging, (tmp_path / "input-package").as_uri())
    published: dict[str, object] = {}

    def fake_download(source: str, destination: Path, **kwargs: object) -> object:
        shutil.copytree(input_package, destination)
        return verify_complete_result(destination)

    def fake_execute(
        request_path: Path,
        *,
        input_root: Path,
        local_result_root: Path | None = None,
        **kwargs: object,
    ) -> Path:
        assert local_result_root is not None
        assert LightGbmCloudJobRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        ).canonical_hash() == request.canonical_hash()
        staging = tmp_path / "execution-staging"
        staging.mkdir()
        (staging / "metrics.json").write_text("{}\n", encoding="utf-8")
        return publish_local_result(staging, local_result_root.as_uri())

    def fake_publish(
        source: Path, destination: str, **kwargs: object
    ) -> tuple[S3ObjectEvidence, ...]:
        verify_complete_result(source)
        published.update(destination=destination, source=source)
        return ()

    monkeypatch.setattr(cloud_transport, "download_s3_release", fake_download)
    monkeypatch.setattr(cloud_transport, "execute_wave1_request", fake_execute)
    monkeypatch.setattr(cloud_transport, "publish_s3_result", fake_publish)

    result_uri = cloud_transport.execute_wave1_s3(
        "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
        work_root=tmp_path / "work",
    )

    assert result_uri == request.result_uri
    assert published["destination"] == request.result_uri


def test_cloud_transport_rejects_unapproved_credential_endpoint(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="approved eu-north1"):
        cloud_transport.execute_wave1_s3(
            "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
            work_root=tmp_path / "work",
            endpoint_url="https://unapproved.example.test",
        )


def test_cloud_transport_requires_injected_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MysteryBox-injected"):
        cloud_transport.execute_wave1_s3(
            "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
            work_root=tmp_path / "work",
        )


def test_fixture_staging_emits_cloud_result_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_publish(
        source: Path, destination: str, **kwargs: object
    ) -> tuple[S3ObjectEvidence, ...]:
        verify_complete_result(source)
        request = LightGbmCloudJobRequest.model_validate_json(
            (source / "request.json").read_text(encoding="utf-8")
        )
        captured.update(destination=destination, result_uri=request.result_uri)
        return ()

    monkeypatch.delenv("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr(wave1_script, "publish_s3_input_release", fake_publish)
    monkeypatch.setattr(wave1_script, "_git_commit", lambda: "0" * 40)
    wave1_script.stage_fixture(
        "release-test",
        "run-test",
        LOCAL_IMAGE,
        "https://storage.eu-north1.nebius.cloud",
        tmp_path / "evidence.json",
        mlflow_tracking_uri="http://10.4.0.54:5500",
    )

    assert captured == {
        "destination": "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release-test/staging",
        "result_uri": (
            "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
            "wave1-research-20260816/development/run-test"
        ),
    }


def test_submitter_dry_run_uses_secret_references_only(tmp_path: Path) -> None:
    input_uri = "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release-test/staging"
    request = LightGbmCloudJobRequest.model_validate(
        _request(
            result_uri=(
                "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                "wave1-test/development/wave1-test-development"
            ),
            mlflow_tracking_uri="http://10.4.0.54:5500",
        )
    )
    evidence_path = tmp_path / "request-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "destination": input_uri,
                "request_sha256": request.canonical_hash(),
                "request": request.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "NEBIUS_SUBNET_ID": "subnet-test",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID": "mysterybox-access-ref",
        "NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID": "mysterybox-secret-ref",
        "NEBIUS_MLFLOW_USERNAME_SECRET_ID": "mysterybox-mlflow-user-ref",
        "NEBIUS_MLFLOW_PASSWORD_SECRET_ID": "mysterybox-mlflow-password-ref",
        "NEBIUS_OBJECT_STORAGE_ENDPOINT_URL": "https://storage.eu-north1.nebius.cloud",
        "NEBIUS_WAVE1_INPUT_URI": input_uri,
        "NEBIUS_WAVE1_REQUEST_EVIDENCE": str(evidence_path),
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
            str(Path(__file__).resolve().parents[2] / "scripts" / "submit_nebius_job.py"),
            "--workload",
            "lightgbm-wave1",
            "--image",
            LOCAL_IMAGE,
            "--dry-run",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    )
    command = json.loads(completed.stdout)["command"]
    joined = " ".join(command)
    assert "--env-secret" in command
    assert "AWS_ACCESS_KEY_ID=mysterybox-access-ref" in command
    assert "AWS_SECRET_ACCESS_KEY=mysterybox-secret-ref" in command
    assert "MLFLOW_TRACKING_USERNAME=mysterybox-mlflow-user-ref" in command
    assert "MLFLOW_TRACKING_PASSWORD=mysterybox-mlflow-password-ref" in command
    assert "run-s3" in joined
    assert "--input-uri" in joined
    assert "--volume" not in command
    assert command[command.index("--platform") + 1] == "cpu-d3"
    assert command[command.index("--preset") + 1] == "4vcpu-16gb"
    assert command[command.index("--disk-size") + 1] == "100Gi"
    assert command[command.index("--timeout") + 1] == "1h"
    assert command[command.index("--parent-id") + 1] == PROJECT_ID
    assert not any(value.startswith("AWS_ACCESS_KEY_ID=AKIA") for value in command)

    script = str(Path(__file__).resolve().parents[2] / "scripts" / "submit_nebius_job.py")
    for override in (("--platform", "gpu-h100"), ("--timeout", "168h")):
        rejected = subprocess.run(
            [
                sys.executable,
                script,
                "--workload",
                "lightgbm-wave1",
                "--image",
                LOCAL_IMAGE,
                *override,
                "--dry-run",
            ],
            check=False,
            text=True,
            capture_output=True,
            env=environment,
        )
        assert rejected.returncode != 0
        assert "requires cpu-d3" in rejected.stderr


def test_wave1_submitter_rejects_filesystem_mounts(tmp_path: Path) -> None:
    input_uri = "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging"
    request = LightGbmCloudJobRequest.model_validate(
        _request(
            result_uri=(
                "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                "wave1-test/development/wave1-test-development"
            ),
            mlflow_tracking_uri="http://10.4.0.54:5500",
        )
    )
    evidence_path = tmp_path / "request-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "destination": input_uri,
                "request_sha256": request.canonical_hash(),
                "request": request.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "NEBIUS_SUBNET_ID": "subnet-test",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID": "mysterybox-access-ref",
        "NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID": "mysterybox-secret-ref",
        "NEBIUS_MLFLOW_USERNAME_SECRET_ID": "mysterybox-mlflow-user-ref",
        "NEBIUS_MLFLOW_PASSWORD_SECRET_ID": "mysterybox-mlflow-password-ref",
        "NEBIUS_OBJECT_STORAGE_ENDPOINT_URL": "https://storage.eu-north1.nebius.cloud",
        "NEBIUS_WAVE1_INPUT_URI": input_uri,
        "NEBIUS_WAVE1_REQUEST_EVIDENCE": str(evidence_path),
        "NEBIUS_VOLUME": "s3://forbidden:/job/inputs:ro:secret",
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "submit_nebius_job.py"),
            "--workload",
            "lightgbm-wave1",
            "--image",
            LOCAL_IMAGE,
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=environment,
    )
    assert completed.returncode != 0
    assert "NEBIUS_VOLUME is forbidden" in completed.stderr
