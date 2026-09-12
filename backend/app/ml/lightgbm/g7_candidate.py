from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.cloud_contracts import (
    CloudArtifact,
    IMMUTABLE_IMAGE_PATTERN,
    LightGbmCloudJobRequest,
    Wave1FinalAuthorization,
)
from app.ml.lightgbm.cloud_runner import FrozenCandidate
from app.ml.lightgbm.contracts import (
    GIT_COMMIT_PATTERN,
    SHA256_PATTERN,
    CalibrationManifest,
)
from app.ml.lightgbm.g6_campaign import collect_validation_record
from app.nebius.object_storage import (
    publish_local_result,
    sha256_file,
    temporary_staging,
    verify_complete_result,
)


SIGNER = "Alexey Khabalov — Wave 1 Release Approver"
WAVE1_SPEND_CEILING_USD = 50.0


class _StrictCanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


class G7FinalEstimate(_StrictCanonicalModel):
    predicted_runtime_seconds: float = Field(gt=0, allow_inf_nan=False)
    predicted_cost_usd: float = Field(ge=0, allow_inf_nan=False)
    basis_runtime_seconds: float = Field(gt=0, allow_inf_nan=False)
    basis_cost_usd: float = Field(ge=0, allow_inf_nan=False)
    campaign_spend_to_date_usd: float = Field(ge=0, allow_inf_nan=False)
    projected_campaign_spend_usd: float = Field(ge=0, allow_inf_nan=False)
    spend_ceiling_usd: Literal[50.0] = WAVE1_SPEND_CEILING_USD

    @model_validator(mode="after")
    def validate_conservative_estimate(self) -> "G7FinalEstimate":
        if self.predicted_runtime_seconds < self.basis_runtime_seconds:
            raise ValueError("G7 final runtime estimate must not understate its selected-Job basis")
        if self.predicted_cost_usd < self.basis_cost_usd:
            raise ValueError("G7 final cost estimate must not understate its selected-Job basis")
        expected = self.campaign_spend_to_date_usd + self.predicted_cost_usd
        if not math.isclose(self.projected_campaign_spend_usd, expected, abs_tol=1e-12):
            raise ValueError("G7 projected spend does not match current spend plus final estimate")
        if self.projected_campaign_spend_usd > self.spend_ceiling_usd:
            raise ValueError("G7 final estimate exceeds the Wave 1 spend ceiling")
        return self


class G7AuthorizationChallenge(_StrictCanonicalModel):
    candidate_hash: str = Field(pattern=SHA256_PATTERN)
    statement_template: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_statement(self) -> "G7AuthorizationChallenge":
        expected = f"APPROVE WAVE1 FINAL TEST {self.candidate_hash} <ISO-8601 timestamp>"
        if self.statement_template != expected:
            raise ValueError("G7 authorization challenge is not canonical")
        return self


class G7CandidateFreeze(_StrictCanonicalModel):
    schema_version: Literal["lightgbm_wave1_g7_candidate_freeze_v1"] = (
        "lightgbm_wave1_g7_candidate_freeze_v1"
    )
    status: Literal["awaiting_manual_authorization"] = "awaiting_manual_authorization"
    created_at: AwareDatetime
    tool_git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    campaign_id: str
    selected_trial_id: str
    g6_comparison: CloudArtifact
    selected_collection: CloudArtifact
    selected_monitor: CloudArtifact
    candidate: CloudArtifact
    candidate_hash: str = Field(pattern=SHA256_PATTERN)
    reproducibility_hash: str = Field(pattern=SHA256_PATTERN)
    experiment_hash: str = Field(pattern=SHA256_PATTERN)
    input_identity_hash: str = Field(pattern=SHA256_PATTERN)
    model_sha256: str = Field(pattern=SHA256_PATTERN)
    source_result_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    calibration_method: Literal["raw", "platt", "isotonic"]
    operating_mode: Literal["balanced", "high_precision", "high_recall"]
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    validation_balanced_f1: float = Field(ge=0, le=1, allow_inf_nan=False)
    validation_minimum_family_recall: float = Field(ge=0, le=1, allow_inf_nan=False)
    validation_calibrated_brier: float = Field(ge=0, le=1, allow_inf_nan=False)
    validation_calibrated_ece: float = Field(ge=0, le=1, allow_inf_nan=False)
    test_fold_accessed: Literal[False] = False
    development_jobs_consumed: Literal[20] = 20
    development_job_ceiling: Literal[20] = 20
    final_estimate: G7FinalEstimate
    authorization_challenge: G7AuthorizationChallenge
    final_identity_available: Literal[False] = False

    @model_validator(mode="after")
    def validate_candidate_binding(self) -> "G7CandidateFreeze":
        if self.candidate.sha256 != self.candidate_hash:
            raise ValueError("G7 candidate artifact does not match the selected candidate hash")
        if self.authorization_challenge.candidate_hash != self.candidate_hash:
            raise ValueError("G7 authorization challenge does not bind the frozen candidate")
        return self


