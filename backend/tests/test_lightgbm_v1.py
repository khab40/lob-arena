from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("lightgbm", reason="LightGBM v1 tests require the ml extra")
np = pytest.importorskip("numpy", reason="LightGBM v1 tests require the ml extra")

from app.features.io import feature_arrow_schema  # noqa: E402
from app.features.pipeline import FEATURE_COLUMNS, FEATURE_SCHEMA_V2  # noqa: E402
from app.ml.lightgbm.data import (  # noqa: E402
    GovernedFeatureDataset,
    GovernedFeatureFold,
    GovernedFeatureShard,
)
from app.ml.lightgbm.detector import LightGbmV1Detector  # noqa: E402
from app.ml.lightgbm.contracts import (  # noqa: E402
    CalibrationParameters,
    LightGbmV1Hyperparameters,
)
from app.ml.lightgbm.release import build_model_bundle, verify_phase_zero_release  # noqa: E402
from app.ml.lightgbm.scoring import (  # noqa: E402
    PREDICTION_ARROW_SCHEMA,
    apply_calibration,
    calibrate_validation_predictions,
    predict_governed_fold,
    select_operating_points,
    validate_prediction_parquet,
)
from app.ml.lightgbm.training import train_binary_attack_model  # noqa: E402
from app.ml.lightgbm import tracking as tracking_module  # noqa: E402
from app.ml.lightgbm.tracking import (  # noqa: E402
    DEVELOPMENT_EXPERIMENT,
    EVALUATION_EXPERIMENT,
    log_development_run,
    log_governed_evaluation_run,
)
from scripts.evaluate_governed_benchmark import (  # noqa: E402
    _load_detector_prediction_alerts,
    _load_verified_detector_release,
)


CREATED_AT = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


class _FakeRun:
    def __init__(self, run_id: str) -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> "_FakeRun":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _FakeMlflow:
    def __init__(self) -> None:
        self.experiments: list[str] = []
        self.tags: list[dict[str, str]] = []
        self.parameters: list[dict[str, object]] = []
        self.metrics: list[dict[str, float]] = []
        self.artifacts: list[tuple[str, str]] = []
        self.run_names: list[str] = []

    def set_experiment(self, name: str) -> None:
        self.experiments.append(name)

    def start_run(self, *, run_name: str) -> _FakeRun:
        self.run_names.append(run_name)
        return _FakeRun(f"run-{len(self.run_names)}")

    def set_tags(self, values: dict[str, str]) -> None:
        self.tags.append(values)

    def log_params(self, values: dict[str, object]) -> None:
        self.parameters.append(values)

    def log_metrics(self, values: dict[str, float]) -> None:
        self.metrics.append(values)

    def log_artifact(self, path: str, *, artifact_path: str) -> None:
        self.artifacts.append((path, artifact_path))


def _hyperparameters() -> LightGbmV1Hyperparameters:
    return LightGbmV1Hyperparameters(
        num_boost_round=60,
        learning_rate=0.1,
        num_leaves=8,
        min_data_in_leaf=2,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _row(
    *,
    run_id: str,
    base_session_id: str,
    label: int,
    index: int,
    day: int,
    family: str | None,
) -> dict[str, object]:
    signal = (3.0 if label else -3.0) + (index % 7) * 0.03
    payload: dict[str, object] = {
        "feature_schema_version": FEATURE_SCHEMA_V2,
        "feature_config_hash": _sha256("feature-config"),
        "run_id": run_id,
        "dataset_id": f"dataset-{base_session_id}",
        "source_type": "hybrid" if label else "lobster",
        "instrument": "SPY",
        "venue": "LOBSTER",
        "session_id": base_session_id,
        "session_date": date(2026, 1, day),
        "seed": day if label else None,
        "prediction_timestamp_ns": day * 1_000_000 + index,
        "tick": index + 1,
        "sequence": index + 1,
        "split_group": f"SPY:{base_session_id}",
        "attack_family": family,
        "attack_phase": "pressure_build" if label else "none",
        "label": label,
        "label_source": "synthetic_scenario" if label else "independently_verified_clean",
        "row_valid": True,
        "invalid_reason": None,
    }
    for feature_index, name in enumerate(FEATURE_COLUMNS):
        payload[name] = signal + feature_index * 0.0001
    payload["spread"] = None if index == 0 else payload["spread"]
    return payload


def _shard(
    root: Path,
    *,
    fold: str,
    session: str,
    day: int,
    label: int,
    rows: int,
    family: str | None,
) -> GovernedFeatureShard:
    domain = family or "control"
    run_id = f"{session}-{domain}"
    path = root / "features" / fold / session / f"{domain}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                _row(
                    run_id=run_id,
                    base_session_id=session,
                    label=label,
                    index=index,
                    day=day,
                    family=family,
                )
                for index in range(rows)
            ],
            schema=feature_arrow_schema(_sha256("feature-config"), FEATURE_SCHEMA_V2),
        ),
        path,
        compression="zstd",
    )
    content = path.read_bytes()
    return GovernedFeatureShard(
        fold=fold,
        base_session_id=session,
        campaign_id=f"campaign-{session}-{domain}" if label else None,
        run_id=run_id,
        source_type="hybrid" if label else "lobster",
        feature_path=path,
        feature_uri=path.relative_to(root).as_posix(),
        feature_sha256=hashlib.sha256(content).hexdigest(),
        feature_size_bytes=len(content),
        run_metadata_path=path,
        run_metadata_sha256=hashlib.sha256(content).hexdigest(),
        total_row_count=rows,
        supervised_row_count=rows,
        positive_row_count=rows if label else 0,
        negative_row_count=0 if label else rows,
        unlabeled_row_count=0,
        feature_columns=tuple(FEATURE_COLUMNS),
    )


