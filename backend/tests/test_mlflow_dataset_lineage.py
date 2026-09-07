from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.market_data.preparation import NasdaqPreparationRequest, PreparationManifest
from app.market_data.preparation_checkpoints import CheckpointReference
from app.market_data.projections import FinalAccessDenialEvidence
from app.market_data.public_sample import load_source_config
from app.market_data import tracking as market_tracking
from app.ml.dataset_lineage import (
    feature_dataset_inputs,
    log_dataset_inputs,
    mlflow_dataset_digest,
)
from app.ml.lightgbm.contracts import ArtifactDigest, FoldFeatureInput


ROOT = Path(__file__).resolve().parents[2]


class _Run:
    info = SimpleNamespace(run_id="mlflow-data-run")

    def __enter__(self) -> _Run:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeMlflow:
    def __init__(self) -> None:
        self.experiments: list[str] = []
        self.inputs: list[tuple[object, str, dict[str, str]]] = []
        self.artifacts: list[tuple[str, str]] = []

    def set_experiment(self, name: str) -> None:
        self.experiments.append(name)

    def start_run(self, *, run_name: str) -> _Run:
        assert run_name
        return _Run()

    def set_tags(self, _values: dict[str, str]) -> None:
        return None

    def log_params(self, _values: dict[str, object]) -> None:
        return None

    def log_metrics(self, _values: dict[str, float]) -> None:
        return None

    def log_input(
        self,
        dataset: object,
        *,
        context: str,
        tags: dict[str, str],
    ) -> None:
        self.inputs.append((dataset, context, tags))

    def log_artifact(self, path: str, *, artifact_path: str) -> None:
        self.artifacts.append((path, artifact_path))


def test_feature_lineage_logs_metadata_only_s3_datasets() -> None:
    inputs = tuple(
        FoldFeatureInput(
            fold=fold,
            artifact=ArtifactDigest(
                logical_name=f"features-{fold}",
                uri=f"{fold}/rows.parquet",
                sha256=digest,
                size_bytes=123,
                schema_version="lob_features_v2",
            ),
            fold_membership_hash=("c" if fold == "train" else "d") * 64,
            session_count=2,
            row_count=10,
        )
        for fold, digest in (("train", "a" * 64), ("validation", "b" * 64))
    )
    lineage = feature_dataset_inputs(
        inputs,
        source_root_uri="s3://aimada-wave1-dev-e00g6zvxpr00/releases/release/staging/projection-artifacts",
        feature_release_id="release-v1",
        feature_release_sha256="e" * 64,
        expected_folds={"train", "validation"},
    )
    fake = _FakeMlflow()

    log_dataset_inputs(fake, lineage)

    assert [context for _, context, _ in fake.inputs] == ["training", "validation"]
    assert [dataset.digest for dataset, _, _ in fake.inputs] == [
        "sha256:" + "a" * 29,
        "sha256:" + "b" * 29,
    ]
    assert fake.inputs[0][0].source.uri.endswith("/train/rows.parquet")
    assert all(tags["raw_rows_uploaded_to_mlflow"] == "false" for _, _, tags in fake.inputs)
    assert [tags["artifact_sha256"] for _, _, tags in fake.inputs] == [
        "a" * 64,
        "b" * 64,
    ]


def test_mlflow_dataset_digest_is_bounded_and_preserves_full_hash_in_input_tags() -> None:
    digest = mlflow_dataset_digest("a" * 64)

    assert digest == "sha256:" + "a" * 29
    assert len(digest) == 36
    with pytest.raises(ValueError, match="canonical SHA-256"):
        mlflow_dataset_digest("a" * 63)


def test_feature_lineage_rejects_test_data_in_development_and_credentialed_uri() -> None:
    test_input = FoldFeatureInput(
        fold="test",
        artifact=ArtifactDigest(
            logical_name="features-test",
            uri="test/rows.parquet",
            sha256="a" * 64,
            size_bytes=1,
            schema_version="lob_features_v2",
        ),
        fold_membership_hash="b" * 64,
        session_count=1,
        row_count=1,
    )
    with pytest.raises(ValueError, match="access mode"):
        feature_dataset_inputs(
            (test_input,),
            source_root_uri="s3://dev/release",
            feature_release_id="release",
            feature_release_sha256="c" * 64,
            expected_folds={"train", "validation"},
        )
    with pytest.raises(ValueError, match="credentials"):
        feature_dataset_inputs(
            (test_input,),
            source_root_uri="s3://user:secret@final/release",
            feature_release_id="release",
            feature_release_sha256="c" * 64,
            expected_folds={"test"},
        )