class G7AuthorizationReceipt(_StrictCanonicalModel):
    schema_version: Literal["lightgbm_wave1_g7_authorization_receipt_v1"] = (
        "lightgbm_wave1_g7_authorization_receipt_v1"
    )
    status: Literal["authorized"] = "authorized"
    authorized_at: AwareDatetime
    campaign_id: str
    candidate_hash: str = Field(pattern=SHA256_PATTERN)
    freeze_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    statement: str = Field(min_length=1, max_length=512)
    signer: Literal["Alexey Khabalov — Wave 1 Release Approver"] = SIGNER
    authorization: CloudArtifact
    authorization_signature: CloudArtifact
    authorization_public_key: CloudArtifact
    trusted_authorization_public_key_sha256: str = Field(pattern=SHA256_PATTERN)
    signature_verified: Literal[True] = True
    final_identity_available: Literal[True] = True

    @model_validator(mode="after")
    def validate_authorization_binding(self) -> "G7AuthorizationReceipt":
        expected = f"APPROVE WAVE1 FINAL TEST {self.candidate_hash} {self.authorized_at.isoformat()}"
        if self.statement != expected:
            raise ValueError("G7 authorization receipt statement is not canonical")
        if self.authorization_public_key.sha256 != self.trusted_authorization_public_key_sha256:
            raise ValueError("G7 authorization receipt does not bind its trusted public key")
        return self


def create_g7_candidate_freeze(
    *,
    g6_comparison_path: Path,
    selected_result: Path,
    selected_collection_path: Path,
    selected_monitor_path: Path,
    output: Path,
    tool_git_commit: str,
    created_at: datetime,
    predicted_final_runtime_seconds: float,
    predicted_final_cost_usd: float,
) -> G7CandidateFreeze:
    report = _load_g6_report(g6_comparison_path)
    selected_trial_id = _required_string(report, "selected_trial_id")
    campaign_id = _required_string(report, "campaign_id")
    record, experiment = collect_validation_record(
        result=selected_result,
        collection=selected_collection_path,
        trial_id=selected_trial_id,
        group="calibration",
        expected_campaign_id=campaign_id,
    )
    selected_candidate_hash = _required_hash(report, "selected_candidate_hash")
    selected_reproducibility_hash = _required_hash(
        report, "selected_reproducibility_hash"
    )
    if record.candidate_hash != selected_candidate_hash:
        raise ValueError("G7 selected result does not match the G6 candidate hash")
    if record.reproducibility_hash != selected_reproducibility_hash:
        raise ValueError("G7 selected result does not match the G6 reproducibility hash")
    if record.trial_id != selected_trial_id or record.calibration_method != "isotonic":
        raise ValueError("G7 selected result is not the G6 isotonic winner")

    verify_complete_result(selected_result)
    request = LightGbmCloudJobRequest.model_validate_json(
        (selected_result / "request.json").read_text(encoding="utf-8")
    )
    candidate_path = selected_result / "candidate.json"
    candidate = FrozenCandidate.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    if candidate.test_fold_accessed or candidate.experiment.canonical_hash() != experiment.canonical_hash():
        raise ValueError("G7 candidate changed its selected experiment or test-access boundary")
    calibration_path = _verified_candidate_artifact(
        selected_result / "artifacts", candidate.calibration_manifest
    )
    calibration = CalibrationManifest.model_validate_json(
        calibration_path.read_text(encoding="utf-8")
    )
    if (
        calibration.test_fold_accessed
        or calibration.parameters.method != record.calibration_method
    ):
        raise ValueError("G7 candidate calibration changed or accessed the test fold")
    operating_point = next(
        point for point in calibration.operating_points if point.mode == experiment.operating_mode
    )

    collection = _load_json_object(selected_collection_path, "selected collection")
    monitor = _load_json_object(selected_monitor_path, "selected monitor")
    basis_cost = _finite_number(collection.get("estimated_cost_usd"), "selected Job cost")
    campaign_spend = _finite_number(
        collection.get("campaign_spend_to_date_usd"), "campaign spend"
    )
    basis_runtime = _finite_number(monitor.get("elapsed_seconds"), "selected Job runtime")
    if (
        collection.get("verified") is not True
        or monitor.get("status") != "COMPLETED"
        or monitor.get("job_id") != collection.get("nebius_job_id")
        or monitor.get("request_sha256") != collection.get("request_sha256")
        or collection.get("request_sha256") != request.canonical_hash()
    ):
        raise ValueError("G7 selected Job execution receipts do not agree")
    actual_context = collection.get("actual_job_context")
    if not isinstance(actual_context, dict) or actual_context.get("image") != record.image:
        raise ValueError("G7 selected Job image receipt does not match the immutable candidate")

    estimate = G7FinalEstimate(
        predicted_runtime_seconds=predicted_final_runtime_seconds,
        predicted_cost_usd=predicted_final_cost_usd,
        basis_runtime_seconds=basis_runtime,
        basis_cost_usd=basis_cost,
        campaign_spend_to_date_usd=campaign_spend,
        projected_campaign_spend_usd=round(campaign_spend + predicted_final_cost_usd, 2),
    )
    challenge = G7AuthorizationChallenge(
        candidate_hash=selected_candidate_hash,
        statement_template=(
            f"APPROVE WAVE1 FINAL TEST {selected_candidate_hash} "
            "<ISO-8601 timestamp>"
        ),
    )

    staging = temporary_staging(output.resolve().parent, "g7-candidate-freeze")
    try:
        candidate_root = staging / "candidate"
        shutil.copytree(selected_result, candidate_root)
        verify_complete_result(candidate_root)
        evidence_root = staging / "evidence"
        evidence_root.mkdir()
        shutil.copy2(g6_comparison_path, evidence_root / "g6-comparison-final.json")
        shutil.copy2(selected_collection_path, evidence_root / "selected-collection.json")
        shutil.copy2(selected_monitor_path, evidence_root / "selected-monitor.json")
        freeze = G7CandidateFreeze(
            created_at=created_at,
            tool_git_commit=tool_git_commit,
            campaign_id=campaign_id,
            selected_trial_id=selected_trial_id,
            g6_comparison=_artifact(
                evidence_root / "g6-comparison-final.json", staging, "g6_comparison"
            ),
            selected_collection=_artifact(
                evidence_root / "selected-collection.json", staging, "selected_collection"
            ),
            selected_monitor=_artifact(
                evidence_root / "selected-monitor.json", staging, "selected_monitor"
            ),
            candidate=_artifact(candidate_root / "candidate.json", staging, "candidate"),
            candidate_hash=selected_candidate_hash,
            reproducibility_hash=selected_reproducibility_hash,
            experiment_hash=experiment.canonical_hash(),
            input_identity_hash=record.input_identity_hash,
            model_sha256=record.model_sha256,
            source_result_inventory_sha256=sha256_file(candidate_root / "SUCCESS"),
            image=record.image,
            calibration_method=record.calibration_method,
            operating_mode=experiment.operating_mode,
            threshold=operating_point.threshold,
            validation_balanced_f1=record.balanced_f1,
            validation_minimum_family_recall=record.minimum_family_recall,
            validation_calibrated_brier=record.calibrated_brier,
            validation_calibrated_ece=record.calibrated_ece,
            final_estimate=estimate,
            authorization_challenge=challenge,
        )
        (staging / "g7-candidate-freeze.json").write_bytes(freeze.canonical_bytes())
        publish_local_result(staging, output.resolve().as_uri())
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return freeze