def _fold(root: Path, name: str, day_offset: int) -> GovernedFeatureFold:
    shards: list[GovernedFeatureShard] = []
    for offset, session in enumerate((f"{name}-a", f"{name}-b"), day_offset):
        shards.extend(
            [
                _shard(
                    root,
                    fold=name,
                    session=session,
                    day=offset,
                    label=0,
                    rows=12,
                    family=None,
                ),
                _shard(
                    root,
                    fold=name,
                    session=session,
                    day=offset,
                    label=1,
                    rows=6,
                    family="liquidity_evaporation" if offset % 2 else "layering_like",
                ),
            ]
        )
    positive = sum(shard.positive_row_count for shard in shards)
    negative = sum(shard.negative_row_count for shard in shards)
    return GovernedFeatureFold(
        fold=name,
        shards=tuple(shards),
        fold_membership_hash=_sha256(f"{name}-membership"),
        session_count=2,
        row_count=positive + negative,
        positive_row_count=positive,
        negative_row_count=negative,
    )


def _dataset(root: Path, *, access_mode: str) -> GovernedFeatureDataset:
    folds = (
        (_fold(root, "train", 1), _fold(root, "validation", 3))
        if access_mode == "development"
        else (_fold(root, "test", 5),)
    )
    return GovernedFeatureDataset(
        access_mode=access_mode,
        protocol_id="v1-protocol",
        protocol_hash=_sha256("protocol"),
        corpus_id="v1-corpus",
        corpus_hash=_sha256("corpus"),
        split_id="v1-split",
        assignment_hash=_sha256("assignment"),
        feature_schema_version=FEATURE_SCHEMA_V2,
        feature_config_hash=_sha256("feature-config"),
        feature_release_id="v1-feature-release",
        feature_release_sha256=_sha256("feature-release"),
        ordered_feature_columns=tuple(FEATURE_COLUMNS),
        folds=folds,
    )


