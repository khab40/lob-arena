from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from app.market_data.projections import (
    FinalAccessDenialEvidence,
    FrozenPublicSampleRoot,
    SequenceProjectionManifest,
    TabularProjectionManifest,
    verify_sequence_projection,
    verify_tabular_projection,
)
from app.ml.dataset_lineage import (
    GovernedDatasetInput,
    dataset_input_name,
    join_dataset_source_uri,
    log_dataset_inputs,
)
from app.nebius.object_storage import sha256_file
from app.ml.lightgbm.cloud_contracts import APPROVED_MLFLOW_TRACKING_URI

if TYPE_CHECKING:
    from app.market_data.preparation import NasdaqPreparationRequest, PreparationManifest


CORPUS_EXPERIMENT = "lob-arena/corpus-releases"
DEVELOPMENT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
FINAL_BUCKET = "aimada-wave1-final-e00g6zvxpr00"


def log_preparation_run(
    *,
    request: NasdaqPreparationRequest,
    preparation: PreparationManifest,
    request_path: Path,
    preparation_path: Path,
    tracking_uri: str,
) -> str:
    """Track a verified C3 preparation without copying market rows to MLflow."""

    if preparation.run_id != request.run_id:
        raise ValueError("MLflow preparation run identity does not match its request")
    if preparation.source_manifest_sha256 != request.source_release_manifest_sha256:
        raise ValueError("MLflow preparation source manifest does not match its request")
    if request_path.read_bytes() != request.canonical_bytes():
        raise ValueError("MLflow preparation request path is not canonical")
    if preparation_path.read_bytes() != preparation.canonical_bytes():
        raise ValueError("MLflow preparation manifest path is not canonical")
    mlflow = _mlflow(tracking_uri)
    mlflow.set_experiment(CORPUS_EXPERIMENT)
    with mlflow.start_run(run_name=request.run_id) as run:
        mlflow.set_tags(
            {
                "governance_state": "preparation_verified",
                "pipeline_stage": "nasdaq_normalize_replay_features",
                "run_id": request.run_id,
                "source_date": request.source.date.isoformat(),
                "source_sha256": preparation.source_sha256,
                "source_manifest_sha256": preparation.source_manifest_sha256,
                "result_uri": request.result_uri,
                "raw_rows_uploaded_to_mlflow": "false",
            }
        )
        mlflow.log_params(
            {
                "source_filename": preparation.source_filename,
                "parser_version": preparation.parser_version,
                "parser_config_sha256": preparation.parser_config_sha256,
                "symbols": json.dumps(preparation.symbols, separators=(",", ":")),
                "window_start_ms": request.window_start_ms,
                "window_end_ms": request.window_end_ms,
                "depth": request.depth,
            }
        )
        mlflow.log_metrics(
            {
                "source_message_count": float(sum(preparation.itch_message_counts.values())),
                "system_event_count": float(preparation.system_event_count),
                "normalized_dataset_count": float(len(preparation.dataset_ids)),
                "replay_domain_count": float(preparation.replay_domain_count),
                "feature_run_count": float(preparation.feature_run_count),
            }
        )
        log_dataset_inputs(
            mlflow,
            (
                GovernedDatasetInput(
                    name=dataset_input_name(
                        "nasdaq",
                        request.source.date.isoformat(),
                        request.source.filename,
                    ),
                    digest=preparation.source_sha256,
                    source_uri=join_dataset_source_uri(
                        request.source_release_uri,
                        request.source.filename,
                    ),
                    context="preparation_source",
                    tags={
                        "source_manifest_sha256": preparation.source_manifest_sha256,
                        "trade_date": request.source.date.isoformat(),
                        "licensed_rows_uploaded_to_mlflow": "false",
                    },
                ),
            ),
        )
        mlflow.log_artifact(str(request_path), artifact_path="governed-data")
        mlflow.log_artifact(str(preparation_path), artifact_path="governed-data")
        return str(run.info.run_id)