def load_g7_candidate_freeze(root: Path) -> G7CandidateFreeze:
    verify_complete_result(root)
    freeze_path = root / "g7-candidate-freeze.json"
    freeze = G7CandidateFreeze.model_validate_json(freeze_path.read_text(encoding="utf-8"))
    for artifact in (
        freeze.g6_comparison,
        freeze.selected_collection,
        freeze.selected_monitor,
        freeze.candidate,
    ):
        _verify_root_artifact(root, artifact)
    verify_complete_result(root / "candidate")
    return freeze


def authorize_g7_candidate(
    *,
    freeze_root: Path,
    approval_statement: str,
    output: Path,
) -> G7AuthorizationReceipt:
    freeze = load_g7_candidate_freeze(freeze_root)
    statement_prefix = f"APPROVE WAVE1 FINAL TEST {freeze.candidate_hash} "
    if not approval_statement.startswith(statement_prefix):
        raise ValueError("G7 approval does not exactly match the frozen candidate hash")
    signed_at_raw = approval_statement.removeprefix(statement_prefix)
    try:
        signed_at = datetime.fromisoformat(signed_at_raw)
    except ValueError as exc:
        raise ValueError("G7 approval timestamp is not canonical ISO-8601") from exc
    if signed_at.tzinfo is None or signed_at.utcoffset() is None:
        raise ValueError("G7 approval timestamp must be timezone-aware")
    if approval_statement != f"{statement_prefix}{signed_at.isoformat()}":
        raise ValueError("G7 approval timestamp is not canonical ISO-8601")
    if signed_at < freeze.created_at:
        raise ValueError("G7 approval timestamp predates the candidate freeze")
    authorization = Wave1FinalAuthorization(
        campaign_id=freeze.campaign_id,
        candidate_hash=freeze.candidate_hash,
        signer=SIGNER,
        signed_at=signed_at,
        statement=approval_statement,
    )
    staging = temporary_staging(output.resolve().parent, "g7-authorization")
    try:
        authorization_path = staging / "authorization.json"
        signature_path = staging / "authorization.sig"
        public_key_path = staging / "authorization-public.pem"
        authorization_path.write_bytes(authorization.canonical_bytes())
        _sign_authorization(authorization_path, signature_path, public_key_path)
        trusted_key_sha256 = sha256_file(public_key_path)
        _verify_authorization_signature(
            authorization_path,
            signature_path,
            public_key_path,
        )
        receipt = G7AuthorizationReceipt(
            authorized_at=authorization.signed_at,
            campaign_id=authorization.campaign_id,
            candidate_hash=authorization.candidate_hash,
            freeze_receipt_sha256=sha256_file(freeze_root / "g7-candidate-freeze.json"),
            statement=authorization.statement,
            authorization=_artifact(authorization_path, staging, "authorization"),
            authorization_signature=_artifact(
                signature_path, staging, "authorization_signature"
            ),
            authorization_public_key=_artifact(
                public_key_path, staging, "authorization_public_key"
            ),
            trusted_authorization_public_key_sha256=trusted_key_sha256,
        )
        (staging / "g7-authorization.json").write_bytes(receipt.canonical_bytes())
        publish_local_result(staging, output.resolve().as_uri())
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return receipt


