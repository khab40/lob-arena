"""Export/load hash-pinned research metadata; never fit, score or access cloud."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import NamedTuple

from app.features.pipeline import FEATURE_COLUMNS
from .contracts import InputContract, Normalization
from .research_comparison_contract import MANIFEST, REPLACEMENT_PREFIX
from .research_confirmation_contract import LEGACY_PREFIX
from .settings_schema import (
    Artifacts, Lineage, OperatingPoint, Preprocessing, SettingsRelease, TrainingSettings,
)

BUCKET = "aimada-wave1-results-e00g6zvxpr00"
METADATA_LIMIT = 2 * 1024 * 1024


class ArtifactRead(NamedTuple):
    data: bytes
    version_id: str


def checked_read(reference, reader, *, metadata=True):
    """Reader must honor the exact version and bound streaming by size_bytes."""
    if metadata and reference.size_bytes > METADATA_LIMIT:
        raise ValueError("settings metadata exceeds read bound")
    result = reader(reference)
    if (not isinstance(result, ArtifactRead) or result.version_id != reference.version_id
            or type(result.data) is not bytes or len(result.data) != reference.size_bytes
            or hashlib.sha256(result.data).hexdigest() != reference.sha256):
        raise ValueError("settings artifact version, size or checksum differs")
    return result.data


def json_record(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate settings metadata key")
            value[key] = item
        return value

    def nonfinite(value):
        raise ValueError("nonfinite settings metadata")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def build_release(artifacts: Artifacts, reader, *, verification_sha256, decision_sha256, selection_sha256):
    """Pins come from reviewed evidence, never from the supplied manifest itself."""
    if (artifacts.verification.sha256 != verification_sha256 or artifacts.decision.sha256 != decision_sha256
            or artifacts.selection_verification.sha256 != selection_sha256
            or any(not getattr(artifacts, name).uri.startswith("evidence:sha256:")
                   for name in ("verification", "selection_verification", "decision", "comparison_summary"))):
        raise ValueError("settings evidence differs from caller trust pins")
    report = json_record(checked_read(artifacts.verification, reader))
    selection = json_record(checked_read(artifacts.selection_verification, reader))
    decision = json_record(checked_read(artifacts.decision, reader))
    summary = json_record(checked_read(artifacts.comparison_summary, reader))
    result, context = report["result"], report["context"]
    origin, bindings = result["checkpoint_origin"], result["checkpoint_origin"]["bindings"]
    execution = result["execution_bindings"]
    selected = selection["result"]
    if (selection["status"] != "verified" or selected["status"] != "verified"
            or selected["kind"] != "trial" or selected["final_test_access"] is not False
            or selected["selected_epoch"] != origin["checkpoint"]["epoch"]
            or selected["trial"] != MANIFEST["selected"]["trial"]
            or selected["trial_sha256"] != origin["trial_sha256"]
            or selected["selected_checkpoint"] != origin["checkpoint"] or selected["bindings"] != bindings
            or selection["context"]["request_sha256"] != origin["request_sha256"]
            or selected["request_sha256"] != origin["request_sha256"]
            or selected["job_id"] != selection["context"]["job_id"]
            or selection["context"]["image_digest"] != bindings["image_digest"]):
        raise ValueError("settings original selection receipt differs")
    if (report["status"] != "verified" or summary["verification"]["status"] != "verified"
            or summary["verification"]["receipt_sha256"] != verification_sha256
            or decision["results_evidence_sha256"] != artifacts.comparison_summary.sha256
            or result["kind"] != "inference" or result["final_test_access"] is not False
            or result["job_id"] != context["job_id"] or summary["job_id"] != result["job_id"]
            or result["request_sha256"] != context["request_sha256"]
            or summary["request_sha256"] != result["request_sha256"]
            or execution != {**bindings, "source_commit": execution["source_commit"],
                             "image_digest": context["image_digest"]}
            or origin["slot"] != MANIFEST["selected"]["slot"]
            or origin["request_sha256"] != MANIFEST["prior"][origin["slot"]]["request"]["sha256"]
            or origin["trial_sha256"] != MANIFEST["selected"]["trial_sha256"]
            or result["winner_trial_sha256"] != origin["trial_sha256"]
            or summary["candidate"]["checkpoint"] != origin["checkpoint"]):
        raise ValueError("settings selection/comparison/decision lineage differs")
    for name, ref in (("input-contract.json", artifacts.contract), ("normalization.json", artifacts.normalization)):
        item = report["inventory"][name]
        if (item != {k: getattr(ref, k) for k in ("sha256", "size_bytes", "version_id")}
                or ref.uri != f"s3://{BUCKET}/{REPLACEMENT_PREFIX}inference/{name}"):
            raise ValueError("settings input artifact origin differs")
    checkpoint = origin["checkpoint"]
    if (checkpoint["epoch"] != MANIFEST["selected"]["checkpoint"]["epoch"]
            or checkpoint["object_name"] != MANIFEST["selected"]["checkpoint"]["object_name"]
            or artifacts.checkpoint.uri != f"s3://{BUCKET}/{LEGACY_PREFIX}{origin['slot']}/{checkpoint['object_name']}"
            or any(getattr(artifacts.checkpoint, k) != checkpoint[k] for k in ("sha256", "size_bytes", "version_id"))):
        raise ValueError("settings checkpoint origin differs")
    if selection["inventory"][checkpoint["object_name"]] != {
            k: getattr(artifacts.checkpoint, k) for k in ("sha256", "size_bytes", "version_id")}:
        raise ValueError("settings original checkpoint inventory differs")
    contract_raw = checked_read(artifacts.contract, reader)
    normalization_raw = checked_read(artifacts.normalization, reader)
    json_record(contract_raw)
    json_record(normalization_raw)
    contract = InputContract.model_validate_json(contract_raw)
    normalization = Normalization.model_validate_json(normalization_raw)
    source, root = bindings["source_binding"], contract.root
    targets = bindings["ordered_targets_sha256"]
    if (artifacts.contract.sha256 != bindings["contract_sha256"]
            or artifacts.normalization.sha256 != bindings["normalization_sha256"]
            or normalization.training_binding_sha256 != contract.training_binding()
            or normalization.fitting_row_sha256 != targets["train"]
            or source["feature_release_id"] != root.feature_release_id
            or source["feature_release_sha256"] != root.feature_release_sha256):
        raise ValueError("settings feature/normalization training lineage differs")
    checked_read(artifacts.checkpoint, reader, metadata=False)  # Hash only; never deserialize weights.
    calibration = result.get("calibration")
    comparison = result["comparison"]
    points = tuple(OperatingPoint(mode=p["mode"], threshold=p["threshold"])
                   for p in comparison.get("transformer_selected_operating_points", []))
    gates = (result["freeze_blocked"] is False and comparison["freeze_blocked"] is False
             and result["stability"]["passed"] is True and bool(calibration)
             and result["stability"]["candidate_seed"] == 42
             and comparison["unattainable_floor"] is False
             and comparison["calibration_worsened_brier_and_ece"] is False
             and calibration["converged"] is True and calibration["boundary_hit"] is False
             and calibration["fitting_role"] == "calibration"
             and tuple(p.mode for p in points) == ("high_precision", "balanced", "high_recall"))
    return SettingsRelease(artifacts=artifacts, training=TrainingSettings(**MANIFEST["selected"]["trial"]),
        preprocessing=Preprocessing(ordered_features=contract.ordered_features),
        lineage=Lineage(feature_release_id=root.feature_release_id, feature_release_sha256=root.feature_release_sha256,
            feature_config_sha256=root.feature_config_sha256, root_sha256=root.canonical_hash(),
            training_binding_sha256=contract.training_binding(), trial_sha256=origin["trial_sha256"],
            selected_epoch=checkpoint["epoch"], numerical_source_commit=bindings["source_commit"],
            training_image_digest=bindings["image_digest"], selection_request_sha256=origin["request_sha256"],
            selection_job_id=selected["job_id"], selection_run_id=selection["context"]["run_id"],
            comparison_request_sha256=result["request_sha256"], comparison_job_id=result["job_id"],
            comparison_run_id=context["run_id"],
            comparison_source_commit=execution["source_commit"], comparison_image_digest=execution["image_digest"],
            role_manifest_sha256=bindings["role_manifest_sha256"],
            **{role + "_targets_sha256": targets[role] for role in ("train", "selection", "calibration", "operating_point")}),
        temperature=None if not calibration else calibration["temperature"], operating_points=points,
        decision=decision["decision"], gates_passed=bool(gates), limitations=tuple(comparison["limitations"]))


def save_release(release: SettingsRelease, path: Path):
    """Atomic exclusive link: interrupted writes never expose a partial manifest."""
    path = Path(path)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".settings-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(release.canonical_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Existing destinations, including symlinks, are never overwritten.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return release.sha256()


def load_release(raw: bytes, reader, *, expected_sha256, verification_sha256, decision_sha256, selection_sha256,
                 ordered_features=FEATURE_COLUMNS):
    if len(raw) > METADATA_LIMIT or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("settings manifest checksum or size differs")
    json_record(raw)
    release = SettingsRelease.model_validate_json(raw)
    if release.canonical_bytes() != raw or tuple(ordered_features) != release.preprocessing.ordered_features:
        raise ValueError("noncanonical settings or consumer feature order differs")
    derived = build_release(release.artifacts, reader, verification_sha256=verification_sha256,
                            decision_sha256=decision_sha256, selection_sha256=selection_sha256)
    if derived.canonical_bytes() != raw:
        raise ValueError("saved settings differ from verified source evidence")
    return release
