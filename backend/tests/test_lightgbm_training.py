from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

lgb = pytest.importorskip("lightgbm", reason="LightGBM Phase 2 tests require the ml extra")
np = pytest.importorskip("numpy", reason="LightGBM Phase 2 tests require the ml extra")
sklearn_decomposition = pytest.importorskip(
    "sklearn.decomposition",
    reason="LightGBM Phase 2 tests require the ml extra",
)
sklearn_preprocessing = pytest.importorskip(
    "sklearn.preprocessing",
    reason="LightGBM Phase 2 tests require the ml extra",
)
PCA = sklearn_decomposition.PCA
StandardScaler = sklearn_preprocessing.StandardScaler

import app.ml.lightgbm as lightgbm_boundary  # noqa: E402
from app.features.io import feature_arrow_schema  # noqa: E402
from app.features.pipeline import (  # noqa: E402
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_V2,
)
from app.ml.lightgbm.data import (  # noqa: E402
    GovernedFeatureDataset,
    GovernedFeatureFold,
    GovernedFeatureShard,
)
from app.ml.lightgbm.training import (  # noqa: E402
    _clone_preprocessor,
    _fit_optional_preprocessor,
    _materialize_fold,
    calculate_base_session_sample_weights,
    calculate_training_class_weights,
    train_binary_attack_model,
)

GIT_COMMIT = "a" * 40
GENERATED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _feature_row(
    *,
    run_id: str,
    base_session_id: str,
    label: int,
    row_index: int,
    session_index: int,
) -> dict[str, object]:
    signal = (2.0 if label else -2.0) + (row_index % 5) * 0.05
    row: dict[str, object] = {
        "feature_schema_version": FEATURE_SCHEMA_V2,
        "feature_config_hash": _sha256("feature-config"),
        "run_id": run_id,
        "dataset_id": f"dataset-{base_session_id}",
        "source_type": "hybrid" if label else "lobster",
        "instrument": "SPY",
        "venue": "LOBSTER",
        "session_id": base_session_id,
        "session_date": date(2026, 1, session_index + 1),
        "seed": 1000 + session_index if label else None,
        "prediction_timestamp_ns": 1_000_000 + row_index,
        "tick": row_index + 1,
        "sequence": row_index + 1,
        "split_group": f"SPY:{base_session_id}",
        "attack_family": "layering_like" if label else None,
        "attack_phase": "pressure_build" if label else "none",
        "label": label,
        "label_source": ("synthetic_scenario" if label else "independently_verified_clean"),
        "row_valid": True,
        "invalid_reason": None,
    }
    for feature_index, name in enumerate(FEATURE_COLUMNS):
        value = signal + session_index * 0.01 + feature_index * 0.0001
        row[name] = None if name == "spread" and row_index == 0 else value
    return row


def _write_shard(
    root: Path,
    *,
    fold: str,
    base_session_id: str,
    session_index: int,
    label: int,
    row_count: int,
) -> GovernedFeatureShard:
    domain = "campaign" if label else "control"
    run_id = f"{base_session_id}-{domain}"
    rows = [
        _feature_row(
            run_id=run_id,
            base_session_id=base_session_id,
            label=label,
            row_index=index,
            session_index=session_index,
        )
        for index in range(row_count)
    ]
    path = root / "inputs" / fold / base_session_id / f"{domain}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            rows,
            schema=feature_arrow_schema(
                _sha256("feature-config"),
                FEATURE_SCHEMA_V2,
            ),
        ),
        path,
        compression="zstd",
    )
    payload = path.read_bytes()
    return GovernedFeatureShard(
        fold=fold,
        base_session_id=base_session_id,
        campaign_id=f"campaign-{base_session_id}" if label else None,
        run_id=run_id,
        source_type="hybrid" if label else "lobster",
        feature_path=path,
        feature_uri=path.relative_to(root).as_posix(),
        feature_sha256=hashlib.sha256(payload).hexdigest(),
        feature_size_bytes=len(payload),
        run_metadata_path=path,
        run_metadata_sha256=hashlib.sha256(payload).hexdigest(),
        total_row_count=row_count,
        supervised_row_count=row_count,
        positive_row_count=row_count if label else 0,
        negative_row_count=0 if label else row_count,
        unlabeled_row_count=0,
        feature_columns=tuple(FEATURE_COLUMNS),
    )


