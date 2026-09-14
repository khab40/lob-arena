from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("lightgbm")

from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.c4_replay_evidence import C4CheckpointLocation, C4ComparisonPackage, paired_observations  # noqa: E402
from app.ml.lightgbm.contracts import (  # noqa: E402
    ArtifactDigest,
    DetectorPredictionsManifest,
    FoldFeatureInput,
    GovernedModelBinding,
)
from app.ml.lightgbm.scoring import PREDICTION_ARROW_SCHEMA  # noqa: E402
from test_canonical_evaluation_bundle import _bundle  # noqa: E402


def _digest(path, root, name, schema):
    return ArtifactDigest(
        logical_name=name,
        uri=str(path.relative_to(root)),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        schema_version=schema,
    )


def fixture(tmp_path, *, changed_feature=None, changed_prediction=None):
    replay_root = tmp_path / "replay"
    replay_root.mkdir()
    replay = _bundle(replay_root)
    metadata = json.loads(replay.read_text())
    alerts = replay_root / "alerts.jsonl"
    alerts.write_text(json.dumps(dict(run_id="run-1", campaign_id="campaign-1", detector="Layering", tick=2)) + "\n")
    metadata["alerts"].update(sha256=sha256_file(alerts), size_bytes=alerts.stat().st_size)
    replay.write_text(json.dumps(metadata))
    feature = dict(
        sequence=2,
        tick=2,
        prediction_timestamp_ns=200,
        run_id="run-1",
        label=1,
        label_source="synthetic_scenario",
        attack_family="layering_like",
        attack_phase="pressure_build",
        instrument="SPY",
        source_type="hybrid",
        session_id="regular",
    )
    prediction = {key: value for key, value in feature.items() if key not in {"tick", "label_source"}} | dict(
        prediction_row_id="prediction-row-1",
        fold="test",
        base_session_id="base-1",
        campaign_id="campaign-1",
        raw_probability=0.9,
        calibrated_probability=0.9,
        threshold=0.5,
        alert=True,
    )
    features = tmp_path / "features.parquet"
    pq.write_table(pa.Table.from_pylist([feature | (changed_feature or {})]), features)
    predictions = tmp_path / "predictions.parquet"
    pq.write_table(
        pa.Table.from_pylist([prediction | (changed_prediction or {})], schema=PREDICTION_ARROW_SCHEMA), predictions
    )
    feature_artifact = _digest(features, tmp_path, "features", "lob_features_v2")
    shard = SimpleNamespace(
        run_id="run-1",
        base_session_id="base-1",
        campaign_id="campaign-1",
        replay_manifest_sha256=metadata["canonical_event_stream_hash"],
        rows=feature_artifact,
        supervised_row_count=1,
    )
    binding = GovernedModelBinding(
        model_id="test-model",
        training_run_id="training",
        protocol_id="test-protocol",
        protocol_hash="a" * 64,
        corpus_id="test-corpus",
        corpus_hash="b" * 64,
        split_id="test-split",
        assignment_hash="c" * 64,
        feature_schema_version="lob_features_v2",
        feature_config_hash="d" * 64,
    )
    manifest = DetectorPredictionsManifest(
        prediction_run_id="test-predictions",
        binding=binding,
        calibration_id="calibration",
        created_at=datetime.now(UTC),
        fold="test",
        operating_mode="balanced",
        threshold=0.5,
        row_count=1,
        alert_count=1,
        input_features=(
            FoldFeatureInput(
                fold="test", artifact=feature_artifact, fold_membership_hash="e" * 64, session_count=1, row_count=1
            ),
        ),
        predictions=_digest(predictions, tmp_path, "predictions", "detector_prediction_rows_v1"),
    )
    return dict(
        projection=SimpleNamespace(shards=(shard,)),
        artifact_root=tmp_path,
        predictions=manifest,
        replay_paths={"run-1": replay},
        coverage={},
    )


def test_rules_and_predictions_join_to_the_same_verified_canonical_snapshot(tmp_path):
    arguments = fixture(tmp_path)
    rows = list(paired_observations(**arguments))
    assert len(rows) == 1
    assert rows[0]["rules_alert"] is True
    assert rows[0]["label_source"] == "synthetic_scenario"
    assert arguments["coverage"]["paired_observation_count"] == 1
    assert arguments["coverage"]["canonical_event_count"] == 2


@pytest.mark.parametrize("change", [{"tick": 1}, {"prediction_timestamp_ns": 201}, {"sequence": 1}])
def test_feature_identity_must_match_canonical_event(tmp_path, change):
    with pytest.raises(ValueError, match="canonical snapshot"):
        list(paired_observations(**fixture(tmp_path, changed_feature=change)))


def test_prediction_label_must_match_original_projection(tmp_path):
    with pytest.raises(ValueError, match="metadata differ"):
        list(paired_observations(**fixture(tmp_path, changed_prediction={"label": 0})))


