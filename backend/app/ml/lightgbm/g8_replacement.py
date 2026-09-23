"""Package-bound replacement preflight; never treats the consumed R4 approval as reusable."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest
from app.ml.lightgbm.cloud_runner import _verify_signature
from app.ml.lightgbm.g8_mlflow_recovery import ReservationSpec
from app.ml.lightgbm.g8_production_transport import ARCHIVES, BOOTSTRAP, DEPLOYMENT_IMAGE, MAX_FILE, PACKAGE, verify_archives

SHA = r"^[0-9a-f]{64}$"
IMAGE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2"
CANDIDATE = "5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff"
FINAL_RELEASE = "s3://aimada-wave1-final-e00g6zvxpr00/releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging"
FROZEN_ROOT = "642c7258b3424de05bbe8054a0b5c963b3f9fc9c2af65e1892e906c68fe0e7b9"
FINAL_PROJECTION = "2464d7b4e952ee5b007f06e1809eba66e7502efb1484ab1e7f4e034be32e13e7"
MODULES = ("cloud_contracts", "g8_replacement", "g8_live_recovery", "g8_scored_checkpoint", "g8_mlflow_recovery",
           "g8_publication_recovery", "tracking", "c4_evaluation", "c4_replay_evidence", "g8_benchmark_readiness",
           "g8_production_transport")
CODE_PATHS = {f"{name}.py": f"/job/backend/app/ml/lightgbm/{name}.py" for name in MODULES}
CODE_PATHS.update({name: f"/job/g8/{name}" for name in
                   ("run_lightgbm_g8.py", "run_lightgbm_g8_replacement.py")})


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PackageFile(Strict):
    sha256: str = Field(pattern=SHA)
    size_bytes: int = Field(gt=0, le=MAX_FILE)


class ReplacementPlan(Strict):
    schema_version: Literal["g8_replacement_plan_v3"] = "g8_replacement_plan_v3"
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    run_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,53}$")
    request_sha256: str = Field(pattern=SHA)
    candidate_sha256: str = Field(default=CANDIDATE, pattern=SHA)
    image: Literal[IMAGE] = IMAGE
    prior_final_jobs_submitted: Literal[4] = 4
    prior_test_fold_accessed: Literal[True] = True
    prior_run_id: Literal["nasdaq-g8-final-r4-20260913"] = "nasdaq-g8-final-r4-20260913"
    prior_job_id: Literal["aijob-e00vtamgkr07mwzt4t"] = "aijob-e00vtamgkr07mwzt4t"
    prior_monitor_sha256: Literal["e6975dcd517dda25b91a0b6bea9a786c87f7d82a451fcb71a8dcc34355016b72"]
    prior_log_sha256: Literal["eadddbdbac943939a9b8243398584ac8866352b30117ef7ea0e3fb9ed9ac2a8c"]
    replacement_executions_allowed: Literal[1] = 1
    no_retraining_recalibration_or_threshold_changes: Literal[True] = True
    filesystem_id: str = Field(pattern=r"^computefilesystem-[a-z0-9]+$")
    mount_path: Literal["/g8-durable"] = "/g8-durable"
    mount_source: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    mount_type: Literal["virtiofs"] = "virtiofs"
    capacity_gib: int = Field(ge=1, le=100)
    max_checkpoint_bytes: int = Field(gt=0, le=20 * 1024**3)
    max_checkpoint_files: int = Field(gt=0, le=10000)
    comparison_relative_path: str = Field(pattern=r"^comparison/[a-z0-9-]+/comparison.json$")
    evaluation_profile_sha256: str = Field(pattern=SHA)
    comparison_sha256: str = Field(pattern=SHA)
    candidate_release_uri: str
    subnet_id: Literal["vpcsubnet-e00ppzc4353dxv210j"] = "vpcsubnet-e00ppzc4353dxv210j"
    secret_selectors: dict[str, str]
    verified_at: AwareDatetime
    validation_policy: Literal["lightgbm_transformers_validation_v1"] = "lightgbm_transformers_validation_v1"
    spend_monitoring: Literal["operator_managed_alerts"] = "operator_managed_alerts"
    native_durability_receipt_sha256: str = Field(pattern=SHA)
    authenticated_remote_receipt_sha256: str = Field(pattern=SHA)
    comparison_inventory_receipt_sha256: str = Field(pattern=SHA)
    files: dict[str, PackageFile]

    @model_validator(mode="after")
    def boundaries(self):
        import re
        if self.candidate_sha256 != CANDIDATE:
            raise ValueError("replacement must preserve the exact production candidate")
        if (set(self.secret_selectors) != {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD"}
                or any(re.fullmatch(r"mbsec-[a-z0-9]+@mbsecver-[a-z0-9]+", v) is None
                       for v in self.secret_selectors.values())):
            raise ValueError("replacement requires four version-pinned MysteryBox selectors")
        if self.run_id == self.prior_run_id:
            raise ValueError("replacement must have a new run identity")
        # Workspace, scored copy, recovery snapshot and completed/publication copies.
        if 5 * self.max_checkpoint_bytes > self.capacity_gib * 1024**3:
            raise ValueError("storage budget must cover five bounded working copies")
        required = set(CODE_PATHS) | set(ARCHIVES) | {BOOTSTRAP, "request.json", "profile.json", "frozen-root.json", "projection.json",
            "candidate.json", "c4-inputs.json", "dataset-lineage.json", "authorization.json",
            "authorization.sig", "authorization-public.pem", "native-durability.json", "remote-roundtrip.json",
            "comparison-inventory.json"}
        if set(self.files) != required:
            raise ValueError("replacement package must bind the exact complete file allowlist")
        return self

    def identity(self):
        return hashlib.sha256(canonical(self)).hexdigest()


def canonical(value):
    return (json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def verify_package(root: Path, *, trusted_key: str, now: datetime | None = None,
                   recovery: bool = False) -> tuple[ReplacementPlan, LightGbmCloudJobRequest]:
    """Offline verification. Signature covers all code, evidence and execution identities.

    Validation packages have no administrative submission or recovery expiry.
    The original durable reservation and scoring seal are separately mandatory there.
    """
    if root.absolute() != root.resolve() or not root.is_dir():
        raise ValueError("package root must be a canonical directory")
    marker = root / "replacement.json"
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 64 * 1024:
        raise ValueError("replacement plan must be a bounded regular file")
    raw = marker.read_bytes()
    plan = ReplacementPlan.model_validate_json(raw)
    if raw != canonical(plan):
        raise ValueError("replacement plan must be canonical")
    allowed = set(plan.files) | {"replacement.json", "replacement.sig"}
    if {p.name for p in root.iterdir()} != allowed:
        raise ValueError("replacement package has missing or unexpected members")
    for name in allowed:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
            raise ValueError("replacement files must be bounded regular files")
    for name, ref in plan.files.items():
        path = root / name
        if path.stat().st_size != ref.size_bytes or sha256_file(path) != ref.sha256:
            raise ValueError("replacement package file changed: " + name)
    _verify_signature(root / "replacement.json", root / "replacement.sig", root / "authorization-public.pem",
                      trusted_public_key_sha256=trusted_key)
    verify_archives(root, CODE_PATHS)
    current = now or datetime.now(UTC)
    if plan.verified_at > current:
        raise ValueError("replacement verification timestamp is in the future")
    request = LightGbmCloudJobRequest.model_validate_json((root / "request.json").read_bytes())
    if (request.canonical_hash() != plan.request_sha256 or request.run_id != plan.run_id
            or request.git_commit != plan.source_commit
            or request.mode != "final-evaluation" or request.candidate is None
            or request.candidate.sha256 != plan.candidate_sha256 or request.image != plan.image
            or request.input.kind != "tabular-projection"
            or request.input.projection_artifact_root != "artifacts"
            or request.input_release_uri != FINAL_RELEASE
            or request.input.frozen_root.sha256 != FROZEN_ROOT
            or request.input.projection.sha256 != FINAL_PROJECTION
            or request.mlflow_tracking_uri != "http://10.4.0.54:5500"):
        raise ValueError("replacement request differs from signed plan")
    if sha256_file(root / "candidate.json") != plan.candidate_sha256:
        raise ValueError("replacement candidate differs from frozen G7")
    if (request.candidate.uri != "candidate/candidate.json"
            or request.candidate.size_bytes != plan.files["candidate.json"].size_bytes
            or request.input.frozen_root.uri != "manifests/frozen-root.json"
            or request.input.projection.uri != "manifests/tabular-projection.json"
            or request.input.dataset_lineage_receipt.uri != "manifests/c4-mlflow-dataset-release.json"):
        raise ValueError("replacement input references must match the exact C4/candidate layout")
    from app.ml.lightgbm.cloud_runner import FrozenCandidate
    candidate = FrozenCandidate.model_validate_json((root / "candidate.json").read_bytes())
    if (candidate.test_fold_accessed or candidate.campaign_id != request.campaign_id
            or candidate.experiment.canonical_hash() != request.experiment.canonical_hash()):
        raise ValueError("replacement experiment differs from frozen candidate")
    for reference, name in ((request.authorization, "authorization.json"),
            (request.authorization_signature, "authorization.sig"),
            (request.authorization_public_key, "authorization-public.pem"),
            (request.input.dataset_lineage_receipt, "dataset-lineage.json")):
        if (reference is None or reference.sha256 != plan.files[name].sha256
                or reference.size_bytes != plan.files[name].size_bytes):
            raise ValueError("authorization/lineage artifact differs from request")
        if name != "dataset-lineage.json" and reference.uri != "authorization/" + name:
            raise ValueError("replacement authorization must use the dedicated input directory")
    from app.ml.lightgbm.cloud_contracts import Wave1FinalAuthorization
    authorization = Wave1FinalAuthorization.model_validate_json((root / "authorization.json").read_bytes())
    if (authorization.candidate_hash != plan.candidate_sha256 or authorization.campaign_id != request.campaign_id
            or not plan.verified_at - timedelta(hours=1) <= authorization.signed_at <= plan.verified_at):
        raise ValueError("fresh candidate authorization required; consumed R4 statement cannot be reused")
    _verify_signature(root / "authorization.json", root / "authorization.sig", root / "authorization-public.pem",
                      trusted_public_key_sha256=trusted_key)
    expected_result = f"s3://aimada-wave1-results-e00g6zvxpr00/campaigns/{request.campaign_id}/final/{request.run_id}"
    if request.result_uri != expected_result:
        raise ValueError("replacement output must be its exact new result prefix")
    from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile
    from app.market_data.projections import FrozenPublicSampleRoot
    profile = C4EvaluationProfile.model_validate_json((root / "profile.json").read_bytes())
    frozen = FrozenPublicSampleRoot.model_validate_json((root / "frozen-root.json").read_bytes())
    from app.market_data.projections import C4MlflowDatasetReleaseReceipt
    lineage = C4MlflowDatasetReleaseReceipt.model_validate_json((root / "dataset-lineage.json").read_bytes())
    if (lineage.raw_rows_uploaded_to_mlflow or lineage.release_id != frozen.release_id
            or lineage.root_file_sha256 != request.input.frozen_root.sha256
            or lineage.root_identity_sha256 != frozen.canonical_hash()
            or lineage.tabular_final_sha256 != request.input.projection.sha256):
        raise ValueError("replacement must retain verified C4 dataset lineage")
    if (profile.canonical_hash() != plan.evaluation_profile_sha256
            or profile.candidate_sha256 != plan.candidate_sha256
            or profile.comparison_evidence_sha256 != plan.comparison_sha256
            or profile.frozen_root_sha256 != frozen.canonical_hash()
            or sha256_file(root / "frozen-root.json") != request.input.frozen_root.sha256
            or sha256_file(root / "projection.json") != request.input.projection.sha256
            or profile.projection_sha256 != request.input.projection.sha256):
        raise ValueError("replacement C4 contract differs from frozen metadata")
    expected_inputs = {name: f"{PACKAGE}/{file}" for name, file in
        (("profile", "profile.json"), ("frozen_root", "frozen-root.json"), ("projection", "projection.json"),
         ("candidate", "candidate.json"))}
    expected_inputs["comparison"] = plan.mount_path + "/" + plan.comparison_relative_path
    if json.loads((root / "c4-inputs.json").read_bytes()) != expected_inputs:
        raise ValueError("C4 input locations must match the signed mount/package")
    for name, digest in (("native-durability", plan.native_durability_receipt_sha256),
                         ("remote-roundtrip", plan.authenticated_remote_receipt_sha256),
                         ("comparison-inventory", plan.comparison_inventory_receipt_sha256)):
        if sha256_file(root / f"{name}.json") != digest:
            raise ValueError("preflight evidence receipt binding differs")
    # These are operator-reviewed observations, never credentials or self-created approvals.
    native = json.loads((root / "native-durability.json").read_bytes())
    remote = json.loads((root / "remote-roundtrip.json").read_bytes())
    comparison = json.loads((root / "comparison-inventory.json").read_bytes())
    if (native.get("filesystem_id") != plan.filesystem_id or native.get("mount_source") != plan.mount_source
            or native.get("mount_type") != plan.mount_type or native.get("capacity_gib") != plan.capacity_gib
            or native.get("job_loss_reattachment_verified") is not True
            or remote.get("authenticated_mlflow_artifact_readback") is not True
            or remote.get("authenticated_s3_readback") is not True
            or remote.get("tracking_uri") != request.mlflow_tracking_uri
            or remote.get("image") != plan.image
            or comparison.get("comparison_sha256") != plan.comparison_sha256
            or comparison.get("original_checkpoint_count") != 27
            or comparison.get("metadata_inventory_verified") is not True):
        raise ValueError("replacement readiness evidence is incomplete or mismatched")
    for receipt in (native, remote, comparison):
        observed = datetime.fromisoformat(receipt["verified_at"])
        if observed.tzinfo is None or observed > plan.verified_at:
            raise ValueError("readiness observations must precede package signing and be timezone-aware")
    return plan, request


def reservation(plan: ReplacementPlan, request: LightGbmCloudJobRequest) -> ReservationSpec:
    return ReservationSpec(execution_package_sha256=plan.identity(), request_sha256=plan.request_sha256,
        candidate_sha256=plan.candidate_sha256, evaluation_profile_sha256=plan.evaluation_profile_sha256,
        request_run_id=plan.run_id, tracking_uri=request.mlflow_tracking_uri)


def verify_mount(plan: ReplacementPlan, mountinfo: str | None = None):
    """Require the exact rehearsal-observed native mount, never an overlay/FUSE fallback."""
    text = Path("/proc/self/mountinfo").read_text() if mountinfo is None else mountinfo
    mounts = []
    for line in text.splitlines():
        before, after = line.split(" - ", 1)
        fields, filesystem = before.split(), after.split()
        if fields[4] == plan.mount_path:
            mounts.append((fields, filesystem))
        elif fields[4].startswith(plan.mount_path + "/"):
            raise ValueError("nested mounts are forbidden under durable storage")
    if len(mounts) != 1:
        raise ValueError("exact native durable mount is missing or ambiguous")
    fields, filesystem = mounts[0]
    if (filesystem[0] != plan.mount_type or filesystem[1] != plan.mount_source
            or "rw" not in fields[5].split(",") or "rw" not in filesystem[2].split(",")):
        raise ValueError("durable mount differs from reviewed native filesystem evidence")
    # Kernel mount ID, parent ID, device and root detect replacement during the
    # signed-context wait, even when the new mount advertises the same source.
    return tuple(fields[:4])


def job_command(plan: ReplacementPlan, root: Path, trusted_key: str, *, recovery: bool = False) -> list[str]:
    """Render only; the operator must persist the submission intent before issuing this once."""
    import re
    if re.fullmatch(SHA, trusted_key) is None:
        raise ValueError("trusted public-key hash required")
    request_path = root / "request.json"
    request = LightGbmCloudJobRequest.model_validate_json(request_path.read_bytes())
    if (sha256_file(request_path) != plan.files["request.json"].sha256
            or request.canonical_hash() != plan.request_sha256
            or request.resource.timeout_seconds not in {3600, 10800}):
        raise ValueError("rendered timeout requires the exact package-bound request")
    operation = "--recover" if recovery else "--execute"
    job_name = plan.run_id + "-recovery" if recovery else plan.run_id
    command = ["nebius", "ai", "job", "create", "--name", job_name, "--image", DEPLOYMENT_IMAGE,
        "--parent-id", "project-e00g6zvxpr00waz8t3y51k", "--subnet-id", plan.subnet_id,
        "--platform", "cpu-d3", "--preset", "4vcpu-16gb", "--disk-size", "100Gi",
        "--timeout", f"{request.resource.timeout_seconds // 3600}h",
        "--restart-policy", "never", "--volume", f"{plan.filesystem_id}:{plan.mount_path}:rw",
        "--volume", f"{plan.filesystem_id}:/g8-package:ro",
        "--container-command", "python", "--args", f"/job/g8/{BOOTSTRAP} {operation} --package {PACKAGE}",
        "--format", "json"]
    command.extend(["--inject-file", f"{root / BOOTSTRAP}:/job/g8/{BOOTSTRAP}"])
    for index, archive in enumerate(ARCHIVES):
        command.extend(["--env", f"G8_NATIVE_CODE_{index}_SHA256={plan.files[archive].sha256}"])
    for key, value in sorted(plan.secret_selectors.items()):
        command.extend(["--env-secret", f"{key}={value}"])
    for value in ("G8_NATIVE_TARGET=production", "MLFLOW_HTTP_REQUEST_MAX_RETRIES=0",
                  "MLFLOW_HTTP_REQUEST_TIMEOUT=20", "AWS_EC2_METADATA_DISABLED=true",
                  "PYTHONDONTWRITEBYTECODE=1",
                  "AWS_DEFAULT_REGION=eu-north1", f"WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256={trusted_key}"):
        command.extend(["--env", value])
    return command