def test_complete_lightgbm_v1_release_detector_and_mlflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    development = _dataset(artifact_root, access_mode="development")
    training = train_binary_attack_model(
        development,
        artifact_root=artifact_root,
        output_dir=artifact_root / "model" / "training",
        created_at=CREATED_AT,
        git_commit="a" * 40,
        hyperparameters=_hyperparameters(),
        early_stopping_rounds=5,
    )
    calibration = calibrate_validation_predictions(
        development,
        training=training.training_manifest,
        artifact_root=artifact_root,
        output_dir=artifact_root / "model" / "calibration",
        created_at=CREATED_AT,
        precision_floor=0.90,
        recall_floor=0.90,
        batch_size=7,
    )
    final_test = _dataset(artifact_root, access_mode="final_test")
    predictions = predict_governed_fold(
        final_test,
        training=training.training_manifest,
        calibration=calibration.manifest,
        artifact_root=artifact_root,
        output_dir=artifact_root / "model" / "test",
        created_at=CREATED_AT,
        operating_mode="balanced",
        batch_size=5,
    )
    validate_prediction_parquet(
        predictions.predictions_path,
        expected_rows=final_test.fold("test").row_count,
    )
    assert pq.ParquetFile(predictions.contributions_path).metadata.num_rows == predictions.manifest.alert_count * 5
    bundle = build_model_bundle(
        artifact_root,
        output_dir=artifact_root / "model" / "bundle",
        training=training.training_manifest,
        calibration=calibration.manifest,
        predictions=predictions.manifest,
        training_manifest_path=training.training_manifest_path,
        calibration_manifest_path=calibration.manifest_path,
        prediction_manifest_path=predictions.manifest_path,
        feature_schema_path=calibration.feature_schema_path,
        validation_metrics_path=calibration.validation_metrics_path,
        feature_importance_path=calibration.feature_importance_path,
        contributions_path=predictions.contributions_path,
        reliability_bins_path=calibration.reliability_bins_path,
        reliability_diagram_path=calibration.reliability_diagram_path,
        created_at=CREATED_AT,
    )
    verify_phase_zero_release(
        artifact_root,
        training=training.training_manifest,
        calibration=calibration.manifest,
        bundle=bundle.bundle,
        predictions=predictions.manifest,
    )
    loaded_release = _load_verified_detector_release(
        artifact_root=artifact_root,
        training_manifest_path=training.training_manifest_path,
        calibration_manifest_path=calibration.manifest_path,
        model_bundle_path=bundle.bundle_path,
        prediction_manifest_path=predictions.manifest_path,
    )
    assert loaded_release[3] == predictions.manifest
    failed_bundle_dir = artifact_root / "model" / "failed-bundle"
    with pytest.raises(ValueError, match="training manifest digest"):
        build_model_bundle(
            artifact_root,
            output_dir=failed_bundle_dir,
            training=training.training_manifest.model_copy(
                update={"created_at": datetime(2026, 7, 31, 12, 1, tzinfo=UTC)}
            ),
            calibration=calibration.manifest,
            predictions=predictions.manifest,
            training_manifest_path=training.training_manifest_path,
            calibration_manifest_path=calibration.manifest_path,
            prediction_manifest_path=predictions.manifest_path,
            feature_schema_path=calibration.feature_schema_path,
            validation_metrics_path=calibration.validation_metrics_path,
            feature_importance_path=calibration.feature_importance_path,
            contributions_path=predictions.contributions_path,
            created_at=CREATED_AT,
        )
    assert not failed_bundle_dir.exists()
    detector = LightGbmV1Detector(
        artifact_root=artifact_root,
        training=training.training_manifest,
        calibration=calibration.manifest,
        bundle=bundle.bundle,
        release_predictions=predictions.manifest,
    )
    with pytest.raises(ValueError, match="operating mode was not evaluated"):
        LightGbmV1Detector(
            artifact_root=artifact_root,
            training=training.training_manifest,
            calibration=calibration.manifest,
            bundle=bundle.bundle,
            release_predictions=predictions.manifest,
            operating_mode="high_recall",
        )
    score = detector.score({name: 3.0 for name in FEATURE_COLUMNS})
    assert score.alert
    assert len(score.top_contributions) == 5
    assert score.attack_probability >= score.threshold
    assert bundle.bundle_artifact.sha256 == bundle.bundle.manifest_hash()

    fake_mlflow = _FakeMlflow()
    monkeypatch.setattr(tracking_module, "_mlflow", lambda _: fake_mlflow)
    assert log_development_run(
        artifact_root=artifact_root,
        training=training.training_manifest,
        calibration=calibration.manifest,
        training_manifest_path=training.training_manifest_path,
        calibration_manifest_path=calibration.manifest_path,
        validation_metrics_path=calibration.validation_metrics_path,
        feature_importance_path=calibration.feature_importance_path,
        reliability_bins_path=calibration.reliability_bins_path,
        reliability_diagram_path=calibration.reliability_diagram_path,
        model_path=training.model_path,
    ) == "run-1"
    assert log_governed_evaluation_run(
        artifact_root=artifact_root,
        training=training.training_manifest,
        calibration=calibration.manifest,
        predictions=predictions.manifest,
        bundle=bundle.bundle,
        bundle_path=bundle.bundle_path,
        checksum_path=bundle.checksum_path,
        prediction_manifest_path=predictions.manifest_path,
    ) == "run-2"
    assert fake_mlflow.experiments == [DEVELOPMENT_EXPERIMENT, EVALUATION_EXPERIMENT]
    assert fake_mlflow.tags[0]["test_accessed"] == "false"
    assert fake_mlflow.tags[1]["test_accessed"] == "true"

    invalid_schema_path = artifact_root / "model" / "invalid-feature-schema.json"
    invalid_schema_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="feature schema evidence"):
        build_model_bundle(
            artifact_root,
            output_dir=artifact_root / "model" / "invalid-evidence-bundle",
            training=training.training_manifest,
            calibration=calibration.manifest,
            predictions=predictions.manifest,
            training_manifest_path=training.training_manifest_path,
            calibration_manifest_path=calibration.manifest_path,
            prediction_manifest_path=predictions.manifest_path,
            feature_schema_path=invalid_schema_path,
            validation_metrics_path=calibration.validation_metrics_path,
            feature_importance_path=calibration.feature_importance_path,
            contributions_path=predictions.contributions_path,
            created_at=CREATED_AT,
        )

    empty_contributions_path = artifact_root / "model" / "empty-contributions.parquet"
    pq.write_table(
        pq.read_table(predictions.contributions_path).slice(0, 0),
        empty_contributions_path,
    )
    with pytest.raises(ValueError, match="cover every alert"):
        build_model_bundle(
            artifact_root,
            output_dir=artifact_root / "model" / "invalid-contribution-bundle",
            training=training.training_manifest,
            calibration=calibration.manifest,
            predictions=predictions.manifest,
            training_manifest_path=training.training_manifest_path,
            calibration_manifest_path=calibration.manifest_path,
            prediction_manifest_path=predictions.manifest_path,
            feature_schema_path=calibration.feature_schema_path,
            validation_metrics_path=calibration.validation_metrics_path,
            feature_importance_path=calibration.feature_importance_path,
            contributions_path=empty_contributions_path,
            created_at=CREATED_AT,
        )


