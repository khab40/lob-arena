from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from app.ml.lightgbm.contracts import FoldFeatureInput, SHA256_PATTERN


@dataclass(frozen=True)
class GovernedDatasetInput:
    """Metadata-only MLflow dataset input; the governed rows stay in Object Storage."""

    name: str
    digest: str
    source_uri: str
    context: str
    tags: dict[str, str]

    def __post_init__(self) -> None:
        import re

        if not self.name or len(self.name) > 255:
            raise ValueError("MLflow dataset input name must contain at most 255 characters")
        if re.fullmatch(SHA256_PATTERN, self.digest) is None:
            raise ValueError("MLflow dataset input requires a canonical SHA-256 digest")
        _validate_source_uri(self.source_uri)
        if not self.context:
            raise ValueError("MLflow dataset input context is required")


def feature_dataset_inputs(
    inputs: Iterable[FoldFeatureInput],
    *,
    source_root_uri: str,
    feature_release_id: str,
    feature_release_sha256: str,
    expected_folds: set[str],
) -> tuple[GovernedDatasetInput, ...]:
    """Build exact, per-shard dataset lineage without reading or uploading row data."""

    materialized = tuple(inputs)
    observed_folds = {item.fold for item in materialized}
    if observed_folds != expected_folds:
        raise ValueError(
            "MLflow dataset lineage folds do not match the governed access mode: "
            f"expected={sorted(expected_folds)}, observed={sorted(observed_folds)}"
        )
    result: list[GovernedDatasetInput] = []
    for item in materialized:
        context = {
            "train": "training",
            "validation": "validation",
            "test": "evaluation",
        }[item.fold]
        result.append(
            GovernedDatasetInput(
                name=dataset_input_name(
                    feature_release_id,
                    item.fold,
                    item.artifact.logical_name,
                ),
                digest=item.artifact.sha256,
                source_uri=join_dataset_source_uri(source_root_uri, item.artifact.uri),
                context=context,
                tags={
                    "fold": item.fold,
                    "row_count": str(item.row_count),
                    "session_count": str(item.session_count),
                    "fold_membership_sha256": item.fold_membership_hash,
                    "feature_release_id": feature_release_id,
                    "feature_release_sha256": feature_release_sha256,
                    "schema_version": item.artifact.schema_version,
                    "raw_rows_uploaded_to_mlflow": "false",
                },
            )
        )
    return tuple(result)


def log_dataset_inputs(mlflow: Any, inputs: Iterable[GovernedDatasetInput]) -> None:
    """Log metadata-only MLflow Dataset inputs through stable public MLflow APIs."""

    for item in inputs:
        source_type = urlsplit(item.source_uri).scheme
        source_class = next(
            (
                candidate
                for candidate in mlflow.data.get_registered_sources()
                if candidate._get_source_type() == ("local" if source_type == "file" else source_type)
            ),
            None,
        )
        if source_class is None:
            raise RuntimeError(f"MLflow has no registered dataset source for {source_type}://")
        dataset = mlflow.data.meta_dataset.MetaDataset(
            source=source_class(item.source_uri),
            name=item.name,
            digest=mlflow_dataset_digest(item.digest),
        )
        mlflow.log_input(
            dataset,
            context=item.context,
            tags={
                **item.tags,
                "artifact_sha256": item.digest,
                "digest_algorithm": "sha256",
            },
        )


def mlflow_dataset_digest(sha256: str) -> str:
    """Adapt a full SHA-256 to MLflow's 36-character dataset digest field."""

    import re

    if re.fullmatch(SHA256_PATTERN, sha256) is None:
        raise ValueError("MLflow dataset digest adapter requires a canonical SHA-256")
    return f"sha256:{sha256[:29]}"


def join_dataset_source_uri(root: str, relative: str) -> str:
    parsed = _validate_source_uri(root)
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
        raise ValueError("MLflow dataset artifact path must be normalized and relative")
    path = f"{parsed.path.rstrip('/')}/{relative_path.as_posix()}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def dataset_input_name(*parts: str) -> str:
    value = "-".join(parts)
    if len(value) <= 255:
        return value
    suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{value[:230]}-{suffix}"


def _validate_source_uri(value: str):
    parsed = urlsplit(value)
    if parsed.scheme not in {"s3", "file"}:
        raise ValueError("MLflow governed dataset sources must use s3:// or file://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MLflow governed dataset source URI must not contain credentials, query, or fragment")
    if parsed.scheme == "s3" and (not parsed.netloc or not parsed.path.strip("/")):
        raise ValueError("MLflow S3 dataset source must include a bucket and bounded prefix")
    if parsed.scheme == "file" and not parsed.path.startswith("/"):
        raise ValueError("MLflow file dataset source must be absolute")
    return parsed