def test_replay_stream_hash_is_verified_after_yielded_rows(tmp_path):
    arguments = fixture(tmp_path)
    replay = arguments["replay_paths"]["run-1"]
    events = replay.parent / "events.jsonl"
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    rows[0]["quantity"] = 11
    events.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest = json.loads(replay.read_text())
    manifest["events"].update(sha256=sha256_file(events), size_bytes=events.stat().st_size)
    replay.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="stream hash"):
        list(paired_observations(**arguments))


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a//b", "a/./b", "."])
def test_comparison_checkpoint_cannot_escape_its_package(path):
    with pytest.raises(ValueError):
        C4CheckpointLocation(source_uri="s3://source/checkpoint", relative_root=path)


def test_incomplete_comparison_package_is_rejected():
    with pytest.raises(ValueError, match="exactly 27"):
        C4ComparisonPackage(
            preparation=dict(logical_name="preparation", uri="preparation.json", sha256="a" * 64, size_bytes=1),
            checkpoints=(),
        )


def test_original_27_checkpoint_inventory_binding_and_tamper_detection(tmp_path):
    from itertools import product
    from app.market_data.preparation import PreparationManifest
    from app.market_data.preparation_checkpoints import (
        CheckpointReference,
        ComparisonCheckpoint,
        inventory_evidence,
    )
    from app.ml.lightgbm.c4_replay_evidence import verified_replay_paths
    from app.nebius.object_storage import publish_local_result

    references, locations = [], []
    symbols = ("AAPL", "MSFT", "NVDA")
    families = ("spoofing_like_wall", "layering_like", "quote_stuffing")
    for number, (symbol, family, seed) in enumerate(product(symbols, families, (41, 42, 43)), 1):
        stage = tmp_path / f"stage-{number}"
        stage.mkdir()
        relative = f"replays/xnas-2019-12-30-{symbol.lower()}/comparisons/{family}-s{seed}"
        include_control = family == families[0] and seed == 41
        for mode in ("hybrid", "control") if include_control else ("hybrid",):
            path = stage / relative / mode / "manifest.json"
            path.parent.mkdir(parents=True)
            # This test exercises checkpoint inventories; replay parsing/join
            # is separately tested using real canonical streams above.
            path.write_text("{}")
        digest, count, size = inventory_evidence(stage)
        checkpoint = ComparisonCheckpoint(
            binding_sha256="a" * 64,
            comparison_number=number,
            symbol=symbol,
            attack_family=family,
            seed=seed,
            control_run_id=f"control-{symbol}",
            control_event_stream_sha256="b" * 64,
            hybrid_run_id=f"hybrid-{number}",
            hybrid_event_stream_sha256="c" * 64,
            includes_control_artifacts=include_control,
            payload_inventory_sha256=digest,
            payload_file_count=count,
            payload_size_bytes=size,
        )
        (stage / "checkpoint.json").write_bytes(checkpoint.canonical_bytes())
        target = tmp_path / f"checkpoint-{number}"
        publish_local_result(stage, target.as_uri())
        uri = f"s3://synthetic/checkpoint-{number}"
        references.append(
            CheckpointReference(
                kind="comparison",
                uri=uri,
                checkpoint_sha256=checkpoint.canonical_hash(),
                payload_inventory_sha256=digest,
                payload_file_count=count,
                payload_size_bytes=size,
            )
        )
        locations.append(C4CheckpointLocation(source_uri=uri, relative_root=target.name))
    preparation = PreparationManifest(
        run_id="synthetic-preparation",
        source_filename="synthetic.gz",
        source_sha256="d" * 64,
        source_manifest_sha256="e" * 64,
        parser_version="synthetic",
        parser_config_sha256="f" * 64,
        itch_message_counts={"S": 2},
        system_event_count=2,
        symbols=symbols,
        dataset_ids={s: s for s in symbols},
        control_run_ids={s: f"control-{s}" for s in symbols},
        campaign_run_ids=tuple(f"hybrid-{n}" for n in range(1, 28)),
        checkpoint_binding_sha256="a" * 64,
        normalized_checkpoint=references[0].model_copy(update={"kind": "normalized"}),
        comparison_checkpoints=tuple(references),
        checkpoint_payload_bytes=sum(r.payload_size_bytes for r in references),
        created_at=datetime.now(UTC),
    )
    path = tmp_path / "preparation.json"
    path.write_bytes(preparation.canonical_bytes())
    package = C4ComparisonPackage(
        preparation=dict(
            logical_name="preparation", uri=path.name, sha256=sha256_file(path), size_bytes=path.stat().st_size
        ),
        checkpoints=tuple(locations),
    )
    package_path = tmp_path / "comparison.json"
    package_path.write_text(package.model_dump_json())
    source = SimpleNamespace(fold="test", trade_date="2019-12-30", preparation_manifest_sha256=sha256_file(path))
    root = SimpleNamespace(sources=(source,))
    replays = verified_replay_paths(package_path, root=root)
    assert len(replays) == 30
    assert all(p.is_file() for p in replays.values())
    next(iter(replays.values())).write_text('{"tampered":true}')
    with pytest.raises(ValueError):
        verified_replay_paths(package_path, root=root)
