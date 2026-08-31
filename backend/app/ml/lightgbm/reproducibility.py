from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import CloudArtifact, LightGbmCloudJobRequest
from app.ml.lightgbm.cloud_runner import FrozenCandidate, verify_wave1_result
from app.ml.lightgbm.contracts import CalibrationManifest, LightGbmTrainingRun
from app.nebius.object_storage import inventory_directory


G5_DETERMINISTIC_FIELDS = (
    "request_equivalence_hash",
    "experiment_hash",
    "input_identity_hash",
    "governed_identity_hash",
    "training_inputs_hash",
    "negative_label_source",
    "image",
    "model_sha256",
    "validation_predictions_sha256",
    "best_iteration",
    "validation_binary_logloss",
    "calibration_parameters_hash",
    "calibration_metrics_hash",
    "operating_points_hash",
    "validation_metrics_sha256",
    "feature_importance_sha256",
    "ordered_features_hash",
    "feature_schema_sha256",
    "reliability_bins_sha256",
    "reliability_diagram_sha256",
    "reproducibility_hash",
)


def compare_g5_results(
    results: list[Path],
    output: Path,
    *,
    collections: list[Path] | None = None,
    allow_fixture_preflight: bool = False,
) -> None:
    """Compare exactly three G5 development results and fail closed on drift.

    Fixture mode validates the comparator itself but emits only a local-preflight
    disposition. A real G5 pass requires three governed results and their three
    independently collected cloud receipts.
    """

    if len(results) != 3:
        raise ValueError("G5 reproducibility requires exactly three results")
    if collections is not None and len(collections) != 3:
        raise ValueError("G5 reproducibility requires exactly three collection receipts")
    receipt_paths: list[Path | None] = list(collections) if collections is not None else [None] * 3
    records = [_g5_result_record(result, collection) for result, collection in zip(results, receipt_paths, strict=True)]
    comparisons = {
        field: {
            "matches": all(record[field] == records[0][field] for record in records[1:]),
            "values": [record[field] for record in records],
        }
        for field in G5_DETERMINISTIC_FIELDS
    }
    governed_inputs = all(
        record["input_kind"] in {"governed-feature-release", "tabular-projection"}
        for record in records
    )
    fixture_inputs = all(record["input_kind"] == "approved-research-fixture" for record in records)
    distinct_run_ids = len({record["run_id"] for record in records}) == 3
    distinct_job_ids = _three_distinct_present(records, "nebius_job_id")
    distinct_mlflow_ids = _three_distinct_present(records, "mlflow_run_id")
    test_isolation = all(record["test_fold_accessed"] is False for record in records)
    deterministic_evidence = all(item["matches"] is True for item in comparisons.values())
    verified_receipts = all(record["collection_receipt_verified"] is True for record in records)
    local_preflight = allow_fixture_preflight and fixture_inputs
    gates = {
        "exactly_three_results": True,
        "development_mode_only": all(record["mode"] == "development" for record in records),
        "governed_projection_bound": governed_inputs,
        "distinct_run_ids": distinct_run_ids,
        "verified_collection_receipts": verified_receipts,
        "distinct_nebius_job_ids": distinct_job_ids,
        "distinct_mlflow_run_ids": distinct_mlflow_ids,
        "test_fold_isolation": test_isolation,
        "deterministic_evidence_matches": deterministic_evidence,
    }
    if local_preflight:
        required = gates["development_mode_only"] and distinct_run_ids and test_isolation and deterministic_evidence
        status = "preflight_passed" if required else "failed"
        disposition = "local_fixture_comparator_preflight_only"
    else:
        required = all(gates.values())
        status = "passed" if required else "failed"
        disposition = "g5_reproducibility_passed" if required else "g5_reproducibility_blocked"
    payload = {
        "schema_version": "lightgbm_wave1_g5_repeat_comparison_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "scope": "local-preflight-only" if local_preflight else "governed-cloud-g5",
        "disposition": disposition,
        "repeat_count": len(records),
        "compared_fields": list(G5_DETERMINISTIC_FIELDS),
        "allowed_to_differ": [
            "cloud_run_id",
            "nebius_job_id",
            "mlflow_run_id",
            "request_sha256",
            "candidate_package_hash",
            "timestamps",
            "runtime",
            "peak_memory",
            "cost",
        ],
        "gates": gates,
        "comparisons": comparisons,
        "runs": records,
    }
    _write_json_once(output, payload)
    if not required:
        failed = ", ".join(name for name, passed in gates.items() if not passed)
        raise ValueError(f"G5 reproducibility gates failed: {failed}")


