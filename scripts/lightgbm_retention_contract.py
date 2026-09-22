"""Independent, metadata-only expectations for candidate inventory v1."""

import hashlib
import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit


def require(ok, message):
    if not ok:
        raise ValueError(message)


def relative(value):
    require(isinstance(value, str) and bool(value), "empty path")
    require(re.fullmatch(r"[A-Za-z0-9_./-]+", value), "unsupported path characters")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts, "unsafe path")
    require(str(path) == value and value != ".", "noncanonical path")
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate metadata key")
        result[key] = value
    return result


def decode(raw):
    def invalid(_):
        raise ValueError("nonfinite JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def s3_uri(value, bucket):
    parsed = urlsplit(value)
    require(parsed.scheme == "s3" and parsed.netloc == bucket, "unapproved S3 bucket")
    require(not parsed.query and not parsed.fragment, "S3 URI query or fragment")
    relative(parsed.path.removeprefix("/"))
    require("test" not in parsed.path.split("/") and "final" not in parsed.path.split("/"),
            "final/test path excluded")
    return parsed.path.removeprefix("/")


def load_inventory(raw, anchor, results_bucket, input_bucket):
    require(len(raw) <= 4 * 1024**2, "inventory too large")
    require(re.fullmatch(r"[0-9a-f]{64}", anchor), "invalid inventory anchor")
    require(hashlib.sha256(raw).hexdigest() == anchor, "inventory anchor mismatch")
    inv = decode(raw)
    require(inv["schema_version"] == "lightgbm_candidate_inventory_v1", "inventory schema")
    root = inv["result_uri"]
    require("/development/" in root, "development result prefix required")
    s3_uri(root, results_bucket)
    s3_uri(inv["lineage"]["input_release_uri"], input_bucket)
    require(re.fullmatch(r"[0-9a-f]{32}", inv["lineage"]["mlflow_run_id"]), "run ID")
    objects = inv["result_objects"]
    require(0 < len(objects) <= 500, "object count limit")
    seen = set()
    for obj in objects:
        relative(obj["path"])
        require(obj["path"] not in seen, "duplicate object")
        seen.add(obj["path"])
        require(obj["uri"] == root + "/" + obj["path"], "object outside result prefix")
        s3_uri(obj["uri"], results_bucket)
        require(re.fullmatch(r"[0-9a-f]{64}", obj["sha256"]), "invalid object hash")
        require(type(obj["size_bytes"]) is int and 0 <= obj["size_bytes"] <= 16 * 1024**2,
                "object size limit")
    require({"SUCCESS", "checksums.sha256"} <= seen, "missing completion markers")
    require(sum(o["size_bytes"] for o in objects) <= 64 * 1024**2, "total size limit")
    for path in inv["artifact_roles"].values():
        require(path in seen, "artifact role missing from inventory")
    require({x["fold"] for x in inv["lineage"]["feature_inputs"]} == {"train", "validation"},
            "development folds required")
    return inv


def expected_tracking(inv):
    lineage, config = inv["lineage"], inv["configuration"]
    references = lineage["input_references"]
    if references["kind"] == "tabular-projection":
        suffix = references["projection_artifact_root"]
    elif references["kind"] == "governed-feature-release":
        suffix = references["feature_artifact_root"]
    else:
        raise ValueError("unsupported development input kind")
    source_root = lineage["input_release_uri"].rstrip("/") + "/" + relative(suffix)
    tags = {**lineage["binding"], "feature_release_id": lineage["feature_release_id"],
            "feature_release_sha256": lineage["feature_release_sha256"],
            "git_commit": lineage["training_git_commit"], "governance_state": "validation_frozen",
            "test_accessed": "false", "raw_rows_uploaded_to_mlflow": "false",
            "experiment_hash": inv["experiment_sha256"],
            "campaign_id": inv["selection"]["campaign_id"], "request_run_id": lineage["run_id"]}
    experiment = config["experiment"]
    params = {**experiment["hyperparameters"], "training_seed": config["training_seed"],
              "preprocessing": config["preprocessing"]["mode"],
              "class_weight_strategy": config["class_weights"]["strategy"],
              "base_session_weighting": config["data_policy"]["base_session_weighting"],
              "calibration_method": config["calibration"]["method"],
              "ordered_feature_count": len(config["ordered_features"]),
              "excluded_features": json.dumps(experiment["excluded_features"], separators=(",", ":")),
              **{k: experiment[k] for k in ("operating_mode", "precision_floor", "recall_floor")}}
    metrics = {"best_iteration": config["early_stopping"]["best_iteration"],
               "validation_binary_logloss": config["early_stopping"]["best_score"],
               "mlflow_dataset_input_count": len(lineage["feature_inputs"])}
    for point in config["operating_points"]:
        metrics[point["mode"] + "_threshold"] = point["threshold"]
        for key in ("precision", "recall", "f1"):
            metrics[point["mode"] + "_" + key] = point["validation_metrics"][key]
    inputs = []
    for item in lineage["feature_inputs"]:
        art = item["artifact"]
        name = "-".join((lineage["feature_release_id"], item["fold"], art["logical_name"]))
        if len(name) > 255:
            name = name[:230] + "-" + hashlib.sha256(name.encode()).hexdigest()[:24]
        inputs.append({"name": name, "digest": "sha256:" + art["sha256"][:29],
                       "source": source_root + "/" + relative(art["uri"]),
                       "tags": {"fold": item["fold"], "row_count": str(item["row_count"]),
                                "session_count": str(item["session_count"]),
                                "fold_membership_sha256": item["fold_membership_hash"],
                                "feature_release_id": lineage["feature_release_id"],
                                "feature_release_sha256": lineage["feature_release_sha256"],
                                "schema_version": art["schema_version"], "digest_algorithm": "sha256",
                                "artifact_sha256": art["sha256"], "raw_rows_uploaded_to_mlflow": "false",
                                "mlflow.data.context": "training" if item["fold"] == "train" else "validation"}})
    return tags, {k: str(v) for k, v in params.items()}, metrics, inputs


def tracking_mismatches(inv, run):
    import math
    tags, params, metrics, inputs = expected_tracking(inv)
    failures = []
    info = run["info"]
    for key, expected in {"run_id": inv["lineage"]["mlflow_run_id"],
                          "status": "FINISHED", "lifecycle_stage": "active"}.items():
        if info.get(key) != expected:
            failures.append("info." + key)
    data = run.get("data", {})
    for category, expected in (("tags", tags), ("params", params), ("metrics", metrics)):
        actual = pairs((x["key"], x["value"]) for x in data.get(category, []))
        for key, value in expected.items():
            observed = actual.get(key)
            matches = (isinstance(observed, (int, float)) and not isinstance(observed, bool)
                       and math.isclose(observed, value, rel_tol=1e-12, abs_tol=1e-15)) if category == "metrics" else observed == value
            if not matches:
                failures.append(category + "." + key)
    actual_inputs = {}
    for item in run.get("inputs", {}).get("dataset_inputs", []):
        ds = item["dataset"]
        require(ds["name"] not in actual_inputs, "duplicate dataset name")
        actual_inputs[ds["name"]] = item
    if set(actual_inputs) != {x["name"] for x in inputs}:
        failures.append("inputs.names")
    for expected in inputs:
        item = actual_inputs.get(expected["name"])
        if item is None:
            continue
        ds = item["dataset"]
        actual_tags = pairs((x["key"], x["value"]) for x in item.get("tags", []))
        source = decode(ds["source"])
        checks = {"digest": ds.get("digest") == expected["digest"],
                  "source_type": ds.get("source_type") == "s3",
                  "source_uri": source.get("uri") == expected["source"],
                  **{"tags." + k: actual_tags.get(k) == v for k, v in expected["tags"].items()}}
        for field, matches in checks.items():
            if not matches:
                # Emit field names only, never remote values or source URIs.
                failures.append("inputs." + expected["name"] + "." + field)
    return failures
