from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from app.ml.lightgbm.contracts import (
    ArtifactDigest,
    ClassWeightEvidence,
    EarlyStoppingEvidence,
    FoldFeatureInput,
    GovernedModelBinding,
    LightGbmTrainingRun,
    LightGbmV1Hyperparameters,
    PreprocessingEvidence,
)
from app.ml.lightgbm.data import (
    GovernedFeatureDataset,
    GovernedFeatureFold,
)
from app.ml.lightgbm.artifacts import (
    artifact_digest_for_destination,
    require_output_within_artifact_root,
)


MODEL_SCHEMA_VERSION = "lightgbm_text_v1"
TRAINING_MANIFEST_FILE = "training-run.json"
MODEL_FILE = "model.txt"
PREPROCESSOR_FILE = "preprocessor.joblib"
PREPROCESSOR_SCHEMA_VERSION = "sklearn_transformer_joblib_v1"


@dataclass(frozen=True)
class MaterializedFold:
    name: str
    features: np.ndarray
    labels: np.ndarray
    base_session_ids: np.ndarray


@dataclass(frozen=True)
class DeterministicTrainingResult:
    output_dir: Path
    model_path: Path
    training_manifest_path: Path
    preprocessor_path: Path | None
    model_artifact: ArtifactDigest
    training_manifest_artifact: ArtifactDigest
    training_manifest: LightGbmTrainingRun
    validation_predictions: tuple[float, ...]