def _g5_result_record(result: Path, collection_path: Path | None) -> dict[str, object]:
    run = verify_wave1_result(result)
    if run.mode != "development" or run.status != "succeeded":
        raise ValueError("G5 accepts only successful development results")
    request = LightGbmCloudJobRequest.model_validate_json((result / "request.json").read_text(encoding="utf-8"))
    metrics = json.loads((result / "metrics.json").read_text(encoding="utf-8"))
    if not isinstance(metrics, dict) or metrics.get("test_fold_accessed") is not False:
        raise ValueError("G5 result does not prove test-fold isolation")
    artifact_root = result / "artifacts"
    candidate = FrozenCandidate.model_validate_json((result / "candidate.json").read_text(encoding="utf-8"))
    training_path = _verify_candidate_artifact(artifact_root, candidate.training_manifest)
    calibration_path = _verify_candidate_artifact(artifact_root, candidate.calibration_manifest)
    training = LightGbmTrainingRun.model_validate_json(training_path.read_text(encoding="utf-8"))
    calibration = CalibrationManifest.model_validate_json(calibration_path.read_text(encoding="utf-8"))
    if calibration.binding.identity_tuple() != training.binding.identity_tuple():
        raise ValueError("G5 calibration identity does not match training")
    _verify_digest(
        artifact_root / training.model_artifact.uri,
        training.model_artifact.sha256,
        training.model_artifact.size_bytes,
    )
    _verify_digest(
        artifact_root / calibration.input_predictions.uri,
        calibration.input_predictions.sha256,
        calibration.input_predictions.size_bytes,
    )
    derived = {
        name: _verify_candidate_artifact(artifact_root, getattr(candidate, name))
        for name in (
            "validation_metrics",
            "feature_importance",
            "feature_schema",
            "reliability_bins",
            "reliability_diagram",
        )
    }
    collection = _verified_collection_receipt(collection_path, result, request, run.mlflow_run_id)
    nebius_job_id = collection.get("nebius_job_id") if collection else run.nebius_job_id
    mlflow_run_id = collection.get("mlflow_run_id") if collection else run.mlflow_run_id
    if run.nebius_job_id is not None and nebius_job_id != run.nebius_job_id:
        raise ValueError("G5 collection Job ID does not match the cloud result")
    request_payload = request.model_dump(mode="json")
    for volatile in ("run_id", "created_at", "result_uri"):
        request_payload.pop(volatile, None)
    calibration_metrics = {
        "raw": calibration.raw_metrics.model_dump(mode="json"),
        "calibrated": calibration.calibrated_metrics.model_dump(mode="json"),
    }
    return {
        "result_path": str(result.resolve()),
        "collection_path": str(collection_path.resolve()) if collection_path else None,
        "collection_receipt_verified": bool(collection),
        "run_id": run.run_id,
        "mode": run.mode,
        "nebius_job_id": nebius_job_id,
        "mlflow_run_id": mlflow_run_id,
        "request_sha256": run.request_sha256,
        "candidate_package_hash": run.candidate_hash,
        "request_equivalence_hash": _canonical_hash(request_payload),
        "experiment_hash": request.experiment.canonical_hash(),
        "input_kind": request.input.kind,
        "input_identity_hash": request.input.canonical_hash(),
        "governed_identity_hash": _canonical_hash(training.binding.model_dump(mode="json")),
        "training_inputs_hash": _canonical_hash([item.model_dump(mode="json") for item in training.input_features]),
        "negative_label_source": training.data_policy.negative_label_source,
        "image": run.image,
        "model_sha256": training.model_artifact.sha256,
        "validation_predictions_sha256": calibration.input_predictions.sha256,
        "best_iteration": training.early_stopping.best_iteration,
        "validation_binary_logloss": training.early_stopping.best_score,
        "calibration_parameters_hash": _canonical_hash(calibration.parameters.model_dump(mode="json")),
        "calibration_metrics_hash": _canonical_hash(calibration_metrics),
        "operating_points_hash": _canonical_hash(
            [point.model_dump(mode="json") for point in calibration.operating_points]
        ),
        "validation_metrics_sha256": sha256_file(derived["validation_metrics"]),
        "feature_importance_sha256": sha256_file(derived["feature_importance"]),
        "ordered_features_hash": _canonical_hash(list(training.ordered_feature_columns)),
        "feature_schema_sha256": sha256_file(derived["feature_schema"]),
        "reliability_bins_sha256": sha256_file(derived["reliability_bins"]),
        "reliability_diagram_sha256": sha256_file(derived["reliability_diagram"]),
        "reproducibility_hash": run.reproducibility_hash,
        "test_fold_accessed": metrics.get("test_fold_accessed"),
    }


def _verified_collection_receipt(
    path: Path | None,
    result: Path,
    request: LightGbmCloudJobRequest,
    mlflow_run_id: str | None,
) -> dict[str, object]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"G5 collection receipt is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "lightgbm_wave1_collection_v1":
        raise ValueError("G5 collection receipt has the wrong schema")
    expected_inventory_hash = _canonical_hash(inventory_directory(result).model_dump(mode="json"))
    context = payload.get("actual_job_context")
    expected_context = {
        "project_id": request.project_id,
        "image": request.image,
        "platform": request.resource.platform,
        "preset": request.resource.preset,
        "disk_size_gib": request.resource.disk_size_gib,
        "timeout_seconds": request.resource.timeout_seconds,
    }
    if not (
        payload.get("verified") is True
        and payload.get("run_id") == request.run_id
        and payload.get("request_sha256") == request.canonical_hash()
        and payload.get("mlflow_run_id") == mlflow_run_id
        and payload.get("result_sha256") == expected_inventory_hash
        and context == expected_context
    ):
        raise ValueError("G5 collection receipt is not bound to its verified cloud result")
    return payload


def _verify_candidate_artifact(root: Path, artifact: CloudArtifact) -> Path:
    path = (root.resolve() / artifact.uri).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"G5 artifact escapes its result root: {artifact.logical_name}")
    _verify_digest(path, artifact.sha256, artifact.size_bytes)
    return path


def _verify_digest(path: Path, expected_sha256: str, expected_size: int) -> None:
    if not path.is_file() or path.stat().st_size != expected_size or sha256_file(path) != expected_sha256:
        raise ValueError(f"G5 artifact integrity failed: {path.name}")


def _three_distinct_present(records: list[dict[str, object]], field: str) -> bool:
    values = [record[field] for record in records]
    return all(isinstance(value, str) and value for value in values) and len(set(values)) == 3


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json_once(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, allow_nan=False, indent=2, sort_keys=True)
        handle.write("\n")
