"""Metadata-only compatibility audit; never opens features or authorizes a run."""

from __future__ import annotations

from pathlib import Path

from app.corpus.models import load_benchmark_protocol
from app.market_data.projections import C4MlflowDatasetReleaseReceipt, FrozenPublicSampleRoot
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_runner import FrozenCandidate, _verify_cloud_artifact
from app.ml.lightgbm.contracts import LightGbmTrainingRun


def assess_benchmark_compatibility(
    *,
    frozen_root_path: Path,
    lineage_path: Path,
    candidate_path: Path,
    benchmark_protocol_path: Path,
) -> dict:
    """Prove the candidate/C4 binding, then compare actual protocol identities.

    Matching human-readable protocol IDs are not proof of interchangeable
    protocol contracts. A compatible identity alone is not a submission gate:
    replay availability, metric implementation and authorization remain separate.
    """
    root = FrozenPublicSampleRoot.model_validate_json(frozen_root_path.read_bytes())
    lineage = C4MlflowDatasetReleaseReceipt.model_validate_json(lineage_path.read_bytes())
    if (
        lineage.release_id != root.release_id
        or lineage.root_file_sha256 != sha256_file(frozen_root_path)
        or lineage.root_identity_sha256 != root.canonical_hash()
    ):
        raise ValueError("C4 root is not bound to the dataset lineage receipt")
    candidate = FrozenCandidate.model_validate_json(candidate_path.read_bytes())
    if candidate.test_fold_accessed:
        raise ValueError("selected candidate was not frozen before test access")
    training_path = _verify_cloud_artifact(candidate_path.parent / "artifacts", candidate.training_manifest)
    training = LightGbmTrainingRun.model_validate_json(training_path.read_bytes())
    binding = training.binding
    expected = (
        root.protocol_id,
        root.protocol_sha256,
        root.corpus_id,
        root.corpus_sha256,
        root.split_id,
        root.assignment_sha256,
        root.feature_schema_version,
        root.feature_config_sha256,
        root.feature_release_id,
        root.feature_release_sha256,
    )
    observed = (
        binding.protocol_id,
        binding.protocol_hash,
        binding.corpus_id,
        binding.corpus_hash,
        binding.split_id,
        binding.assignment_hash,
        binding.feature_schema_version,
        binding.feature_config_hash,
        training.feature_release_id,
        training.feature_release_sha256,
    )
    if observed != expected or training.data_policy.test_fold_accessed:
        raise ValueError("frozen candidate training metadata does not match the C4 root")
    protocol = load_benchmark_protocol(benchmark_protocol_path)
    reasons = []
    if protocol.protocol_id != root.protocol_id:
        reasons.append("protocol_id_mismatch")
    if protocol.protocol_hash() != root.protocol_sha256:
        reasons.append("protocol_hash_mismatch")
    if protocol.feature_schema_version != root.feature_schema_version:
        reasons.append("feature_schema_mismatch")
    source_dates = sorted({source.trade_date.isoformat() for source in root.sources})
    if len(source_dates) < protocol.corpus.distinct_dates:
        reasons.append("insufficient_frozen_source_dates")
    return {
        "schema_version": "g8_benchmark_compatibility_v1",
        "status": "incompatible" if reasons else "identity_compatible_only",
        "candidate_hash": sha256_file(candidate_path),
        "training_manifest_sha256": sha256_file(training_path),
        "frozen_root_file_sha256": sha256_file(frozen_root_path),
        "frozen_root_identity_sha256": root.canonical_hash(),
        "c4_mlflow_receipt_sha256": sha256_file(lineage_path),
        "benchmark_protocol_file_sha256": sha256_file(benchmark_protocol_path),
        "candidate_c4_binding_verified": True,
        "frozen_protocol_id": root.protocol_id,
        "frozen_protocol_sha256": root.protocol_sha256,
        "benchmark_protocol_id": protocol.protocol_id,
        "benchmark_protocol_sha256": protocol.protocol_hash(),
        "frozen_source_dates": source_dates,
        "benchmark_minimum_distinct_dates": protocol.corpus.distinct_dates,
        "negative_label_source": root.negative_label_source,
        "blocking_reasons": reasons,
        "test_rows_read_by_audit": False,
        "replay_availability_verified": False,
        "submission_authorized": False,
    }