def train_binary_attack_model(
    dataset: GovernedFeatureDataset,
    *,
    output_dir: Path,
    created_at: datetime,
    git_commit: str,
    model_id: str = "lightgbm-attack-active-v1",
    training_seed: int = 42,
    hyperparameters: LightGbmV1Hyperparameters | None = None,
    early_stopping_rounds: int = 50,
    early_stopping_min_delta: float = 0.0,
    preprocessor: Any | None = None,
    batch_size: int = 65_536,
    artifact_root: Path | None = None,
) -> DeterministicTrainingResult:
    """Train the governed Phase 2 binary detector without opening the test fold."""

    output_dir = output_dir.resolve()
    artifact_root = output_dir if artifact_root is None else artifact_root.resolve()
    _validate_training_request(
        dataset,
        output_dir=output_dir,
        artifact_root=artifact_root,
        created_at=created_at,
        training_seed=training_seed,
        early_stopping_rounds=early_stopping_rounds,
        early_stopping_min_delta=early_stopping_min_delta,
        batch_size=batch_size,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    parameters = hyperparameters or LightGbmV1Hyperparameters()
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}.materialized.",
        dir=output_dir.parent,
    ) as materialized_root:
        materialized_path = Path(materialized_root)
        train_fold = _materialize_fold(
            dataset.fold("train"),
            ordered_feature_columns=dataset.ordered_feature_columns,
            batch_size=batch_size,
            storage_path=materialized_path / "train.float32.mmap",
        )
        validation_fold = _materialize_fold(
            dataset.fold("validation"),
            ordered_feature_columns=dataset.ordered_feature_columns,
            batch_size=batch_size,
            storage_path=materialized_path / "validation.float32.mmap",
        )
        class_weights = calculate_training_class_weights(train_fold.labels)
        train_weights = calculate_base_session_sample_weights(
            train_fold.labels,
            train_fold.base_session_ids,
            class_weights=class_weights,
        )
        validation_weights = calculate_base_session_sample_weights(
            validation_fold.labels,
            validation_fold.base_session_ids,
            class_weights=class_weights,
        )
        training_preprocessor = _clone_preprocessor(preprocessor)
        train_features, validation_features = _fit_optional_preprocessor(
            training_preprocessor,
            train_features=train_fold.features,
            train_labels=train_fold.labels,
            validation_features=validation_fold.features,
            ordered_feature_columns=dataset.ordered_feature_columns,
        )

        import lightgbm as lgb

        train_data = lgb.Dataset(
            train_features,
            label=train_fold.labels,
            weight=train_weights,
            feature_name=list(dataset.ordered_feature_columns),
            free_raw_data=True,
        )
        validation_data = lgb.Dataset(
            validation_features,
            label=validation_fold.labels,
            weight=validation_weights,
            reference=train_data,
            feature_name=list(dataset.ordered_feature_columns),
            free_raw_data=True,
        )
        booster = lgb.train(
            _lightgbm_parameters(parameters, training_seed=training_seed),
            train_data,
            num_boost_round=parameters.num_boost_round,
            valid_sets=[validation_data],
            valid_names=["validation"],
            callbacks=[
                lgb.early_stopping(
                    early_stopping_rounds,
                    first_metric_only=True,
                    verbose=False,
                    min_delta=early_stopping_min_delta,
                ),
                lgb.log_evaluation(period=0),
            ],
        )
        best_iteration = int(booster.best_iteration)
        if best_iteration < 1:
            raise RuntimeError("LightGBM did not select a valid best iteration")
        best_score = float(booster.best_score["validation"]["binary_logloss"])
        if not math.isfinite(best_score):
            raise RuntimeError("LightGBM produced a non-finite validation score")
        validation_predictions = np.asarray(
            booster.predict(validation_features, num_iteration=best_iteration),
            dtype=np.float64,
        )
        if (
            validation_predictions.shape != validation_fold.labels.shape
            or not np.isfinite(validation_predictions).all()
        ):
            raise RuntimeError("LightGBM produced invalid validation predictions")
        del (
            train_data,
            validation_data,
            train_features,
            validation_features,
            train_fold,
            validation_fold,
            train_weights,
            validation_weights,
        )
        gc.collect()

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.",
            dir=output_dir.parent,
        )
    )
    try:
        model_path = staging / MODEL_FILE
        booster.save_model(model_path, num_iteration=best_iteration)
        model_artifact = artifact_digest_for_destination(
            model_path,
            destination=output_dir / MODEL_FILE,
            artifact_root=artifact_root,
            logical_name="model",
            schema_version=MODEL_SCHEMA_VERSION,
        )
        preprocessing = _persist_preprocessor(
            training_preprocessor,
            staging=staging,
            output_dir=output_dir,
            artifact_root=artifact_root,
        )
        training_run_id = _training_run_id(
            dataset=dataset,
            model_id=model_id,
            git_commit=git_commit,
            training_seed=training_seed,
            hyperparameters=parameters,
            early_stopping_rounds=early_stopping_rounds,
            early_stopping_min_delta=early_stopping_min_delta,
            model_artifact=model_artifact,
            preprocessing=preprocessing,
        )
        binding = GovernedModelBinding(
            model_id=model_id,
            training_run_id=training_run_id,
            protocol_id=dataset.protocol_id,
            protocol_hash=dataset.protocol_hash,
            corpus_id=dataset.corpus_id,
            corpus_hash=dataset.corpus_hash,
            split_id=dataset.split_id,
            assignment_hash=dataset.assignment_hash,
            feature_schema_version=dataset.feature_schema_version,
            feature_config_hash=dataset.feature_config_hash,
        )
        manifest = LightGbmTrainingRun(
            binding=binding,
            feature_release_id=dataset.feature_release_id,
            feature_release_sha256=dataset.feature_release_sha256,
            model_artifact=model_artifact,
            git_commit=git_commit,
            created_at=created_at,
            training_seed=training_seed,
            ordered_feature_columns=dataset.ordered_feature_columns,
            input_features=_fold_inputs(dataset),
            hyperparameters=parameters,
            class_weights=class_weights,
            preprocessing=preprocessing,
            early_stopping=EarlyStoppingEvidence(
                stopping_rounds=early_stopping_rounds,
                min_delta=early_stopping_min_delta,
                best_iteration=best_iteration,
                best_score=best_score,
            ),
        )
        manifest_path = staging / TRAINING_MANIFEST_FILE
        _write_manifest(manifest_path, manifest)
        manifest_artifact = artifact_digest_for_destination(
            manifest_path,
            destination=output_dir / TRAINING_MANIFEST_FILE,
            artifact_root=artifact_root,
            logical_name="training_manifest",
            schema_version=manifest.schema_version,
        )
        if output_dir.exists():
            raise ValueError("training output directory was created concurrently")
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    final_preprocessor = output_dir / PREPROCESSOR_FILE if preprocessing.transformer is not None else None
    return DeterministicTrainingResult(
        output_dir=output_dir,
        model_path=output_dir / MODEL_FILE,
        training_manifest_path=output_dir / TRAINING_MANIFEST_FILE,
        preprocessor_path=final_preprocessor,
        model_artifact=model_artifact,
        training_manifest_artifact=manifest_artifact,
        training_manifest=manifest,
        validation_predictions=tuple(float(value) for value in validation_predictions),
    )