def load_g7_authorization(root: Path) -> G7AuthorizationReceipt:
    verify_complete_result(root)
    receipt = G7AuthorizationReceipt.model_validate_json(
        (root / "g7-authorization.json").read_text(encoding="utf-8")
    )
    authorization_path = _verify_root_artifact(root, receipt.authorization)
    signature_path = _verify_root_artifact(root, receipt.authorization_signature)
    public_key_path = _verify_root_artifact(root, receipt.authorization_public_key)
    authorization = Wave1FinalAuthorization.model_validate_json(
        authorization_path.read_text(encoding="utf-8")
    )
    if (
        authorization.campaign_id != receipt.campaign_id
        or authorization.candidate_hash != receipt.candidate_hash
        or authorization.statement != receipt.statement
    ):
        raise ValueError("G7 authorization artifact does not match its receipt")
    _verify_authorization_signature(authorization_path, signature_path, public_key_path)
    return receipt


def _load_g6_report(path: Path) -> dict[str, object]:
    report = _load_json_object(path, "G6 comparison")
    gates = report.get("gates")
    if (
        report.get("schema_version") != "lightgbm_wave1_g6_campaign_comparison_v1"
        or report.get("status") != "passed"
        or report.get("disposition") != "g6_candidate_selected"
        or report.get("test_fold_accessed") is not False
        or report.get("job_count") != 9
        or report.get("development_jobs_consumed_after_g6") != 20
        or not isinstance(gates, dict)
        or not gates
        or any(value is not True for value in gates.values())
    ):
        raise ValueError("G7 requires the fully passed, validation-only G6 comparison")
    return report


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"G7 {label} is not readable canonical JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"G7 {label} must be a JSON object")
    return payload


def _required_string(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"G7 comparison lacks {name}")
    return value


def _required_hash(payload: dict[str, object], name: str) -> str:
    value = _required_string(payload, name)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"G7 comparison has an invalid {name}")
    return value


def _finite_number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"G7 {label} is missing")
    converted = float(value)
    if not math.isfinite(converted) or converted < 0:
        raise ValueError(f"G7 {label} is invalid")
    return converted


def _artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    resolved = path.resolve()
    root = root.resolve()
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError(f"G7 {logical_name} artifact escaped its package")
    return CloudArtifact(
        logical_name=logical_name,
        uri=resolved.relative_to(root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
    )


def _verify_root_artifact(root: Path, artifact: CloudArtifact) -> Path:
    path = (root.resolve() / artifact.uri).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"G7 artifact is missing or outside its package: {artifact.logical_name}")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError(f"G7 artifact integrity failed: {artifact.logical_name}")
    return path


def _verified_candidate_artifact(root: Path, artifact: CloudArtifact) -> Path:
    path = (root.resolve() / artifact.uri).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"G7 candidate artifact is missing: {artifact.logical_name}")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError(f"G7 candidate artifact checksum mismatch: {artifact.logical_name}")
    return path


def _sign_authorization(document: Path, signature: Path, public_key: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="wave1-g7-signing-") as directory:
        private_key = Path(directory) / "private.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(private_key),
                "-pubout",
                "-out",
                str(public_key),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(document),
                "-out",
                str(signature),
            ],
            check=True,
            capture_output=True,
        )


def _verify_authorization_signature(document: Path, signature: Path, public_key: Path) -> None:
    completed = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-sigfile",
            str(signature),
            "-rawin",
            "-in",
            str(document),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        raise ValueError("G7 authorization signature verification failed")
