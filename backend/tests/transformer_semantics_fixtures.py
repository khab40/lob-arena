"""Metadata fixtures only; no events, feature rows, model or cloud execution."""
from app.features.models import FeaturePipelineConfig, LabelSpec, LabelWindow
from app.nebius.object_storage import InventoryEntry
from app.ml.transformer.lineage_inventory import run_members
from app.ml.transformer.verification_spec import canonical, digest


def fixture(index=1):
    member = run_members()[index]
    hybrid = member["mode"] == "hybrid"
    replay = dict(schema_version="canonical_java_replay_bundle_v1", run_id=member["run_id"],
        base_session_id=member["base_session_id"], dataset_id="fixture-dataset", instrument=member["symbol"],
        venue="XNAS", session_id=member["base_session_id"], session_date="2019-10-30",
        mode="hybrid" if hybrid else "historical_control", historical_source_type="nasdaq_itch",
        campaign_id=member["run_id"] if hybrid else None, attack_family=member["family"] if hybrid else None,
        seed=member["seed"] if hybrid else None, price_tick_size=0.0001, quantity_lot_size=1.0,
        tick_interval_ns=500000000, java_engine_version="lob-arena-control-plane-0.1.0",
        canonical_event_stream_hash="a" * 64, event_count=10, snapshot_count=2, alert_count=0,
        label_count=int(hybrid), first_sequence=1, last_sequence=10,
        first_timestamp_ns=100, last_timestamp_ns=1000000100)
    directory = member["replay_key"].removeprefix(member["prefix"]).rsplit("/", 1)[0] + "/"
    inventory, blobs = {}, {}
    for name, filename in (("events", "events.jsonl.gz"), ("snapshots", "snapshots.parquet"),
            ("alerts", "alerts.jsonl"), ("validation", "validation.json")):
        # Inventory references only. There are deliberately no payload files.
        entry = InventoryEntry(path=directory + filename, sha256="b" * 64, size_bytes=123)
        inventory[entry.path] = entry
        replay[name] = dict(name=name, uri=filename, sha256=entry.sha256, size_bytes=entry.size_bytes,
            schema_version="fixture-v1")
    if hybrid:
        raw = canonical(dict(run_id=member["run_id"], campaign_id=member["run_id"],
            scenario_family=member["family"], start_tick=1, end_tick=2)) + b"\n"
        blobs[member["label_key"]] = raw
        replay["ground_truth"] = dict(name="ground_truth", uri="ground-truth.jsonl",
            sha256=digest(raw), size_bytes=len(raw), schema_version="fixture-v1")
    labels = LabelSpec(labels=[LabelWindow(attack_family=member["family"], start_tick=1, end_tick=2)]
        if hybrid else [], default_label=0, default_label_source="research_control_assumption")
    blobs[member["replay_key"]] = canonical(replay)
    config = FeaturePipelineConfig().model_dump(mode="json")
    run = {k: replay[k] for k in ("run_id", "dataset_id", "instrument", "venue", "session_id",
        "session_date", "seed", "price_tick_size", "quantity_lot_size", "tick_interval_ns", "historical_source_type")}
    run["source_type"] = "hybrid" if hybrid else "nasdaq_itch"
    feature = dict(schema_version="feature_stream_run_metadata_v1", feature_schema_version="lob_features_v2",
        feature_config_hash=digest(canonical(config)), run=run, config=config,
        input=dict(java_canonical_event_stream_hash=replay["canonical_event_stream_hash"],
            replay_manifest_sha256=digest(blobs[member["replay_key"]]),
            canonical_java_replay_bundle=replay["schema_version"], java_engine_version=replay["java_engine_version"],
            canonical_event_count=10, first_sequence=1, last_sequence=10, first_timestamp_ns=100,
            last_timestamp_ns=1000000100, feature_label_schema_version="feature_labels_v2",
            feature_label_spec_sha256=labels.spec_hash(), feature_label_window_count=int(hybrid),
            negative_label_source="research_control_assumption", negative_label_scope="public_sample_research_only",
            independently_verified_clean=False, feature_checkpoint_count=2),
        output=dict(feature_file="features.parquet", feature_file_sha256="c" * 64,
            feature_file_size_bytes=321, row_count=2, valid_row_count=2, invalid_row_count=0))
    entry = InventoryEntry(path=f"features/{member['run_id']}/features.parquet", sha256="c" * 64, size_bytes=321)
    inventory[entry.path] = entry
    blobs[member["feature_key"]] = canonical(feature)
    inventories = {member["prefix"]: inventory}
    reseal(member, blobs, inventories)
    return member, blobs, inventories


def reseal(member, blobs, inventories):
    """Model producer-authenticated but semantically conflicting metadata."""
    for key, raw in blobs.items():
        relative = key.removeprefix(member["prefix"])
        inventories[member["prefix"]][relative] = InventoryEntry(path=relative, sha256=digest(raw), size_bytes=len(raw))