def calculate_training_class_weights(labels: np.ndarray) -> ClassWeightEvidence:
    raw_values = np.asarray(labels)
    if raw_values.ndim != 1 or raw_values.size == 0 or not np.isin(raw_values, (0, 1)).all():
        raise ValueError("training labels must be a non-empty binary vector")
    values = raw_values.astype(np.int8, copy=False)
    negative_count = int(np.count_nonzero(values == 0))
    positive_count = int(np.count_nonzero(values == 1))
    if negative_count == 0 or positive_count == 0:
        raise ValueError("training labels require both binary classes")
    total = negative_count + positive_count
    return ClassWeightEvidence(
        negative_count=negative_count,
        positive_count=positive_count,
        negative_weight=total / (2 * negative_count),
        positive_weight=total / (2 * positive_count),
    )


def calculate_base_session_sample_weights(
    labels: np.ndarray,
    base_session_ids: np.ndarray,
    *,
    class_weights: ClassWeightEvidence,
) -> np.ndarray:
    raw_values = np.asarray(labels)
    sessions = np.asarray(base_session_ids)
    if (
        raw_values.ndim != 1
        or sessions.ndim != 1
        or raw_values.shape != sessions.shape
        or raw_values.size == 0
        or not np.isin(raw_values, (0, 1)).all()
    ):
        raise ValueError("labels and base-session IDs must be aligned governed vectors")
    if sessions.dtype.kind in {"U", "S", "O"} and any(not str(session) for session in sessions):
        raise ValueError("base-session IDs must be non-empty")
    values = raw_values.astype(np.int8, copy=False)
    weights = np.empty(values.size, dtype=np.float64)
    per_class_weight = {
        0: class_weights.negative_weight,
        1: class_weights.positive_weight,
    }
    for label in (0, 1):
        class_indices = np.flatnonzero(values == label)
        if class_indices.size == 0:
            raise ValueError("sample weighting requires both binary classes")
        _, inverse, counts = np.unique(
            sessions[class_indices],
            return_inverse=True,
            return_counts=True,
        )
        session_factor = class_indices.size / (counts.size * counts[inverse])
        weights[class_indices] = per_class_weight[label] * session_factor
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise RuntimeError("calculated sample weights are invalid")
    return weights


def _validate_training_request(
    dataset: GovernedFeatureDataset,
    *,
    output_dir: Path,
    artifact_root: Path,
    created_at: datetime,
    training_seed: int,
    early_stopping_rounds: int,
    early_stopping_min_delta: float,
    batch_size: int,
) -> None:
    if dataset.access_mode != "development":
        raise ValueError("training requires governed development access only")
    if {fold.fold for fold in dataset.folds} != {"train", "validation"}:
        raise ValueError("training requires exactly the train and validation folds")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("training created_at must be timezone-aware")
    if training_seed < 0:
        raise ValueError("training seed must be non-negative")
    if early_stopping_rounds < 1:
        raise ValueError("early stopping rounds must be positive")
    if not math.isfinite(early_stopping_min_delta) or early_stopping_min_delta < 0:
        raise ValueError("early stopping min_delta must be finite and non-negative")
    if batch_size < 1:
        raise ValueError("training batch size must be positive")
    if output_dir.exists():
        raise ValueError("training output directory already exists")
    if artifact_root == output_dir:
        return
    require_output_within_artifact_root(output_dir, artifact_root)
    for fold in dataset.folds:
        for shard in fold.shards:
            expected = (artifact_root / shard.feature_uri).resolve()
            if expected != shard.feature_path.resolve():
                raise ValueError(
                    "governed feature artifacts and training output must share one artifact root"
                )


