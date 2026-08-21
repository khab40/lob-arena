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
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1FixtureInput,
)
from app.ml.lightgbm import cloud_transport  # noqa: E402
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
        "input": Wave1FixtureInput(feature_release_sha256=SHA).model_dump(mode="json"),
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
            return {
                "Contents": [
                    {"Key": prefix + path.relative_to(package).as_posix(), "Size": path.stat().st_size}
                    for path in sorted(package.rglob("*"))
                    if path.is_file()
                ]
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

    list_call = calls[0]
    assert list_call[list_call.index("--prefix") + 1] == "releases/rel1/staging/"
    assert not any("head-bucket" in call for call in calls)
    verify_complete_result(downloaded)


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
    request = LightGbmCloudJobRequest.model_validate(
        _request(
            result_uri=(
                "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                "wave1-test/development/wave1-test-development"
            )
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
        request_path: Path, *, input_root: Path, local_result_root: Path | None = None
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
    )

    assert captured == {
        "destination": "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release-test/staging",
        "result_uri": (
            "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
            "wave1-research-20260816/development/run-test"
        ),
    }


def test_submitter_dry_run_uses_secret_references_only() -> None:
    environment = {
        **os.environ,
        "NEBIUS_SUBNET_ID": "subnet-test",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID": "mysterybox-access-ref",
        "NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID": "mysterybox-secret-ref",
        "NEBIUS_OBJECT_STORAGE_ENDPOINT_URL": "https://storage.eu-north1.nebius.cloud",
        "NEBIUS_WAVE1_INPUT_URI": (
            "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release-test/staging"
        ),
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
    assert "run-s3" in joined
    assert "--input-uri" in joined
    assert "--volume" not in command
    assert not any(value.startswith("AWS_ACCESS_KEY_ID=AKIA") for value in command)


def test_wave1_submitter_rejects_filesystem_mounts() -> None:
    environment = {
        **os.environ,
        "NEBIUS_SUBNET_ID": "subnet-test",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID": "mysterybox-access-ref",
        "NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID": "mysterybox-secret-ref",
        "NEBIUS_OBJECT_STORAGE_ENDPOINT_URL": "https://storage.eu-north1.nebius.cloud",
        "NEBIUS_WAVE1_INPUT_URI": "s3://aimada-wave1-dev-e00g6zvxpr00/releases/rel1/staging",
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
