"""Bind C4 rules comparisons to original C3 checkpoints and exact snapshot rows."""

from __future__ import annotations

import json
from copy import deepcopy
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Literal

import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, model_validator

from app.evaluation.canonical_bundle import open_canonical_evaluation_stream
from app.market_data.preparation import PreparationManifest
from app.market_data.preparation_checkpoints import ComparisonCheckpoint, inventory_evidence
from app.market_data.projections import FrozenPublicSampleRoot, verify_tabular_projection
from app.ml.lightgbm.artifacts import resolve_verified_artifact, sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile, evaluate_c4_observations
from app.ml.lightgbm.cloud_contracts import CloudArtifact
from app.ml.lightgbm.cloud_runner import FrozenCandidate, _verify_cloud_artifact
from app.ml.lightgbm.contracts import (
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    CalibrationManifest,
    ModelBundleManifest,
)
from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release
from app.ml.lightgbm.scoring import validate_prediction_parquet
from app.nebius.object_storage import verify_complete_result


# One process-local, independently recomputed result. Never populated by scoring.
_VERIFIED_COMPARISON = None


def _reuse_comparison(key, compute):
    global _VERIFIED_COMPARISON
    if _VERIFIED_COMPARISON is None or _VERIFIED_COMPARISON[0] != key:
        result = compute()  # Exceptions never populate the cache.
        _VERIFIED_COMPARISON = (key, deepcopy(result))
    return deepcopy(_VERIFIED_COMPARISON[1])


class C4CheckpointLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_uri: str
    relative_root: str

    @model_validator(mode="after")
    def canonical_path(self):
        path = PurePosixPath(self.relative_root)
        if (
            not self.relative_root
            or path.is_absolute()
            or path.as_posix() != self.relative_root
            or ".." in path.parts
            or "\\" in self.relative_root
            or self.relative_root == "."
        ):
            raise ValueError("checkpoint location must be a canonical relative directory")
        return self


class C4ComparisonPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_c4_comparison_package_v1"] = "g8_c4_comparison_package_v1"
    preparation: CloudArtifact
    checkpoints: tuple[C4CheckpointLocation, ...]

    @model_validator(mode="after")
    def unique_checkpoints(self):
        if (
            len(self.checkpoints) != 27
            or len({item.source_uri for item in self.checkpoints}) != 27
            or len({item.relative_root for item in self.checkpoints}) != 27
        ):
            raise ValueError("C4 comparison requires exactly 27 distinct original checkpoints")
        return self


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("comparison evidence escaped its artifact root")
    return path


def verified_replay_paths(package_path: Path, *, root: FrozenPublicSampleRoot) -> dict[str, Path]:
    """Never regenerate rules: every replay is bound through C3 back to C4."""
    package = C4ComparisonPackage.model_validate_json(package_path.read_bytes())
    evidence_root = package_path.parent.resolve()
    source = next(item for item in root.sources if item.fold == "test")
    if package.preparation.sha256 != source.preparation_manifest_sha256:
        raise ValueError("comparison preparation is not the frozen C4 test preparation")
    preparation_path = _verify_cloud_artifact(evidence_root, package.preparation)
    preparation = PreparationManifest.model_validate_json(preparation_path.read_bytes())
    references = {item.uri: item for item in preparation.comparison_checkpoints}
    if len(references) != 27 or set(references) != {item.source_uri for item in package.checkpoints}:
        raise ValueError("comparison checkpoints differ from the frozen preparation inventory")
    replays = {}
    for location in package.checkpoints:
        reference = references[location.source_uri]
        checkpoint_root = _inside(evidence_root, location.relative_root)
        checkpoint_path = _inside(checkpoint_root, "checkpoint.json")
        if sha256_file(checkpoint_path) != reference.checkpoint_sha256:
            raise ValueError("C3 checkpoint identity differs from the frozen preparation")
        checkpoint = ComparisonCheckpoint.model_validate_json(checkpoint_path.read_bytes())
        if checkpoint.binding_sha256 != preparation.checkpoint_binding_sha256:
            raise ValueError("C3 checkpoint belongs to a different preparation")
        verify_complete_result(checkpoint_root)
        expected = (reference.payload_inventory_sha256, reference.payload_file_count, reference.payload_size_bytes)
        if (
            inventory_evidence(checkpoint_root, exclude_checkpoint=True) != expected
            or (checkpoint.payload_inventory_sha256, checkpoint.payload_file_count, checkpoint.payload_size_bytes)
            != expected
        ):
            raise ValueError("C3 comparison payload no longer matches its frozen inventory")
        session = f"xnas-{source.trade_date}-{checkpoint.symbol.lower()}"
        replay_root = f"replays/{session}/comparisons/{checkpoint.attack_family}-s{checkpoint.seed}"
        entries = [(checkpoint.hybrid_run_id, "hybrid")]
        if checkpoint.includes_control_artifacts:
            entries.append((checkpoint.control_run_id, "control"))
        for run_id, mode in entries:
            if run_id in replays:
                raise ValueError("C3 comparison package duplicates a replay domain")
            replays[run_id] = _inside(checkpoint_root, replay_root + f"/{mode}/manifest.json")
    if len(replays) != 30:
        raise ValueError("C3 comparison package must resolve exactly 30 replay domains")
    return replays


