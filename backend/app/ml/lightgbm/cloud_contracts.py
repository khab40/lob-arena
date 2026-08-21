from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.contracts import GIT_COMMIT_PATTERN, IDENTIFIER_PATTERN, SHA256_PATTERN


IMMUTABLE_IMAGE_PATTERN = r"^[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$"
SENSITIVE_NAME = re.compile(
    r"(?i)(access.?key|api.?key|credential|password|private.?key|secret|session.?token|token)"
)
Wave1Mode = Literal["preflight", "development", "final-evaluation", "verify"]
RunStatus = Literal["succeeded", "failed", "verified"]


class _StrictCanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _relative_path(value: str, *, label: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise ValueError(f"{label} must be a normalized relative POSIX path")
    return value


class CloudArtifact(_StrictCanonicalModel):
    logical_name: str = Field(pattern=IDENTIFIER_PATTERN)
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_uri(self) -> "CloudArtifact":
        _relative_path(self.uri, label="artifact URI")
        return self


class Wave1ResourceRequest(_StrictCanonicalModel):
    platform: Literal["cpu-d3"] = "cpu-d3"
    preset: Literal["4vcpu-16gb"] = "4vcpu-16gb"
    cpu_count: Literal[4] = 4
    memory_gib: Literal[16] = 16
    timeout_seconds: int = Field(default=3600, ge=60, le=3600)
    gpu_count: Literal[0] = 0


class Wave1FixtureInput(_StrictCanonicalModel):
    kind: Literal["approved-research-fixture"] = "approved-research-fixture"
    fixture_version: Literal["lightgbm-wave1-fixture-v1"] = "lightgbm-wave1-fixture-v1"
    feature_release_sha256: str = Field(pattern=SHA256_PATTERN)


class Wave1GovernedInput(_StrictCanonicalModel):
    kind: Literal["governed-feature-release"] = "governed-feature-release"
    protocol: CloudArtifact
    corpus: CloudArtifact
    corpus_validation: CloudArtifact
    split: CloudArtifact
    feature_config: CloudArtifact
    feature_release: CloudArtifact
    feature_artifact_root: str
    corpus_artifact_root: str

    @model_validator(mode="after")
    def validate_roots(self) -> "Wave1GovernedInput":
        _relative_path(self.feature_artifact_root, label="feature artifact root")
        _relative_path(self.corpus_artifact_root, label="corpus artifact root")
        return self


class Wave1FinalAuthorization(_StrictCanonicalModel):
    schema_version: Literal["lightgbm_wave1_final_authorization_v1"] = (
        "lightgbm_wave1_final_authorization_v1"
    )
    campaign_id: str = Field(pattern=IDENTIFIER_PATTERN)
    candidate_hash: str = Field(pattern=SHA256_PATTERN)
    signer: Literal["Alexey Khabalov — Wave 1 Release Approver"]
    signed_at: AwareDatetime
    statement: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_statement(self) -> "Wave1FinalAuthorization":
        expected = f"APPROVE WAVE1 FINAL TEST {self.candidate_hash} {self.signed_at.isoformat()}"
        if self.statement != expected:
            raise ValueError("final authorization statement is not canonical")
        return self


class LightGbmCloudJobRequest(_StrictCanonicalModel):
    schema_version: Literal["lightgbm_cloud_job_v1"] = "lightgbm_cloud_job_v1"
    campaign_id: str = Field(pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    mode: Wave1Mode
    project_id: Literal["project-e00g6zvxpr00waz8t3y51k"]
    region: Literal["eu-north1"] = "eu-north1"
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    created_at: AwareDatetime
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    random_seed: int = Field(default=42, ge=0)
    input: Wave1FixtureInput | Wave1GovernedInput = Field(discriminator="kind")
    resource: Wave1ResourceRequest = Field(default_factory=Wave1ResourceRequest)
    result_uri: str = Field(min_length=1)
    candidate: CloudArtifact | None = None
    authorization: CloudArtifact | None = None
    authorization_signature: CloudArtifact | None = None
    authorization_public_key: CloudArtifact | None = None
    mlflow_tracking_uri: str | None = None

    @model_validator(mode="after")
    def validate_governance(self) -> "LightGbmCloudJobRequest":
        if self.result_uri.startswith("s3://"):
            lane = "final" if self.mode == "final-evaluation" else "development"
            expected = (
                "s3://aimada-wave1-results-e00g6zvxpr00/"
                f"campaigns/{self.campaign_id}/{lane}/{self.run_id}"
            )
            if self.result_uri.rstrip("/") != expected:
                raise ValueError("result URI must match the exact approved campaign/mode/run prefix")
        elif not self.result_uri.startswith("file://"):
            raise ValueError("result URI must use s3:// or file://")
        final_refs = (
            self.candidate,
            self.authorization,
            self.authorization_signature,
            self.authorization_public_key,
        )
        if self.mode == "final-evaluation" and any(item is None for item in final_refs):
            raise ValueError("final evaluation requires candidate and signed authorization artifacts")
        if self.mode != "final-evaluation" and any(item is not None for item in final_refs):
            raise ValueError("only final evaluation may reference candidate or authorization artifacts")
        if self.mode == "development":
            serialized = self.canonical_json_values()
            if any(_is_final_test_reference(value) for value in serialized):
                raise ValueError("development requests must not reference final/test inputs")
        _reject_secrets(self.model_dump(mode="json"))
        return self

    def canonical_json_values(self) -> tuple[str, ...]:
        values: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    visit(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)
            elif isinstance(value, str):
                values.append(value)

        visit(self.model_dump(mode="json"))
        return tuple(values)


class Wave1ResourceEvidence(_StrictCanonicalModel):
    platform: Literal["cpu-d3"] = "cpu-d3"
    preset: Literal["4vcpu-16gb"] = "4vcpu-16gb"
    cpu_count: Literal[4] = 4
    memory_gib: Literal[16] = 16
    gpu_count: Literal[0] = 0
    wall_seconds: float = Field(ge=0, allow_inf_nan=False)
    cpu_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_rss_bytes: int = Field(ge=0)
    processed_rows: int = Field(ge=0)
    rows_per_second: float = Field(ge=0, allow_inf_nan=False)


class LightGbmCloudRun(_StrictCanonicalModel):
    schema_version: Literal["lightgbm_cloud_run_v1"] = "lightgbm_cloud_run_v1"
    campaign_id: str = Field(pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    mode: Wave1Mode
    status: RunStatus
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    resource: Wave1ResourceEvidence
    outputs: tuple[CloudArtifact, ...]
    candidate_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    mlflow_run_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    error_type: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)

    @model_validator(mode="after")
    def validate_status(self) -> "LightGbmCloudRun":
        if self.completed_at < self.started_at:
            raise ValueError("cloud run completion precedes start")
        if self.status == "failed" and self.error_type is None:
            raise ValueError("failed cloud run requires a bounded error type")
        if self.status != "failed" and self.error_type is not None:
            raise ValueError("successful cloud run must not contain an error")
        _reject_secrets(self.model_dump(mode="json"))
        return self


def _reject_secrets(payload: Any, *, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if SENSITIVE_NAME.search(str(key)):
                raise ValueError(f"secret-shaped field is forbidden at {path}.{key}")
            _reject_secrets(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            _reject_secrets(value, path=f"{path}[{index}]")
    elif isinstance(payload, str) and SENSITIVE_NAME.search(payload) and "secret://" not in payload:
        raise ValueError(f"secret-shaped value is forbidden at {path}")


def _is_final_test_reference(value: str) -> bool:
    lowered = value.lower()
    if "aimada-wave1-final-" in lowered or lowered == "final-evaluation":
        return True
    if "://" in lowered:
        path = PurePosixPath(lowered.split("://", 1)[1])
    else:
        path = PurePosixPath(lowered)
    return any(part in {"test", "test-fold", "final-inputs"} for part in path.parts)
