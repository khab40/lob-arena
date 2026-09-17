"""Signed synthetic-only native rehearsal contract; no provisioning or model imports."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

if __package__:
    from .g8_native_source_capsule import MAX_INJECTION
else:
    from g8_native_source_capsule import MAX_INJECTION

IMAGE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2"
DEPLOYMENT_IMAGE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/g:dc32b12d7216bfee"
IMAGE_DIGEST = "sha256:" + IMAGE.rsplit("sha256:", 1)[1]
PROJECT = "project-e00g6zvxpr00waz8t3y51k"
SUBNET = "vpcsubnet-e00ppzc4353dxv210j"
# MysteryBox resource/version identifiers, never credential values. The Job
# service resolves these pinned references into credentials at execution time.
S3_SELECTORS = {
    "AWS_ACCESS_KEY_ID": "mbsec-e00arhndyprqr8egjw@mbsecver-e00rjzerny1pf9qhna",
    "AWS_SECRET_ACCESS_KEY": "mbsec-e00s7qtjj5n9ghacnh@mbsecver-e00yfn5w54jc1ybkwv",
}
MODULES = ("g8_replacement", "g8_live_recovery", "g8_scored_checkpoint", "g8_mlflow_recovery",
           "g8_publication_recovery", "tracking", "c4_evaluation", "c4_replay_evidence",
           "g8_benchmark_readiness", "g8_c4_fixture")
SCRIPTS = ("run_lightgbm_g8", "prepare_g8_native_sources", "g8_rehearsal", "stage_g8_native_sources",
           "g8_source_sdk", "g8_native_source_capsule", "g8_native_contract", "g8_native_readback",
           "g8_native_runtime", "g8_native_lifecycle", "run_g8_native_rehearsal", "g8_native_archive")
ARCHIVES = ("native-code-0.zip", "native-code-1.zip", "native-code-2.zip")
BOOTSTRAP = "g8_native_bootstrap.py"
PACKAGE = "/g8-package/package"
CODE_PATHS = {f"{n}.py": f"/job/backend/app/ml/lightgbm/{n}.py" for n in MODULES}
CODE_PATHS.update({f"{n}.py": f"/job/g8/{n}.py" for n in SCRIPTS})
CAPSULE = {f"source-capsule/inventory-{i}.part" for i in range(2)} | {
    f"source-capsule/metadata-{i}.part" for i in range(6)}
SHA = r"^[a-f0-9]{64}$"


def canonical(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileRef(Strict):
    sha256: str = Field(pattern=SHA)
    size_bytes: int = Field(gt=0, le=65536)


class RegistryVerification(Strict):
    deployment_image: Literal[DEPLOYMENT_IMAGE]
    expected_digest: Literal[IMAGE_DIGEST]
    resolved_digest: Literal[IMAGE_DIGEST]
    manifest_sha256: str = Field(pattern=SHA)
    verified_at: AwareDatetime


class NativePlan(Strict):
    schema_version: Literal["g8_native_rehearsal_plan_v5"] = "g8_native_rehearsal_plan_v5"
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    run_id: Literal["synthetic-final"] = "synthetic-final"
    request_sha256: Literal["6f7d5b2aec04f49719b16ed9146baee472f7373374f1cd0dedf51dddb61ec486"]
    candidate_sha256: Literal["e04f50ff0748a0077c0602c397ed7c9c3087757fe0892f1a2d284e91b2383b7c"]
    evaluation_profile_sha256: Literal["4cdace51a0133e3be41baa385ea806c7010ded42c48ae172a0fee18c5c5f589e"]
    image: Literal[IMAGE] = IMAGE
    deployment_image: Literal[DEPLOYMENT_IMAGE] = DEPLOYMENT_IMAGE
    registry_verification: RegistryVerification
    filesystem_id: str = Field(pattern=r"^computefilesystem-[a-z0-9]+$")
    mount_path: Literal["/g8-durable"] = "/g8-durable"
    capacity_gib: Literal[10] = 10
    max_checkpoint_bytes: Literal[67108864] = 67108864
    max_checkpoint_files: Literal[2000] = 2000
    candidate_release_uri: Literal["s3://aimada-wave1-results-e00g6zvxpr00/campaigns/g8-native-rehearsal-20260914/development/synthetic-development"]
    secret_selectors: dict[str, str]
    verified_at: AwareDatetime
    validation_policy: Literal["lightgbm_transformers_validation_v1"] = "lightgbm_transformers_validation_v1"
    spend_monitoring: Literal["operator_managed_alerts"] = "operator_managed_alerts"
    maximum_jobs: Literal[2] = 2
    files: dict[str, FileRef]
    production_final_test_authorized: Literal[False] = False
    dataset_lineage_kind: Literal["synthetic_placeholder_not_remote_mlflow_registration"]
    comparison_kind: Literal["synthetic_contract_fixtures_not_java_execution"]

    @model_validator(mode="after")
    def boundaries(self):
        if not self.verified_at - timedelta(minutes=5) <= self.registry_verification.verified_at <= self.verified_at:
            raise ValueError("fresh registry mapping required when signing the package")
        names = set(S3_SELECTORS) | {"MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD"}
        if (set(self.secret_selectors) != names
                or any(re.fullmatch(r"mbsec-[a-z0-9]+@mbsecver-[a-z0-9]+", s) is None
                       for s in self.secret_selectors.values())
                or any(self.secret_selectors[k] != v for k, v in S3_SELECTORS.items())):
            raise ValueError("exact development S3 and four version-pinned selectors required")
        if set(self.files) != set(CODE_PATHS) | CAPSULE | set(ARCHIVES) | {BOOTSTRAP, "reviewer-public.pem", "filesystem.json"}:
            raise ValueError("exact native code, capsule, reviewer and filesystem allowlist required")
        if any(ref.size_bytes > MAX_INJECTION for name, ref in self.files.items() if name not in CODE_PATHS):
            raise ValueError("physical injection exceeds 40 KiB transport bound")
        return self

    def identity(self):
        return hashlib.sha256(canonical(self)).hexdigest()


def environment(plan):
    return {
        "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0", "MLFLOW_HTTP_REQUEST_TIMEOUT": "20",
        "AWS_EC2_METADATA_DISABLED": "true", "AWS_DEFAULT_REGION": "eu-north1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "G8_NATIVE_REVIEWER_SHA256": plan.files["reviewer-public.pem"].sha256,
        **{f"G8_NATIVE_CODE_{i}_SHA256": plan.files[name].sha256 for i, name in enumerate(ARCHIVES)},
    }


def injections(plan):
    # Bulk code/metadata use native storage, not SecretStash/KMS injections.
    return {f"/job/g8/{BOOTSTRAP}": BOOTSTRAP}


def job_name(phase):
    if phase not in {"score", "recover"}:
        raise ValueError("exactly two native phases")
    return "g8-native-20260915-" + phase


def job_command(plan, package, *, phase):
    """Render argv only. Persist intent and verify the package before one create."""
    command = ["nebius", "ai", "job", "create", "--name", job_name(phase),
        "--image", plan.deployment_image, "--parent-id", PROJECT, "--subnet-id", SUBNET,
        "--platform", "cpu-d3", "--preset", "4vcpu-16gb", "--disk-size", "100Gi",
        "--timeout", "1h", "--restart-policy", "never", "--volume", f"{plan.filesystem_id}:/g8-durable:rw",
        "--volume", f"{plan.filesystem_id}:/g8-package:ro",
        "--container-command", "python", "--args", f"/job/g8/{BOOTSTRAP} --phase {phase}",
        "--format", "json"]
    for path, name in sorted(injections(plan).items()):
        command.extend(["--inject-file", f"{package / name}:{path}"])
    for key, value in sorted(environment(plan).items()):
        command.extend(["--env", f"{key}={value}"])
    for key, value in sorted(plan.secret_selectors.items()):
        command.extend(["--env-secret", f"{key}={value}"])
    return command