def log_frozen_dataset_release(
    *,
    frozen_root_path: Path,
    tabular_development_path: Path,
    tabular_development_artifact_root: Path,
    tabular_development_source_uri: str,
    tabular_final_path: Path,
    tabular_final_artifact_root: Path,
    tabular_final_source_uri: str,
    sequence_development_path: Path,
    sequence_development_artifact_root: Path,
    sequence_development_source_uri: str,
    sequence_final_path: Path,
    sequence_final_artifact_root: Path,
    sequence_final_source_uri: str,
    access_denial_path: Path,
    tracking_uri: str,
) -> str:
    """Verify and index the complete C4 release and its physically isolated projections."""

    root = FrozenPublicSampleRoot.model_validate_json(frozen_root_path.read_text(encoding="utf-8"))
    tabular_development = verify_tabular_projection(
        tabular_development_path,
        expected_sha256=sha256_file(tabular_development_path),
        root=root,
        artifact_root=tabular_development_artifact_root,
    )
    tabular_final = verify_tabular_projection(
        tabular_final_path,
        expected_sha256=sha256_file(tabular_final_path),
        root=root,
        artifact_root=tabular_final_artifact_root,
    )
    sequence_development = verify_sequence_projection(
        sequence_development_path,
        expected_sha256=sha256_file(sequence_development_path),
        root=root,
        artifact_root=sequence_development_artifact_root,
    )
    sequence_final = verify_sequence_projection(
        sequence_final_path,
        expected_sha256=sha256_file(sequence_final_path),
        root=root,
        artifact_root=sequence_final_artifact_root,
    )
    denial = FinalAccessDenialEvidence.model_validate_json(
        access_denial_path.read_text(encoding="utf-8")
    )
    _verify_release_boundaries(
        tabular_development=tabular_development,
        tabular_development_source_uri=tabular_development_source_uri,
        tabular_final=tabular_final,
        tabular_final_source_uri=tabular_final_source_uri,
        sequence_development=sequence_development,
        sequence_development_source_uri=sequence_development_source_uri,
        sequence_final=sequence_final,
        sequence_final_source_uri=sequence_final_source_uri,
        denial=denial,
    )
    mlflow = _mlflow(tracking_uri)
    mlflow.set_experiment(CORPUS_EXPERIMENT)
    with mlflow.start_run(run_name=root.release_id) as run:
        mlflow.set_tags(
            {
                "governance_state": "release_verified",
                "pipeline_stage": "c4_frozen_dataset_release",
                "release_id": root.release_id,
                "root_identity_sha256": root.canonical_hash(),
                "root_file_sha256": sha256_file(frozen_root_path),
                "protocol_sha256": root.protocol_sha256,
                "corpus_sha256": root.corpus_sha256,
                "assignment_sha256": root.assignment_sha256,
                "feature_release_sha256": root.feature_release_sha256,
                "test_access_denial_verified": "true",
                "raw_rows_uploaded_to_mlflow": "false",
            }
        )
        mlflow.log_params(
            {
                "protocol_id": root.protocol_id,
                "corpus_id": root.corpus_id,
                "split_id": root.split_id,
                "feature_release_id": root.feature_release_id,
                "feature_schema_version": root.feature_schema_version,
                "negative_label_source": root.negative_label_source,
            }
        )
        mlflow.log_metrics(
            {
                "source_count": float(len(root.sources)),
                "tabular_development_shards": float(len(tabular_development.shards)),
                "tabular_final_shards": float(len(tabular_final.shards)),
                "tabular_development_rows": float(
                    sum(item.supervised_row_count for item in tabular_development.shards)
                ),
                "tabular_final_rows": float(
                    sum(item.supervised_row_count for item in tabular_final.shards)
                ),
                "sequence_development_rows": float(
                    sum(item.sequence_count for item in sequence_development.shards)
                ),
                "sequence_final_rows": float(
                    sum(item.sequence_count for item in sequence_final.shards)
                ),
            }
        )
        log_dataset_inputs(
            mlflow,
            _projection_inputs(
                tabular_development,
                tabular_development_source_uri,
                projection_kind="tabular",
            )
            + _projection_inputs(
                tabular_final,
                tabular_final_source_uri,
                projection_kind="tabular",
            )
            + _projection_inputs(
                sequence_development,
                sequence_development_source_uri,
                projection_kind="sequence",
            )
            + _projection_inputs(
                sequence_final,
                sequence_final_source_uri,
                projection_kind="sequence",
            ),
        )
        for path in (
            frozen_root_path,
            tabular_development_path,
            tabular_final_path,
            sequence_development_path,
            sequence_final_path,
            access_denial_path,
        ):
            mlflow.log_artifact(str(path), artifact_path="governed-data")
        return str(run.info.run_id)