def _materialize_fold(
    fold: GovernedFeatureFold,
    *,
    ordered_feature_columns: tuple[str, ...],
    batch_size: int,
    storage_path: Path,
) -> MaterializedFold:
    features = np.memmap(
        storage_path,
        mode="w+",
        dtype=np.float32,
        shape=(fold.row_count, len(ordered_feature_columns)),
    )
    labels = np.empty(fold.row_count, dtype=np.int8)
    session_codes = np.empty(fold.row_count, dtype=np.int32)
    session_code_by_id = {
        session_id: code for code, session_id in enumerate(sorted({shard.base_session_id for shard in fold.shards}))
    }
    offset = 0
    selected_features = set(ordered_feature_columns)
    for shard in fold.shards:
        retained_order = tuple(name for name in shard.feature_columns if name in selected_features)
        if retained_order != ordered_feature_columns:
            raise ValueError("selected feature columns do not preserve the governed shard order")
        for batch in shard.iter_supervised_batches(batch_size=batch_size):
            end = offset + batch.num_rows
            for column_index, name in enumerate(ordered_feature_columns):
                values = pc.cast(
                    batch.column(batch.schema.get_field_index(name)),
                    pa.float32(),
                )
                features[offset:end, column_index] = values.to_numpy(
                    zero_copy_only=False,
                )
            labels[offset:end] = np.asarray(
                batch.column(batch.schema.get_field_index("label")).to_numpy(zero_copy_only=False),
                dtype=np.int8,
            )
            session_codes[offset:end] = session_code_by_id[shard.base_session_id]
            offset = end
    if offset == 0:
        raise ValueError(f"governed feature fold has no supervised rows: {fold.fold}")
    features.flush()
    if (
        offset != fold.row_count
        or features.shape != (fold.row_count, len(ordered_feature_columns))
        or labels.shape != (fold.row_count,)
        or session_codes.shape != (fold.row_count,)
        or int(np.count_nonzero(labels == 1)) != fold.positive_row_count
        or int(np.count_nonzero(labels == 0)) != fold.negative_row_count
        or len(np.unique(session_codes)) != fold.session_count
    ):
        raise ValueError("materialized rows do not match the governed fold inventory")
    return MaterializedFold(
        name=fold.fold,
        features=features,
        labels=labels,
        base_session_ids=session_codes,
    )


def _fit_optional_preprocessor(
    preprocessor: Any | None,
    *,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    ordered_feature_columns: tuple[str, ...],
) -> tuple[Any, Any]:
    if preprocessor is None:
        return train_features, validation_features
    if not callable(getattr(preprocessor, "fit_transform", None)) or not callable(
        getattr(preprocessor, "transform", None)
    ):
        raise ValueError("optional preprocessor must implement fit_transform and transform")
    transformed_train = np.asarray(
        preprocessor.fit_transform(train_features, train_labels),
        dtype=np.float32,
    )
    transformed_validation = np.asarray(
        preprocessor.transform(validation_features),
        dtype=np.float32,
    )
    expected_columns = train_features.shape[1]
    if getattr(transformed_train, "shape", None) != (train_features.shape[0], expected_columns) or getattr(
        transformed_validation, "shape", None
    ) != (validation_features.shape[0], expected_columns):
        raise ValueError("optional preprocessing must preserve governed rows and feature columns")
    output_columns = tuple(
        str(name) for name in preprocessor.get_feature_names_out(np.asarray(ordered_feature_columns, dtype=object))
    )
    if output_columns != ordered_feature_columns:
        raise ValueError("optional preprocessing must preserve governed feature identity and order")
    if np.isinf(transformed_train).any() or np.isinf(transformed_validation).any():
        raise ValueError("optional preprocessing produced infinite feature values")
    return transformed_train, transformed_validation