def test_calibration_and_test_access_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    development = _dataset(root, access_mode="development")
    training = train_binary_attack_model(
        development,
        artifact_root=root,
        output_dir=root / "training",
        created_at=CREATED_AT,
        git_commit="b" * 40,
        hyperparameters=_hyperparameters(),
        early_stopping_rounds=5,
    )
    with pytest.raises(ValueError, match="isolated validation"):
        calibrate_validation_predictions(
            replace(development, access_mode="final_test"),
            training=training.training_manifest,
            artifact_root=root,
            output_dir=root / "forbidden-calibration",
            created_at=CREATED_AT,
        )
    calibration = calibrate_validation_predictions(
        development,
        training=training.training_manifest,
        artifact_root=root,
        output_dir=root / "calibration",
        created_at=CREATED_AT,
    )
    with pytest.raises(ValueError, match="isolated test"):
        predict_governed_fold(
            development,
            training=training.training_manifest,
            calibration=calibration.manifest,
            artifact_root=root,
            output_dir=root / "forbidden-test",
            created_at=CREATED_AT,
        )


def test_operating_points_and_platt_application_are_deterministic() -> None:
    labels = np.asarray([0, 0, 0, 1, 1, 1], dtype=np.int8)
    probabilities = np.asarray([0.01, 0.1, 0.4, 0.6, 0.9, 0.99])
    first = select_operating_points(
        labels,
        probabilities,
        precision_floor=1.0,
        recall_floor=1.0,
    )
    second = select_operating_points(
        labels,
        probabilities,
        precision_floor=1.0,
        recall_floor=1.0,
    )
    assert first == second
    calibrated = apply_calibration(
        calibration_parameters := CalibrationParameters(
            method="platt",
            platt_slope=1.0,
            platt_intercept=0.0,
        ),
        probabilities,
    )
    assert calibrated.tolist() == pytest.approx(probabilities.tolist())
    assert calibration_parameters.method == "platt"


def test_governed_evaluator_reads_only_frozen_alert_rows(tmp_path: Path) -> None:
    path = tmp_path / "predictions.parquet"
    rows = [
        {
            "prediction_row_id": "row-1",
            "fold": "test",
            "run_id": "run-a",
            "base_session_id": "session-a",
            "campaign_id": None,
            "instrument": "SPY",
            "session_id": "session-a",
            "source_type": "lobster",
            "prediction_timestamp_ns": 100,
            "sequence": 1,
            "label": 0,
            "attack_family": None,
            "attack_phase": "none",
            "raw_probability": 0.1,
            "calibrated_probability": 0.2,
            "threshold": 0.5,
            "alert": False,
        },
        {
            "prediction_row_id": "row-2",
            "fold": "test",
            "run_id": "run-b",
            "base_session_id": "session-b",
            "campaign_id": "campaign-b",
            "instrument": "SPY",
            "session_id": "session-b",
            "source_type": "hybrid",
            "prediction_timestamp_ns": 200,
            "sequence": 2,
            "label": 1,
            "attack_family": "layering_like",
            "attack_phase": "pressure_build",
            "raw_probability": 0.8,
            "calibrated_probability": 0.9,
            "threshold": 0.5,
            "alert": True,
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows, schema=PREDICTION_ARROW_SCHEMA), path)
    validate_prediction_parquet(
        path,
        expected_rows=2,
        expected_fold="test",
        require_decisions=True,
    )
    alerts, run_ids = _load_detector_prediction_alerts(path, detector="lightgbm-v1")
    assert run_ids == {"run-a", "run-b"}
    assert set(alerts) == {"run-b"}
    assert alerts["run-b"][0].alert_id == "row-2"

    rows[1]["alert"] = False
    pq.write_table(pa.Table.from_pylist(rows, schema=PREDICTION_ARROW_SCHEMA), path)
    with pytest.raises(ValueError, match="alert decisions"):
        validate_prediction_parquet(
            path,
            expected_rows=2,
            expected_fold="test",
            require_decisions=True,
        )