def test_preparation_run_logs_source_lineage_and_only_governance_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_source_config(
        ROOT / "configs/data/nasdaq-public-sample-v1.json"
    ).sources[0]
    request = NasdaqPreparationRequest(
        run_id="nasdaq-preparation-lineage",
        sequence_number=1,
        image=f"registry.example/jobs@sha256:{'a' * 64}",
        git_commit="b" * 40,
        created_at=datetime.now(UTC),
        source=source,
        source_release_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"quarantine/nasdaq/{source.date.isoformat()}/source-release"
        ),
        source_release_manifest_sha256="c" * 64,
        result_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"prepared/{source.date.isoformat()}/nasdaq-preparation-lineage"
        ),
        checkpoint_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"preparation-checkpoints/{source.date.isoformat()}/nasdaq-preparation-lineage"
        ),
        feature_config_sha256="f" * 64,
        mlflow_tracking_uri="http://10.4.0.54:5500",
    )
    preparation = PreparationManifest(
        run_id=request.run_id,
        source_filename=source.filename,
        source_sha256="d" * 64,
        source_manifest_sha256="c" * 64,
        parser_version="itch-v1",
        parser_config_sha256="e" * 64,
        itch_message_counts={"S": 2, "A": 8},
        system_event_count=2,
        symbols=("AAPL", "MSFT", "NVDA"),
        dataset_ids={"AAPL": "a", "MSFT": "m", "NVDA": "n"},
        control_run_ids={"AAPL": "ca", "MSFT": "cm", "NVDA": "cn"},
        campaign_run_ids=tuple(f"campaign-{index}" for index in range(27)),
        checkpoint_binding_sha256="1" * 64,
        normalized_checkpoint=CheckpointReference(
            kind="normalized",
            uri="s3://example/normalized",
            checkpoint_sha256="2" * 64,
            payload_inventory_sha256="3" * 64,
            payload_file_count=3,
            payload_size_bytes=300,
        ),
        comparison_checkpoints=tuple(
            CheckpointReference(
                kind="comparison",
                uri=f"s3://example/comparison-{index}",
                checkpoint_sha256=f"{index + 4:064x}",
                payload_inventory_sha256=f"{index + 31:064x}",
                payload_file_count=2,
                payload_size_bytes=100,
            )
            for index in range(27)
        ),
        checkpoint_payload_bytes=3_000,
        created_at=datetime.now(UTC),
    )
    request_path = tmp_path / "request.json"
    preparation_path = tmp_path / "preparation.json"
    request_path.write_bytes(request.canonical_bytes())
    preparation_path.write_bytes(preparation.canonical_bytes())
    fake = _FakeMlflow()
    monkeypatch.setattr(market_tracking, "_mlflow", lambda _uri: fake)

    run_id = market_tracking.log_preparation_run(
        request=request,
        preparation=preparation,
        request_path=request_path,
        preparation_path=preparation_path,
        tracking_uri=request.mlflow_tracking_uri or "",
    )

    assert run_id == "mlflow-data-run"
    assert fake.experiments == [market_tracking.CORPUS_EXPERIMENT]
    assert len(fake.inputs) == 1
    assert fake.inputs[0][0].digest == "sha256:" + "d" * 29
    assert fake.inputs[0][2]["artifact_sha256"] == "d" * 64
    assert fake.inputs[0][1] == "preparation_source"
    assert {Path(path).name for path, _ in fake.artifacts} == {
        "request.json",
        "preparation.json",
    }


def test_c4_lineage_requires_separate_development_and_final_buckets() -> None:
    tabular_development = SimpleNamespace(access_scope="development")
    tabular_final = SimpleNamespace(access_scope="final_test")
    sequence_development = SimpleNamespace(access_scope="development")
    sequence_final = SimpleNamespace(access_scope="final_test")
    final_release_uri = "s3://aimada-wave1-final-e00g6zvxpr00/releases/release/staging"
    tabular_final_uri = f"{final_release_uri}/manifests/tabular-projection.json"
    sequence_final_uri = f"{final_release_uri}/manifests/sequence-projection.json"
    denial = FinalAccessDenialEvidence(
        development_identity_id="development-job",
        tabular_final_uri=tabular_final_uri,
        sequence_final_uri=sequence_final_uri,
    )
    values = {
        "tabular_development": tabular_development,
        "tabular_development_source_uri": (
            "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release/tabular"
        ),
        "tabular_final": tabular_final,
        "tabular_final_source_uri": final_release_uri,
        "sequence_development": sequence_development,
        "sequence_development_source_uri": (
            "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release/sequence"
        ),
        "sequence_final": sequence_final,
        "sequence_final_source_uri": final_release_uri,
        "denial": denial,
    }

    market_tracking._verify_release_boundaries(**values)

    values["tabular_final_source_uri"] = (
        "s3://aimada-wave1-dev-e00g6zvxpr00/releases/release/test"
    )
    with pytest.raises(ValueError, match="segregated bucket"):
        market_tracking._verify_release_boundaries(**values)