def _fold(
    root: Path,
    *,
    name: str,
    sessions: tuple[tuple[str, int, int], ...],
) -> GovernedFeatureFold:
    shards: list[GovernedFeatureShard] = []
    for session_index, (session_id, negative_rows, positive_rows) in enumerate(sessions):
        shards.extend(
            (
                _write_shard(
                    root,
                    fold=name,
                    base_session_id=session_id,
                    session_index=session_index,
                    label=0,
                    row_count=negative_rows,
                ),
                _write_shard(
                    root,
                    fold=name,
                    base_session_id=session_id,
                    session_index=session_index,
                    label=1,
                    row_count=positive_rows,
                ),
            )
        )
    positive = sum(shard.positive_row_count for shard in shards)
    negative = sum(shard.negative_row_count for shard in shards)
    return GovernedFeatureFold(
        fold=name,
        shards=tuple(shards),
        fold_membership_hash=_sha256(f"{name}-membership"),
        session_count=len(sessions),
        row_count=positive + negative,
        positive_row_count=positive,
        negative_row_count=negative,
    )


@pytest.fixture
def nontrivial_dataset(tmp_path: Path) -> GovernedFeatureDataset:
    train = _fold(
        tmp_path,
        name="train",
        sessions=(("train-a", 18, 4), ("train-b", 4, 18)),
    )
    validation = _fold(
        tmp_path,
        name="validation",
        sessions=(("validation-a", 8, 6), ("validation-b", 6, 8)),
    )
    return GovernedFeatureDataset(
        access_mode="development",
        protocol_id="phase2-protocol",
        protocol_hash=_sha256("protocol"),
        corpus_id="phase2-corpus",
        corpus_hash=_sha256("corpus"),
        split_id="phase2-split",
        assignment_hash=_sha256("assignment"),
        feature_schema_version=FEATURE_SCHEMA_V2,
        feature_config_hash=_sha256("feature-config"),
        feature_release_id="phase2-feature-release",
        feature_release_sha256=_sha256("feature-release"),
        ordered_feature_columns=tuple(FEATURE_COLUMNS),
        folds=(train, validation),
    )


def _hyperparameters() -> lightgbm_boundary.LightGbmV1Hyperparameters:
    return lightgbm_boundary.LightGbmV1Hyperparameters(
        num_boost_round=60,
        learning_rate=0.1,
        num_leaves=8,
        min_data_in_leaf=2,
    )


def test_phase2_training_builds_a_nontrivial_reproducible_model(
    nontrivial_dataset: GovernedFeatureDataset,
    tmp_path: Path,
) -> None:
    common = {
        "created_at": GENERATED_AT,
        "git_commit": GIT_COMMIT,
        "training_seed": 73,
        "hyperparameters": _hyperparameters(),
        "early_stopping_rounds": 5,
        "early_stopping_min_delta": 0.002,
    }
    first = train_binary_attack_model(
        nontrivial_dataset,
        output_dir=tmp_path / "training-a",
        **common,
    )
    second = train_binary_attack_model(
        nontrivial_dataset,
        output_dir=tmp_path / "training-b",
        **common,
    )

    first_model = lgb.Booster(model_file=str(first.model_path))
    assert first_model.dump_model()["tree_info"][0]["num_leaves"] > 1
    assert first.training_manifest.early_stopping.best_iteration < common["hyperparameters"].num_boost_round
    assert first.model_path.read_bytes() == second.model_path.read_bytes()
    assert first.training_manifest_path.read_bytes() == second.training_manifest_path.read_bytes()
    assert (
        first.training_manifest_path.read_bytes()
        == first.training_manifest.canonical_bytes()
    )
    assert first.validation_predictions == second.validation_predictions
    assert first.training_manifest.model_artifact == first.model_artifact
    assert first.training_manifest.feature_release_sha256 == nontrivial_dataset.feature_release_sha256
    assert first.training_manifest.feature_release_id == nontrivial_dataset.feature_release_id
    assert first.training_manifest.binding.feature_schema_version == FEATURE_SCHEMA_V2
    assert first.training_manifest.data_policy.numeric_storage_dtype == "float32"
    assert first.training_manifest.preprocessing.mode == "none"
    assert all(0.0 <= probability <= 1.0 for probability in first.validation_predictions)


