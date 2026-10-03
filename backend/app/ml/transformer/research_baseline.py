"""Read the frozen development predictions; never load or score a model."""
import io
import json

import numpy as np
import pyarrow.parquet as pq

from app.market_data.projections import supervised_row_id

from .role_rows import verify_rows
from .verification_spec import canonical, digest

PREDICTIONS_SHA = "828e261801aa36ab55c02fbe199bbd00ce44b8cef64dd0e0a183d0f6e0913f76"
CALIBRATION_SHA = "a27d88091988dc6e504e3e84d57c985f774f5865ea534882ba7fe87c6ea49e30"
MODEL_SHA = "e8c4134063bcb346d17b4839cfa21e458ad2d65bab1d2f240a15267d0dc7f2f3"
CANDIDATE_SHA = "5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff"


def load(predictions_raw, calibration_raw, metadata):
    if (len(predictions_raw) != 618114 or digest(predictions_raw) != PREDICTIONS_SHA
            or len(calibration_raw) > 65536 or digest(calibration_raw) != CALIBRATION_SHA):
        raise ValueError("baseline differs from the frozen development candidate")
    calibration = json.loads(calibration_raw)
    if (calibration["fit_fold"] != "validation" or calibration["test_fold_accessed"]
            or calibration["input_predictions"]["sha256"] != PREDICTIONS_SHA
            or calibration["row_count"] != 9210):
        raise ValueError("baseline calibration lineage differs")
    rows = pq.read_table(io.BytesIO(predictions_raw)).to_pylist()
    if len(rows) != 9210 or any(row["fold"] != "validation" for row in rows):
        raise ValueError("baseline predictions leave the development fold")
    shards = {shard["run_id"]: shard for group in metadata["groups"] for shard in group["shards"]}
    for row in rows:
        identity = f'{row["run_id"]}|{row["prediction_timestamp_ns"]}|{row["sequence"]}'.encode()
        if row["prediction_row_id"] != digest(identity) or row["run_id"] not in shards:
            raise ValueError("invalid baseline prediction identity")
        row["governed_target_id"] = supervised_row_id(root_sha256=metadata["root_identity_sha256"],
            assignment_sha256=calibration["binding"]["assignment_hash"],
            replay_sha256=shards[row["run_id"]]["replay_manifest_sha256"], run_id=row["run_id"],
            sequence=row["sequence"], timestamp_ns=row["prediction_timestamp_ns"])
    ledger = b"".join(canonical({"run_id": row["run_id"], "target_id": row["governed_target_id"],
                                 "label": row["label"]}) + b"\n" for row in rows)
    coverage = verify_rows(ledger, metadata)
    probabilities = np.array([row["raw_probability"] for row in rows], dtype=np.float64)
    if not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("invalid frozen baseline probabilities")
    thresholds = {point["mode"]: point["threshold"] for point in calibration["operating_points"]}
    if (len(calibration["operating_points"]) != 3
            or set(thresholds) != {"high_precision", "balanced", "high_recall"}
            or any(not 0 <= value <= 1 for value in thresholds.values())):
        raise ValueError("invalid frozen baseline operating points")
    roles = {shard["run_id"]: group["role"] for group in metadata["groups"] for shard in group["shards"]}
    selected = {}
    for role in ("selection", "calibration", "operating_point"):
        indices = [i for i, row in enumerate(rows) if roles[row["run_id"]] == role]
        selected[role] = {"target_ids": tuple(rows[i]["governed_target_id"] for i in indices),
            "labels": np.array([rows[i]["label"] for i in indices]), "raw_probabilities": probabilities[indices],
            "frozen_calibration": calibration["parameters"],
            "families": tuple(rows[i]["attack_family"] or "control" for i in indices)}
    return selected, thresholds, {"candidate_sha256": CANDIDATE_SHA, "model_sha256": MODEL_SHA,
        "predictions_sha256": PREDICTIONS_SHA, "calibration_sha256": CALIBRATION_SHA,
        "coverage": coverage, "model_loaded": False, "rescoring": False,
        "calibration_application": "apply_frozen_isotonic_mapping_in_gpu_job_without_refitting",
        "limitation": "LightGBM calibration and thresholds used the entire validation fold"}


def align(split, baseline):
    if (split.target_ids != baseline["target_ids"]
            or not np.array_equal(split.labels, baseline["labels"])):
        raise ValueError("frozen baseline differs from actual governed Transformer targets/labels")
