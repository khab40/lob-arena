from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.market_data.projections import C4MlflowDatasetReleaseReceipt
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import (
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
    Wave1TabularProjectionInput,
)
from app.nebius.object_storage import inventory_directory, verify_complete_result, write_checksum_file

if TYPE_CHECKING:
    from app.ml.lightgbm.g7_candidate import G7AuthorizationReceipt, G7CandidateFreeze


PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
FINAL_BUCKET = "aimada-wave1-final-e00g6zvxpr00"
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
APPROVED_MLFLOW_URI = "http://10.4.0.54:5500"
FINAL_RELEASE_PATTERN = re.compile(
    rf"s3://{FINAL_BUCKET}/releases/[a-z0-9][a-z0-9-]{{2,62}}/staging"
)
DEVELOPMENT_RESULT_PATTERN = re.compile(
    rf"s3://{RESULTS_BUCKET}/campaigns/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}/development/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _FrozenCandidateMetadata(_StrictModel):
    schema_version: Literal["lightgbm_wave1_candidate_v1"] = (
        "lightgbm_wave1_candidate_v1"
    )
    campaign_id: str
    experiment: Wave1ExperimentSpec
    reproducibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_manifest: CloudArtifact
    calibration_manifest: CloudArtifact
    validation_metrics: CloudArtifact
    feature_importance: CloudArtifact
    feature_schema: CloudArtifact
    reliability_bins: CloudArtifact
    reliability_diagram: CloudArtifact
    test_fold_accessed: bool = False


class G8InjectedFile(_StrictModel):
    local_name: str = Field(min_length=1)
    container_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1, le=64 * 1024)

    @model_validator(mode="after")
    def validate_paths(self) -> "G8InjectedFile":
        local = PurePosixPath(self.local_name)
        container = PurePosixPath(self.container_path)
        if local.is_absolute() or any(part in {"", ".", ".."} for part in local.parts):
            raise ValueError("G8 injected local name must be normalized and relative")
        if container != PurePosixPath("/job/g8") / local:
            raise ValueError("G8 injected container path must exactly mirror its local name")
        return self


class G8PreflightReceipt(_StrictModel):
    schema_version: Literal["lightgbm_wave1_g8_preflight_v1"] = (
        "lightgbm_wave1_g8_preflight_v1"
    )
    status: Literal["ready_for_exactly_one_submission"] = "ready_for_exactly_one_submission"
    created_at: AwareDatetime
    tool_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    campaign_id: str
    run_id: str
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_authorization_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_input_uri: str
    candidate_release_uri: str
    result_uri: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image: str
    mlflow_tracking_uri: Literal[APPROVED_MLFLOW_URI] = APPROVED_MLFLOW_URI
    mlflow_experiment: Literal["lob-arena/governed-evaluation"] = (
        "lob-arena/governed-evaluation"
    )
    development_jobs_consumed: Literal[20] = 20
    final_jobs_submitted_before: Literal[0] = 0
    test_fold_accessed: Literal[False] = False
    cloud_resources_mutated: Literal[False] = False
    injected_files: tuple[G8InjectedFile, ...]

    @model_validator(mode="after")
    def validate_boundaries(self) -> "G8PreflightReceipt":
        if FINAL_RELEASE_PATTERN.fullmatch(self.final_input_uri) is None:
            raise ValueError("G8 final input URI is outside the approved release boundary")
        if DEVELOPMENT_RESULT_PATTERN.fullmatch(self.candidate_release_uri) is None:
            raise ValueError("G8 candidate URI is outside the selected development boundary")
        expected = (
            f"s3://{RESULTS_BUCKET}/campaigns/{self.campaign_id}/final/{self.run_id}"
        )
        if self.result_uri != expected:
            raise ValueError("G8 result URI does not match its exact campaign and run")
        paths = [item.container_path for item in self.injected_files]
        if len(paths) != len(set(paths)):
            raise ValueError("G8 injected container paths must be unique")
        return self