def _clone_preprocessor(preprocessor: Any | None) -> Any | None:
    if preprocessor is None:
        return None
    from sklearn.base import clone
    from sklearn.preprocessing import (
        MaxAbsScaler,
        MinMaxScaler,
        RobustScaler,
        StandardScaler,
    )

    allowed_types = {
        StandardScaler,
        RobustScaler,
        MinMaxScaler,
        MaxAbsScaler,
    }
    if type(preprocessor) not in allowed_types:
        allowed = ", ".join(sorted(transformer.__name__ for transformer in allowed_types))
        raise ValueError(f"optional preprocessor must be an approved deterministic scaler: {allowed}")

    try:
        return clone(preprocessor)
    except TypeError as exception:
        raise ValueError("optional preprocessor must be an unfitted cloneable scikit-learn transformer") from exception


def _persist_preprocessor(
    preprocessor: Any | None,
    *,
    staging: Path,
    output_dir: Path,
    artifact_root: Path,
) -> PreprocessingEvidence:
    if preprocessor is None:
        return PreprocessingEvidence(mode="none")
    import joblib

    path = staging / PREPROCESSOR_FILE
    joblib.dump(preprocessor, path, compress=0, protocol=5)
    return PreprocessingEvidence(
        mode="training_fitted",
        transformer=artifact_digest_for_destination(
            path,
            destination=output_dir / PREPROCESSOR_FILE,
            artifact_root=artifact_root,
            logical_name="preprocessor",
            schema_version=PREPROCESSOR_SCHEMA_VERSION,
        ),
    )


def _lightgbm_parameters(
    hyperparameters: LightGbmV1Hyperparameters,
    *,
    training_seed: int,
) -> dict[str, Any]:
    parameters = hyperparameters.model_dump()
    parameters.pop("num_boost_round")
    parameters.update(
        {
            "device_type": "cpu",
            "force_col_wise": True,
            "verbosity": -1,
            "seed": training_seed,
            "data_random_seed": training_seed,
            "feature_fraction_seed": training_seed,
            "bagging_seed": training_seed,
            "drop_seed": training_seed,
            "extra_seed": training_seed,
        }
    )
    return parameters


def _fold_inputs(dataset: GovernedFeatureDataset) -> tuple[FoldFeatureInput, ...]:
    inputs: list[FoldFeatureInput] = []
    for fold_name in ("train", "validation"):
        fold = dataset.fold(fold_name)
        for shard in fold.shards:
            logical_suffix = hashlib.sha256(shard.feature_uri.encode("utf-8")).hexdigest()[:24]
            inputs.append(
                FoldFeatureInput(
                    fold=fold.fold,
                    artifact=ArtifactDigest(
                        logical_name=f"features-{logical_suffix}",
                        uri=shard.feature_uri,
                        sha256=shard.feature_sha256,
                        size_bytes=shard.feature_size_bytes,
                        schema_version=dataset.feature_schema_version,
                    ),
                    fold_membership_hash=fold.fold_membership_hash,
                    session_count=1,
                    row_count=shard.supervised_row_count,
                )
            )
    return tuple(inputs)


def _training_run_id(
    *,
    dataset: GovernedFeatureDataset,
    model_id: str,
    git_commit: str,
    training_seed: int,
    hyperparameters: LightGbmV1Hyperparameters,
    early_stopping_rounds: int,
    early_stopping_min_delta: float,
    model_artifact: ArtifactDigest,
    preprocessing: PreprocessingEvidence,
) -> str:
    payload = {
        "model_id": model_id,
        "git_commit": git_commit,
        "training_seed": training_seed,
        "protocol_hash": dataset.protocol_hash,
        "corpus_hash": dataset.corpus_hash,
        "assignment_hash": dataset.assignment_hash,
        "feature_config_hash": dataset.feature_config_hash,
        "feature_release_sha256": dataset.feature_release_sha256,
        "hyperparameters": hyperparameters.model_dump(mode="json"),
        "early_stopping_rounds": early_stopping_rounds,
        "early_stopping_min_delta": early_stopping_min_delta,
        "model_sha256": model_artifact.sha256,
        "preprocessing": preprocessing.model_dump(mode="json"),
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"lightgbm-train-{digest[:24]}"


def _write_manifest(path: Path, manifest: LightGbmTrainingRun) -> None:
    path.write_bytes(manifest.canonical_bytes())