def test_phase2_materialization_is_single_float32_memmap_and_weights_sessions(
    nontrivial_dataset: GovernedFeatureDataset,
    tmp_path: Path,
) -> None:
    fold = nontrivial_dataset.fold("train")
    storage_path = tmp_path / "train.float32.mmap"
    materialized = _materialize_fold(
        fold,
        ordered_feature_columns=nontrivial_dataset.ordered_feature_columns,
        batch_size=5,
        storage_path=storage_path,
    )

    assert isinstance(materialized.features, np.memmap)
    assert materialized.features.dtype == np.float32
    assert storage_path.stat().st_size == (fold.row_count * len(FEATURE_COLUMNS) * np.dtype(np.float32).itemsize)
    assert np.isnan(
        materialized.features[
            0,
            FEATURE_COLUMNS.index("spread"),
        ]
    )
    class_weights = calculate_training_class_weights(materialized.labels)
    weights = calculate_base_session_sample_weights(
        materialized.labels,
        materialized.base_session_ids,
        class_weights=class_weights,
    )
    for label in (0, 1):
        session_totals = [
            weights[(materialized.labels == label) & (materialized.base_session_ids == session_code)].sum()
            for session_code in np.unique(materialized.base_session_ids)
        ]
        assert session_totals[0] == pytest.approx(session_totals[1])


def test_phase2_optional_preprocessing_is_deterministic_and_feature_preserving(
    nontrivial_dataset: GovernedFeatureDataset,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="approved deterministic scaler"):
        _clone_preprocessor(PCA(n_components=2))

    scaler = StandardScaler()
    transformed_train, transformed_validation = _fit_optional_preprocessor(
        scaler,
        train_features=np.asarray([[1.0], [3.0]], dtype=np.float32),
        train_labels=np.asarray([0, 1], dtype=np.int8),
        validation_features=np.asarray([[101.0], [103.0]], dtype=np.float32),
        ordered_feature_columns=("spread",),
    )
    assert scaler.get_feature_names_out(["spread"]).tolist() == ["spread"]
    assert transformed_train.dtype == np.float32
    assert transformed_train[:, 0].tolist() == pytest.approx([-1.0, 1.0])
    assert transformed_validation[:, 0].tolist() == pytest.approx([99.0, 101.0])

    common = {
        "created_at": GENERATED_AT,
        "git_commit": GIT_COMMIT,
        "hyperparameters": _hyperparameters(),
        "early_stopping_rounds": 5,
        "early_stopping_min_delta": 0.002,
    }
    first = train_binary_attack_model(
        nontrivial_dataset,
        output_dir=tmp_path / "scaled-a",
        preprocessor=StandardScaler(),
        **common,
    )
    second = train_binary_attack_model(
        nontrivial_dataset,
        output_dir=tmp_path / "scaled-b",
        preprocessor=StandardScaler(),
        **common,
    )
    assert first.preprocessor_path is not None
    assert second.preprocessor_path is not None
    assert first.model_path.read_bytes() == second.model_path.read_bytes()
    assert first.training_manifest_path.read_bytes() == second.training_manifest_path.read_bytes()
    assert first.preprocessor_path.read_bytes() == second.preprocessor_path.read_bytes()


def test_phase2_test_access_is_rejected(
    nontrivial_dataset: GovernedFeatureDataset,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="development access"):
        train_binary_attack_model(
            replace(nontrivial_dataset, access_mode="final_test"),
            output_dir=tmp_path / "forbidden",
            created_at=GENERATED_AT,
            git_commit=GIT_COMMIT,
        )


def test_phase2_trainer_is_exported() -> None:
    assert lightgbm_boundary.train_binary_attack_model is train_binary_attack_model
    assert "train_binary_attack_model" in lightgbm_boundary.__all__