def prepare_g8_preflight(
    *,
    freeze_root: Path,
    authorization_root: Path,
    final_publication_evidence: Path,
    c4_mlflow_evidence: Path,
    runner: Path,
    run_id: str,
    output: Path,
    tool_git_commit: str,
    created_at: datetime | None = None,
) -> G8PreflightReceipt:
    from app.ml.lightgbm.g7_candidate import (
        load_g7_authorization,
        load_g7_candidate_freeze,
    )

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", run_id) is None:
        raise ValueError("G8 run ID must be canonical")
    if output.exists():
        raise FileExistsError(f"G8 preflight output already exists: {output}")
    prepared_at = created_at or datetime.now(UTC)
    freeze = load_g7_candidate_freeze(freeze_root)
    authorization = load_g7_authorization(authorization_root)
    _verify_authorization_binding(freeze, authorization, freeze_root)
    publication = _load_final_publication(final_publication_evidence)
    lineage = C4MlflowDatasetReleaseReceipt.model_validate_json(
        c4_mlflow_evidence.read_text(encoding="utf-8")
    )
    final_uri = _required_string(publication, "destination").rstrip("/")
    if FINAL_RELEASE_PATTERN.fullmatch(final_uri) is None:
        raise ValueError("C4 final publication is outside the approved final release boundary")
    release_id = _required_string(publication, "release_id")
    if lineage.release_id != release_id or lineage.raw_rows_uploaded_to_mlflow:
        raise ValueError("G8 C4 lineage receipt does not bind the sealed final release")
    objects = _publication_objects(publication)
    frozen_root_ref = _remote_artifact(
        objects, final_uri, "manifests/frozen-root.json", "frozen_root"
    )
    projection_ref = _remote_artifact(
        objects, final_uri, "manifests/tabular-projection.json", "final_projection"
    )
    if (
        frozen_root_ref.sha256 != lineage.root_file_sha256
        or projection_ref.sha256 != lineage.tabular_final_sha256
        or _required_string(publication, "frozen_root_identity_sha256")
        != lineage.root_identity_sha256
        or _required_string(publication, "tabular_projection_sha256")
        != lineage.tabular_final_sha256
    ):
        raise ValueError("G8 final publication hashes do not match the C4 MLflow receipt")

    candidate_path = freeze_root / freeze.candidate.uri
    candidate = _FrozenCandidateMetadata.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    candidate_request = LightGbmCloudJobRequest.model_validate_json(
        (freeze_root / "candidate" / "request.json").read_text(encoding="utf-8")
    )
    candidate_release_uri = candidate_request.result_uri.rstrip("/")
    if DEVELOPMENT_RESULT_PATTERN.fullmatch(candidate_release_uri) is None:
        raise ValueError("G8 frozen candidate has no approved immutable cloud source")
    if (
        candidate.campaign_id != freeze.campaign_id
        or candidate.experiment.canonical_hash() != freeze.experiment_hash
        or candidate_request.image != freeze.image
    ):
        raise ValueError("G8 candidate package diverges from its G7 freeze")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="g8-preflight-", dir=output.parent) as value:
        staging = Path(value)
        shutil.copyfile(runner, staging / "run_lightgbm_g8.py")
        authorization_dir = staging / "authorization"
        authorization_dir.mkdir()
        for name in ("authorization.json", "authorization.sig", "authorization-public.pem"):
            shutil.copyfile(authorization_root / name, authorization_dir / name)
        manifests = staging / "manifests"
        manifests.mkdir()
        shutil.copyfile(c4_mlflow_evidence, manifests / "c4-mlflow-dataset-release.json")

        request = LightGbmCloudJobRequest(
            campaign_id=freeze.campaign_id,
            run_id=run_id,
            mode="final-evaluation",
            project_id=PROJECT_ID,
            image=freeze.image,
            created_at=prepared_at,
            git_commit=candidate_request.git_commit,
            random_seed=candidate_request.random_seed,
            experiment=candidate.experiment,
            input=Wave1TabularProjectionInput(
                frozen_root=frozen_root_ref,
                projection=projection_ref,
                dataset_lineage_receipt=_local_artifact(
                    manifests / "c4-mlflow-dataset-release.json",
                    staging,
                    "c4_mlflow_dataset_release",
                ),
                projection_artifact_root="projection-artifacts",
            ),
            result_uri=(
                f"s3://{RESULTS_BUCKET}/campaigns/{freeze.campaign_id}/final/{run_id}"
            ),
            input_release_uri=final_uri,
            candidate=CloudArtifact(
                logical_name="candidate",
                uri="candidate/candidate.json",
                sha256=freeze.candidate_hash,
                size_bytes=freeze.candidate.size_bytes,
            ),
            authorization=_local_artifact(
                authorization_dir / "authorization.json", staging, "authorization"
            ),
            authorization_signature=_local_artifact(
                authorization_dir / "authorization.sig", staging, "authorization_signature"
            ),
            authorization_public_key=_local_artifact(
                authorization_dir / "authorization-public.pem",
                staging,
                "authorization_public_key",
            ),
            mlflow_tracking_uri=APPROVED_MLFLOW_URI,
        )
        (staging / "request.json").write_bytes(request.canonical_bytes())
        injected = tuple(
            _injected_file(path, staging)
            for path in (
                staging / "run_lightgbm_g8.py",
                staging / "request.json",
                authorization_dir / "authorization.json",
                authorization_dir / "authorization.sig",
                authorization_dir / "authorization-public.pem",
                manifests / "c4-mlflow-dataset-release.json",
            )
        )
        receipt = G8PreflightReceipt(
            created_at=prepared_at,
            tool_git_commit=tool_git_commit,
            campaign_id=freeze.campaign_id,
            run_id=run_id,
            candidate_hash=freeze.candidate_hash,
            authorization_receipt_sha256=sha256_file(
                authorization_root / "g7-authorization.json"
            ),
            trusted_authorization_public_key_sha256=(
                authorization.trusted_authorization_public_key_sha256
            ),
            final_input_uri=final_uri,
            candidate_release_uri=candidate_release_uri,
            result_uri=request.result_uri,
            request_sha256=request.canonical_hash(),
            image=freeze.image,
            injected_files=injected,
        )
        (staging / "g8-preflight.json").write_text(
            receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        inventory = inventory_directory(staging, exclude_markers=True)
        write_checksum_file(staging, inventory)
        (staging / "SUCCESS").write_text(
            inventory.model_dump_json(indent=2), encoding="utf-8"
        )
        shutil.move(str(staging), output)
    verify_g8_preflight(output)
    return receipt


def verify_g8_preflight(root: Path) -> G8PreflightReceipt:
    verify_complete_result(root)
    receipt = G8PreflightReceipt.model_validate_json(
        (root / "g8-preflight.json").read_text(encoding="utf-8")
    )
    request = LightGbmCloudJobRequest.model_validate_json(
        (root / "request.json").read_text(encoding="utf-8")
    )
    if request.canonical_hash() != receipt.request_sha256:
        raise ValueError("G8 request changed after preflight")
    for item in receipt.injected_files:
        path = root / item.local_name
        if (
            not path.is_file()
            or path.stat().st_size != item.size_bytes
            or sha256_file(path) != item.sha256
        ):
            raise ValueError(f"G8 injected file changed after preflight: {item.local_name}")
    if (
        request.mode != "final-evaluation"
        or request.input_release_uri != receipt.final_input_uri
        or request.result_uri != receipt.result_uri
        or request.image != receipt.image
        or request.candidate is None
        or request.candidate.sha256 != receipt.candidate_hash
    ):
        raise ValueError("G8 request no longer matches its preflight receipt")
    return receipt


def _verify_authorization_binding(
    freeze: G7CandidateFreeze,
    authorization: G7AuthorizationReceipt,
    freeze_root: Path,
) -> None:
    if (
        authorization.candidate_hash != freeze.candidate_hash
        or authorization.freeze_receipt_sha256
        != sha256_file(freeze_root / "g7-candidate-freeze.json")
        or not authorization.signature_verified
        or not authorization.final_identity_available
        or freeze.test_fold_accessed
    ):
        raise ValueError("G8 requires the verified G7 authorization and an untouched test fold")


def _load_final_publication(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "market_data_wave1_projection_publication_v1"
        or payload.get("scope") != "final"
        or payload.get("success_published_last") is not True
    ):
        raise ValueError("G8 requires the completed C4 final publication receipt")
    return payload


def _publication_objects(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    objects = payload.get("objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError("C4 final publication has no object inventory")
    return tuple(item for item in objects if isinstance(item, dict))


def _remote_artifact(
    objects: tuple[dict[str, Any], ...],
    release_uri: str,
    relative: str,
    logical_name: str,
) -> CloudArtifact:
    prefix = release_uri.split("/", maxsplit=3)[-1].rstrip("/") + "/"
    matches = [item for item in objects if item.get("key") == prefix + relative]
    if len(matches) != 1:
        raise ValueError(f"C4 final publication omits exact object: {relative}")
    item = matches[0]
    return CloudArtifact(
        logical_name=logical_name,
        uri=relative,
        sha256=_required_hash(item, "sha256"),
        size_bytes=_required_int(item, "size_bytes"),
    )


def _local_artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    return CloudArtifact(
        logical_name=logical_name,
        uri=path.relative_to(root).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _injected_file(path: Path, root: Path) -> G8InjectedFile:
    relative = path.relative_to(root).as_posix()
    return G8InjectedFile(
        local_name=relative,
        container_path=f"/job/g8/{relative}",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _required_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"G8 evidence field is missing: {name}")
    return value


def _required_hash(payload: dict[str, Any], name: str) -> str:
    value = _required_string(payload, name)
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"G8 evidence field is not SHA-256: {name}")
    return value


def _required_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"G8 evidence field is not a non-negative integer: {name}")
    return value


def git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()