def _projection_inputs(
    projection: TabularProjectionManifest | SequenceProjectionManifest,
    source_root_uri: str,
    *,
    projection_kind: str,
) -> tuple[GovernedDatasetInput, ...]:
    result: list[GovernedDatasetInput] = []
    for shard in projection.shards:
        artifact = shard.rows if isinstance(projection, TabularProjectionManifest) else shard.sequences
        count = (
            shard.supervised_row_count
            if isinstance(projection, TabularProjectionManifest)
            else shard.sequence_count
        )
        result.append(
            GovernedDatasetInput(
                name=dataset_input_name(
                    projection.projection_id,
                    shard.fold,
                    shard.run_id,
                ),
                digest=artifact.sha256,
                source_uri=join_dataset_source_uri(source_root_uri, artifact.uri),
                context=f"released_{shard.fold}",
                tags={
                    "role": "published_output",
                    "projection_kind": projection_kind,
                    "access_scope": projection.access_scope,
                    "fold": shard.fold,
                    "row_count": str(count),
                    "root_sha256": projection.root_sha256,
                    "raw_rows_uploaded_to_mlflow": "false",
                },
            )
        )
    return tuple(result)


def _verify_release_boundaries(
    *,
    tabular_development: TabularProjectionManifest,
    tabular_development_source_uri: str,
    tabular_final: TabularProjectionManifest,
    tabular_final_source_uri: str,
    sequence_development: SequenceProjectionManifest,
    sequence_development_source_uri: str,
    sequence_final: SequenceProjectionManifest,
    sequence_final_source_uri: str,
    denial: FinalAccessDenialEvidence,
) -> None:
    expected = (
        (tabular_development.access_scope, "development"),
        (tabular_final.access_scope, "final_test"),
        (sequence_development.access_scope, "development"),
        (sequence_final.access_scope, "final_test"),
    )
    if any(observed != required for observed, required in expected):
        raise ValueError("C4 MLflow release has incompatible projection access scopes")
    for value, bucket in (
        (tabular_development_source_uri, DEVELOPMENT_BUCKET),
        (sequence_development_source_uri, DEVELOPMENT_BUCKET),
        (tabular_final_source_uri, FINAL_BUCKET),
        (sequence_final_source_uri, FINAL_BUCKET),
    ):
        parsed = urlsplit(value)
        if parsed.scheme != "s3" or parsed.netloc != bucket or not parsed.path.strip("/"):
            raise ValueError("C4 MLflow release source URI escaped its segregated bucket")
    expected_tabular_manifest_uri = join_dataset_source_uri(
        tabular_final_source_uri,
        "manifests/tabular-projection.json",
    )
    expected_sequence_manifest_uri = join_dataset_source_uri(
        sequence_final_source_uri,
        "manifests/sequence-projection.json",
    )
    if denial.tabular_final_uri != expected_tabular_manifest_uri:
        raise ValueError("C4 tabular final access-denial evidence targets another release")
    if denial.sequence_final_uri != expected_sequence_manifest_uri:
        raise ValueError("C4 sequence final access-denial evidence targets another release")


def _mlflow(tracking_uri: str) -> Any:
    allowed = {
        APPROVED_MLFLOW_TRACKING_URI,
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    }
    if tracking_uri.rstrip("/") not in allowed:
        raise ValueError("dataset lineage requires the approved private MLflow endpoint or local tunnel")
    try:
        import mlflow
    except ImportError as exception:
        raise RuntimeError("MLflow logging requires the backend ml optional dependency") from exception
    mlflow.set_tracking_uri(tracking_uri)
    return mlflow
