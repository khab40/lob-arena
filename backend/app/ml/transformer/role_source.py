"""Authenticate the frozen audit materials before any governed row access."""
import json

from app.market_data.projections import (
    FrozenPublicSampleRoot, SequenceProjectionManifest, TabularProjectionManifest,
)
from . import role_audit_bundle
from .contracts import InputContract
from .data import baseline_order
from .role_manifest import metadata_plan
from .verification_spec import SEQUENCE_SHA, TABULAR_SHA, canonical, digest

ANCHOR_SHA = "697f29587002e8cb46f30c8942ebd1a3ac0e78701ed51e69f8aeb330431e83f3"
SOURCE_RECEIPT_SHA = "9ed4852ae01c952d76f59054e3db8ad1a8dce00b4ec7a543ce5a48641d7d07ae"
MAX_SOURCE_RECEIPT = 16 * 1024


def verify_source(raw: bytes, metadata):
    """Accept only the reviewed receipt, with its exact role and lineage bindings."""
    if not 0 < len(raw) <= MAX_SOURCE_RECEIPT or digest(raw) != SOURCE_RECEIPT_SHA:
        raise ValueError("source receipt differs from the reviewed checksum")
    source = json.loads(raw)
    if (canonical(source) != raw or source["anchor_sha256"] != ANCHOR_SHA
            or source["role_metadata_sha256"] != digest(canonical(metadata))
            or any(source[name] != metadata[name] for name in (
                "feature_release_id", "feature_release_sha256"))
            or any(source[name] is not True for name in (
                "source_separation_verified", "source_observation_separation_verified",
                "label_horizon_separation_verified"))):
        raise ValueError("source receipt is not bound to the frozen role metadata")
    expected = [{"role": group["role"], "group_sha256": group["group_sha256"],
        "base_sessions": group["base_sessions"], "row_count": group["row_count"],
        "instrument": group["source_identity"]["instrument"],
        "source_sha256": group["source_identity"]["source_sha256"],
        "run_ids": sorted(shard["run_id"] for shard in group["shards"])}
        for group in metadata["groups"]]
    observed = [{name: group[name] for name in expected[0]} for group in source["groups"]]
    if canonical(observed) != canonical(expected):
        raise ValueError("source receipt role or run coverage changed")
    names = ("anchor_sha256", "lineage_receipt_sha256", "phase_one_receipts_sha256",
        "phase_two_receipts_sha256", "role_metadata_sha256", "feature_release_id",
        "feature_release_sha256", "producer_commit", "producer_image", "proof_method")
    return {"source_receipt_sha256": digest(raw), **{name: source[name] for name in names},
        "source_separation_verified": True,
        "payload_observation_ids_reenumerated": False, "statistical_independence_claimed": False}


def authenticate(bundle_raw: bytes, source_raw: bytes):
    """Return metadata and the original normalizer; neither path reads payloads."""
    if digest(bundle_raw) != ANCHOR_SHA:
        raise ValueError("audit bundle differs from the reviewed anchor")
    role_audit_bundle.verify(bundle_raw)
    files = json.loads(bundle_raw)["files"]
    root = FrozenPublicSampleRoot.model_validate_json(files["frozen-root.json"])
    tabular = TabularProjectionManifest.model_validate_json(files["tabular-projection.json"])
    sequences = SequenceProjectionManifest.model_validate_json(files["sequence-projection.json"])
    metadata = metadata_plan(root, tabular, sequences)
    binding = verify_source(source_raw, metadata)
    contract = InputContract(root=root, tabular_manifest_sha256=TABULAR_SHA,
        sequence_manifest_sha256=SEQUENCE_SHA, training_shards=tuple(sorted(
            (shard for shard in tabular.shards if shard.fold == "train"), key=baseline_order)))
    return metadata, contract, files["normalization.json"].encode(), binding