def paired_observations(
    *,
    projection,
    artifact_root: Path,
    predictions: DetectorPredictionsManifest,
    replay_paths: dict[str, Path],
    coverage: dict,
):
    """Disk-backed exact join; exhaust every canonical stream before accepting output."""
    if set(replay_paths) != {shard.run_id for shard in projection.shards}:
        raise ValueError("rules and LightGBM do not cover the same replay domains")
    expected_inputs = {
        (s.rows.uri, s.rows.sha256, s.rows.size_bytes, s.supervised_row_count) for s in projection.shards
    }
    observed_inputs = {
        (s.artifact.uri, s.artifact.sha256, s.artifact.size_bytes, s.row_count) for s in predictions.input_features
    }
    if expected_inputs != observed_inputs or len(predictions.input_features) != len(projection.shards):
        raise ValueError("predictions do not reference the exact C4 feature shards")
    prediction_path = resolve_verified_artifact(predictions.predictions, artifact_root=artifact_root)
    validate_prediction_parquet(prediction_path, manifest=predictions)
    with tempfile.TemporaryDirectory(prefix="g8-c4-paired-") as temporary:
        with sqlite3.connect(str(Path(temporary) / "join.sqlite")) as db:
            db.execute(
                "CREATE TABLE predictions (run TEXT, sequence INTEGER, ts INTEGER, payload TEXT, PRIMARY KEY(run, sequence, ts))"
            )
            for batch in pq.ParquetFile(prediction_path).iter_batches():
                db.executemany(
                    "INSERT INTO predictions VALUES (?, ?, ?, ?)",
                    (
                        (row["run_id"], row["sequence"], row["prediction_timestamp_ns"], json.dumps(row))
                        for row in batch.to_pylist()
                    ),
                )
            db.commit()
            coverage.update(
                canonical_event_count=0,
                paired_observation_count=0,
                raw_rules_alert_count=0,
                rules_alerts_outside_retained_ticks=0,
                campaigns_without_positive_observations=[],
            )
            for shard in projection.shards:
                stream = open_canonical_evaluation_stream(replay_paths[shard.run_id])
                manifest = stream.manifest
                if (
                    manifest.run_id != shard.run_id
                    or manifest.base_session_id != shard.base_session_id
                    or manifest.campaign_id != shard.campaign_id
                    or manifest.canonical_event_stream_hash != shard.replay_manifest_sha256
                ):
                    raise ValueError("canonical replay identity differs from the projected C4 stream")
                rules_ticks = set()
                for alert in stream.alerts:
                    if (
                        type(alert.get("tick")) is not int
                        or alert["tick"] < 0
                        or not isinstance(alert.get("detector"), str)
                        or not alert["detector"]
                    ):
                        raise ValueError("canonical rules alert has no valid detector/tick")
                    rules_ticks.add(alert["tick"])
                db.execute("CREATE TABLE observations (sequence INTEGER PRIMARY KEY, payload TEXT)")
                path = _inside(artifact_root, shard.rows.uri)
                columns = [
                    "sequence",
                    "tick",
                    "prediction_timestamp_ns",
                    "run_id",
                    "label",
                    "label_source",
                    "attack_family",
                    "attack_phase",
                    "instrument",
                    "source_type",
                    "session_id",
                ]
                for batch in pq.ParquetFile(path).iter_batches(columns=columns):
                    db.executemany(
                        "INSERT INTO observations VALUES (?, ?)",
                        ((row["sequence"], json.dumps(row)) for row in batch.to_pylist()),
                    )
                db.commit()
                retained_ticks = set()
                canonical_ticks = set()
                positive_rows = 0
                for event in stream.iter_events():
                    if event.tick is not None:
                        canonical_ticks.add(event.tick)
                    feature = db.execute(
                        "SELECT payload FROM observations WHERE sequence=?", (event.sequence,)
                    ).fetchone()
                    if feature is None:
                        continue
                    feature = json.loads(feature[0])
                    timestamp = (
                        event.exchange_timestamp_ns
                        if event.exchange_timestamp_ns is not None
                        else event.received_timestamp_ns
                    )
                    if (
                        event.event_type != "snapshot"
                        or timestamp != feature["prediction_timestamp_ns"]
                        or event.tick != feature["tick"]
                    ):
                        raise ValueError("C4 feature observation differs from its canonical snapshot")
                    predicted = db.execute(
                        "SELECT payload FROM predictions WHERE run=? AND sequence=? AND ts=?",
                        (shard.run_id, event.sequence, timestamp),
                    ).fetchone()
                    if predicted is None:
                        raise ValueError("canonical C4 observation has no unique prediction")
                    row = json.loads(predicted[0])
                    if any(row[key] != feature[key] for key in columns if key not in {"tick", "label_source"}):
                        raise ValueError("prediction and C4 observation metadata differ")
                    if row["base_session_id"] != shard.base_session_id or row["campaign_id"] != shard.campaign_id:
                        raise ValueError("prediction replay domain differs from C4")
                    db.execute("DELETE FROM observations WHERE sequence=?", (event.sequence,))
                    db.execute(
                        "DELETE FROM predictions WHERE run=? AND sequence=? AND ts=?",
                        (shard.run_id, event.sequence, timestamp),
                    )
                    retained_ticks.add(event.tick)
                    positive_rows += feature["label"] == 1
                    coverage["paired_observation_count"] += 1
                    yield row | {"rules_alert": event.tick in rules_ticks, "label_source": feature["label_source"]}
                # iter_events verifies full count, chronology and canonical hash on exhaustion.
                if not rules_ticks <= canonical_ticks:
                    raise ValueError("canonical rules alerts reference ticks absent from the replay")
                if db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]:
                    raise ValueError("C4 projection contains observations absent from canonical replay")
                db.execute("DROP TABLE observations")
                coverage["canonical_event_count"] += manifest.event_count
                coverage["raw_rules_alert_count"] += len(stream.alerts)
                coverage["rules_alerts_outside_retained_ticks"] += sum(
                    a["tick"] not in retained_ticks for a in stream.alerts
                )
                if shard.campaign_id and not positive_rows:
                    coverage["campaigns_without_positive_observations"].append(shard.campaign_id)
            if db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]:
                raise ValueError("predictions contain rows outside the C4 comparison observations")


