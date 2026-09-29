import json

import pytest

pytest.importorskip("numpy")

from app.ml.transformer.lineage_semantics import verify_run  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402
from transformer_semantics_fixtures import fixture, reseal  # noqa: E402


def check(member, blobs, inventories):
    return verify_run(member, blobs, inventories, dataset_id="fixture-dataset", stream_sha="a" * 64,
        feature_config_sha=json.loads(blobs[member["feature_key"]])["feature_config_hash"])


@pytest.mark.parametrize("index", range(30))
def test_every_control_and_hybrid_domain_without_payloads(index):
    member, blobs, inventories = fixture(index)
    result = check(member, blobs, inventories)
    assert result["run_id"] == member["run_id"]
    assert len(result["label_windows"]) == (member["mode"] == "hybrid")
    assert result["event_stream_sha256"] != result["replay_file_sha256"]
    assert result["negative_label_source"] == "research_control_assumption"
    assert result["independently_verified_clean"] is False


@pytest.mark.parametrize("section,field,value", [
    ("run", "dataset_id", "another-dataset"), ("run", "session_id", "another-session"),
    ("run", "source_type", "synthetic"), ("run", "seed", 42),
    ("input", "replay_manifest_sha256", "a" * 64),
    ("input", "java_canonical_event_stream_hash", "d" * 64),
    ("input", "feature_label_spec_sha256", "d" * 64),
    ("input", "negative_label_source", "independently_clean"),
    ("input", "independently_verified_clean", 0),
    ("input", "first_sequence", True), ("input", "feature_checkpoint_count", 3),
    ("output", "feature_file", "../features.parquet"),
    ("output", "feature_file_sha256", "d" * 64), ("output", "feature_file_size_bytes", 322),
    ("output", "invalid_row_count", 1), ("output", "valid_row_count", 1),
    ("output", "row_count", True), ("config", "depth_levels", 99),
])
def test_authenticated_feature_contradictions_fail(section, field, value):
    member, blobs, inventories = fixture()
    feature = json.loads(blobs[member["feature_key"]])
    feature[section][field] = value
    blobs[member["feature_key"]] = canonical(feature)
    reseal(member, blobs, inventories)
    with pytest.raises(ValueError):
        check(member, blobs, inventories)


@pytest.mark.parametrize("field,value", [("run_id", "other"), ("campaign_id", "other"),
    ("scenario_family", "other"), ("start_tick", True), ("end_tick", -1)])
def test_authenticated_label_contradictions_fail(field, value):
    member, blobs, inventories = fixture()
    label = json.loads(blobs[member["label_key"]])
    label[field] = value
    blobs[member["label_key"]] = canonical(label)
    replay = json.loads(blobs[member["replay_key"]])
    from app.ml.transformer.verification_spec import digest
    replay["ground_truth"].update(sha256=digest(blobs[member["label_key"]]), size_bytes=len(blobs[member["label_key"]]))
    blobs[member["replay_key"]] = canonical(replay)
    reseal(member, blobs, inventories)
    with pytest.raises(ValueError):
        check(member, blobs, inventories)


@pytest.mark.parametrize("field,value", [("dataset_id", "other"), ("venue", "OTHER"),
    ("session_date", "2019-10-29"), ("canonical_event_stream_hash", "d" * 64)])
def test_authenticated_replay_contradictions_fail(field, value):
    member, blobs, inventories = fixture()
    replay = json.loads(blobs[member["replay_key"]])
    replay[field] = value
    blobs[member["replay_key"]] = canonical(replay)
    reseal(member, blobs, inventories)
    with pytest.raises(ValueError, match="replay identity"):
        check(member, blobs, inventories)


def test_unsealed_metadata_and_referenced_payload_mismatch_fail():
    member, blobs, inventories = fixture()
    blobs[member["feature_key"]] += b" "
    with pytest.raises(ValueError, match="authenticated inventory"):
        check(member, blobs, inventories)
    reseal(member, blobs, inventories)
    entry = next(e for p, e in inventories[member["prefix"]].items() if p.endswith("events.jsonl.gz"))
    inventories[member["prefix"]][entry.path] = entry.model_copy(update={"sha256": "d" * 64})
    with pytest.raises(ValueError, match="artifact reference"):
        check(member, blobs, inventories)
