"""Cross-artifact checks on already authenticated metadata; never opens payloads."""
import json

from app.evaluation.canonical_bundle import CanonicalJavaReplayManifest
from app.features.io import ground_truth_window
from app.features.models import LabelSpec
from .lineage_inventory import verify_member
from .role_provenance import DATE
from .verification_spec import canonical, digest


def artifact(reference, relative, inventory):
    entry = inventory.get(relative)
    if entry is None or (reference.sha256, reference.size_bytes) != (entry.sha256, entry.size_bytes):
        raise ValueError("replay artifact reference differs from authenticated inventory")


def label_spec(replay, raw):
    if replay.mode == "historical_control":
        if raw is not None:
            raise ValueError("control replay cannot supply synthetic labels")
        windows = []
    else:
        if raw is None:
            raise ValueError("hybrid replay lacks label-window metadata")
        rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
        if len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError("hybrid replay requires exactly one ground-truth record")
        row = rows[0]
        if (row.get("run_id") != replay.run_id or row.get("campaign_id") != replay.campaign_id
                or row.get("scenario_family") != replay.attack_family):
            raise ValueError("ground-truth identity differs from replay")
        windows = [ground_truth_window(row)]
    return LabelSpec(labels=windows, default_label=0, default_label_source="research_control_assumption")


def verify_run(member, blobs, inventories, *, dataset_id, stream_sha, feature_config_sha):
    """Caller must authenticate inventories against the frozen preparation first."""
    keys = [member["replay_key"], member["feature_key"]]
    if member["label_key"]:
        keys.append(member["label_key"])
    for key in keys:
        verify_member(key, blobs[key], inventories)
    replay_raw = blobs[member["replay_key"]]
    replay = CanonicalJavaReplayManifest.model_validate_json(replay_raw)
    hybrid = member["mode"] == "hybrid"
    if (replay.run_id != member["run_id"] or replay.base_session_id != member["base_session_id"]
            or replay.session_id != member["base_session_id"] or str(replay.session_date) != DATE
            or replay.dataset_id != dataset_id or replay.instrument != member["symbol"]
            or replay.venue != "XNAS" or replay.historical_source_type != "nasdaq_itch"
            or replay.mode != ("hybrid" if hybrid else "historical_control")
            or replay.campaign_id != (member["run_id"] if hybrid else None)
            or replay.seed != (member["seed"] if hybrid else None)
            or replay.attack_family != (member["family"] if hybrid else None)
            or replay.canonical_event_stream_hash != stream_sha):
        raise ValueError("replay identity differs from frozen comparison domain")
    inventory = inventories[member["prefix"]]
    directory = member["replay_key"].removeprefix(member["prefix"]).rsplit("/", 1)[0] + "/"
    for name, allowed in (("events", {"events.jsonl", "events.jsonl.gz"}),
            ("snapshots", {"snapshots.parquet"}), ("alerts", {"alerts.jsonl"}),
            ("validation", {"validation.json"})):
        reference = getattr(replay, name)
        if reference.uri not in allowed:
            raise ValueError("replay reference escaped its exact artifact names")
        artifact(reference, directory + reference.uri, inventory)
    label_raw = blobs[member["label_key"]] if hybrid else None
    if hybrid:
        if replay.ground_truth.uri != "ground-truth.jsonl":
            raise ValueError("ground truth escaped its exact metadata name")
        artifact(replay.ground_truth, directory + "ground-truth.jsonl", inventory)
    labels = label_spec(replay, label_raw)
    feature = json.loads(blobs[member["feature_key"]])
    verify_feature(feature, replay, digest(replay_raw), labels, feature_config_sha, inventory)
    return {"run_id": replay.run_id, "instrument": replay.instrument, "dataset_id": replay.dataset_id,
        "base_session_id": replay.base_session_id, "campaign_id": replay.campaign_id,
        "event_stream_sha256": stream_sha, "replay_file_sha256": digest(replay_raw),
        "feature_metadata_sha256": digest(blobs[member["feature_key"]]),
        "feature_row_count": feature["output"]["row_count"],
        "label_spec_sha256": labels.spec_hash(), "label_windows": [w.model_dump(mode="json") for w in labels.labels],
        "negative_label_source": "research_control_assumption", "independently_verified_clean": False}


def verify_feature(feature, replay, replay_file_sha, labels, config_sha, inventory):
    if not isinstance(feature, dict):
        raise ValueError("feature metadata must be an object")
    run, inputs, output, config = (feature.get(k) for k in ("run", "input", "output", "config"))
    if not all(isinstance(v, dict) for v in (run, inputs, output, config)):
        raise ValueError("feature metadata omits required objects")
    expected_run = {name: getattr(replay, name) for name in ("run_id", "dataset_id", "instrument", "venue",
        "session_id", "seed", "price_tick_size", "quantity_lot_size", "tick_interval_ns", "historical_source_type")}
    expected_run.update(session_date=str(replay.session_date),
        source_type="hybrid" if replay.mode == "hybrid" else "nasdaq_itch")
    if any(k not in run or isinstance(run[k], bool) or run[k] != v for k, v in expected_run.items()):
        raise ValueError("feature run identity differs from replay")
    expected_input = {"java_canonical_event_stream_hash": replay.canonical_event_stream_hash,
        "replay_manifest_sha256": replay_file_sha, "canonical_java_replay_bundle": replay.schema_version,
        "java_engine_version": replay.java_engine_version, "canonical_event_count": replay.event_count,
        "first_sequence": replay.first_sequence, "last_sequence": replay.last_sequence,
        "first_timestamp_ns": replay.first_timestamp_ns, "last_timestamp_ns": replay.last_timestamp_ns,
        "feature_label_schema_version": labels.schema_version, "feature_label_spec_sha256": labels.spec_hash(),
        "feature_label_window_count": len(labels.labels), "negative_label_source": "research_control_assumption",
        "negative_label_scope": "public_sample_research_only", "independently_verified_clean": False}
    if any(k not in inputs or type(inputs[k]) is not type(v) or inputs[k] != v for k, v in expected_input.items()):
        raise ValueError("feature input lineage differs from replay or label definition")
    entry = inventory.get(f"features/{replay.run_id}/features.parquet")
    rows = output.get("row_count")
    if (feature.get("schema_version") != "feature_stream_run_metadata_v1"
            or feature.get("feature_schema_version") != "lob_features_v2"
            or feature.get("feature_config_hash") != config_sha or digest(canonical(config)) != config_sha
            or entry is None or output.get("feature_file") != "features.parquet"
            or output.get("feature_file_sha256") != entry.sha256
            or type(output.get("feature_file_size_bytes")) is not int
            or output.get("feature_file_size_bytes") != entry.size_bytes
            or type(rows) is not int or rows <= 0
            or type(output.get("invalid_row_count")) is not int or output["invalid_row_count"] != 0
            or type(output.get("valid_row_count")) is not int or output["valid_row_count"] != rows
            or type(inputs.get("feature_checkpoint_count")) is not int or inputs["feature_checkpoint_count"] != rows):
        raise ValueError("feature configuration or output differs from frozen inventory")