def evaluate_c4_release(
    *,
    profile: C4EvaluationProfile,
    root: FrozenPublicSampleRoot,
    projection_path: Path,
    comparison_path: Path,
    artifact_root: Path,
    candidate_path: Path,
    predictions: DetectorPredictionsManifest,
    reuse_verified_comparison: bool = False,
) -> dict:
    if sha256_file(candidate_path) != profile.candidate_sha256:
        raise ValueError("C4 evaluation profile does not bind the frozen candidate")
    candidate = FrozenCandidate.model_validate_json(candidate_path.read_bytes())
    if candidate.test_fold_accessed or candidate.experiment.operating_mode != predictions.operating_mode:
        raise ValueError("C4 evaluation must retain the pre-test candidate and operating mode")
    training = LightGbmTrainingRun.model_validate_json(
        _verify_cloud_artifact(artifact_root, candidate.training_manifest).read_bytes()
    )
    calibration = CalibrationManifest.model_validate_json(
        _verify_cloud_artifact(artifact_root, candidate.calibration_manifest).read_bytes()
    )
    bundle = ModelBundleManifest.model_validate_json((artifact_root / "bundle/model-bundle.json").read_bytes())
    verify_complete_lightgbm_v1_release(
        artifact_root, training=training, calibration=calibration, predictions=predictions, bundle=bundle
    )
    if (
        root.canonical_hash() != profile.frozen_root_sha256
        or sha256_file(comparison_path) != profile.comparison_evidence_sha256
    ):
        raise ValueError("C4 evaluation profile does not bind its root and comparison evidence")
    binding = predictions.binding
    if (
        predictions.fold != "test"
        or binding.protocol_hash != root.protocol_sha256
        or binding.protocol_id != root.protocol_id
        or binding.corpus_id != root.corpus_id
        or binding.split_id != root.split_id
        or binding.feature_schema_version != root.feature_schema_version
        or binding.corpus_hash != root.corpus_sha256
        or binding.assignment_hash != root.assignment_sha256
        or binding.feature_config_hash != root.feature_config_sha256
        or training.feature_release_id != root.feature_release_id
        or training.feature_release_sha256 != root.feature_release_sha256
    ):
        raise ValueError("prediction model binding differs from the frozen C4 root")
    projection = verify_tabular_projection(
        projection_path, expected_sha256=profile.projection_sha256, root=root, artifact_root=artifact_root
    )
    if projection.access_scope != "final_test":
        raise ValueError("C4 comparison requires the isolated test projection")
    # Every call rehashes the complete original checkpoint inventories, including
    # canonical streams, before reuse. Release/projection checks above likewise
    # revalidate actual artifact bytes, rather than trusting manifest assertions.
    replay_paths = verified_replay_paths(comparison_path, root=root)

    def compute():
        coverage = {}
        rows = paired_observations(
            projection=projection, artifact_root=artifact_root, predictions=predictions,
            replay_paths=replay_paths, coverage=coverage,
        )
        with closing(rows):
            result = evaluate_c4_observations(rows, profile=profile, frozen_threshold=predictions.threshold)
        result["coverage"] = coverage
        result["same_observations_verified"] = True
        result["prediction_manifest_sha256"] = predictions.manifest_hash()
        result["model_binding"] = predictions.binding.model_dump(mode="json")
        return result

    if not reuse_verified_comparison:
        return compute()  # Initial scoring cannot prepopulate independent verification.
    return _reuse_comparison((profile.canonical_hash(), predictions.manifest_hash()), compute)
