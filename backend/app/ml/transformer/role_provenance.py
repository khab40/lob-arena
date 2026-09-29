"""C4 validation metadata chain; deliberately not a source-separation proof."""
from __future__ import annotations

from itertools import product

from app.market_data.preparation import PreparationManifest
from app.market_data.preparation_checkpoints import ComparisonCheckpoint, NormalizedCheckpoint
from .role_manifest import SYMBOLS
from .verification_spec import INPUT_BUCKET, digest

DATE = "2019-10-30"
PREPARATION_RUN = "nasdaq-c3-10302019-cf426c0-v2-20260903"
BASE = "data/public-sample-v1/"
PREPARATION_KEY = f"{BASE}prepared/{DATE}/{PREPARATION_RUN}/preparation.json"
CHECKPOINT_PREFIX = f"{BASE}preparation-checkpoints/{DATE}/{PREPARATION_RUN}/"
FAMILIES = ("spoofing_like_wall", "layering_like", "quote_stuffing")
COMPARISONS = tuple(enumerate(product(SYMBOLS, FAMILIES, (41, 42, 43)), 1))


def checkpoint_keys():
    return [CHECKPOINT_PREFIX + "normalized/checkpoint.json"] + [
        f"{CHECKPOINT_PREFIX}comparisons/{number:03d}-{symbol.lower()}-"
        f"{family.replace('_', '-')}-s{seed}/checkpoint.json"
        for number, (symbol, family, seed) in COMPARISONS]


def metadata_keys():
    """Exact metadata keys derived from the retained C4 request and C3 naming contract."""
    return [PREPARATION_KEY, *checkpoint_keys()]


def preparation(raw, source):
    if source.fold != "validation" or str(source.trade_date) != DATE:
        raise ValueError("provenance requires the frozen validation source")
    if digest(raw) != source.preparation_manifest_sha256:
        raise ValueError("preparation checksum differs from frozen C4")
    record = PreparationManifest.model_validate_json(raw)
    for field in ("source_sha256", "source_manifest_sha256", "parser_config_sha256"):
        if getattr(record, field) != getattr(source, field):
            raise ValueError("preparation source identity differs from frozen C4")
    if (record.run_id != PREPARATION_RUN or record.source_filename != source.filename
            or tuple(record.symbols) != SYMBOLS):
        raise ValueError("preparation source domain changed")
    references = [record.normalized_checkpoint, *record.comparison_checkpoints]
    expected = [f"s3://{INPUT_BUCKET}/{key.removesuffix('/checkpoint.json')}"
                for key in checkpoint_keys()]
    if [ref.uri for ref in references] != expected:
        raise ValueError("checkpoint inventory escaped exact validation allowlist")
    return record


def checkpoint(raw, reference, binding, model):
    if digest(raw) != reference.checkpoint_sha256:
        raise ValueError("checkpoint checksum differs from preparation")
    record = model.model_validate_json(raw)
    if record.binding_sha256 != binding:
        raise ValueError("checkpoint belongs to another preparation request")
    for field in ("payload_inventory_sha256", "payload_file_count", "payload_size_bytes"):
        if getattr(record, field) != getattr(reference, field):
            raise ValueError("checkpoint payload inventory binding changed")
    return record


def verify_chain(blobs, source, validation_run_ids):
    if set(blobs) != set(metadata_keys()):
        raise ValueError("metadata chain is incomplete or contains extra objects")
    prepared = preparation(blobs[PREPARATION_KEY], source)
    keys = checkpoint_keys()
    normalized = checkpoint(blobs[keys[0]], prepared.normalized_checkpoint,
        prepared.checkpoint_binding_sha256, NormalizedCheckpoint)
    if set(normalized.manifests) != set(SYMBOLS) or set(prepared.dataset_ids) != set(SYMBOLS):
        raise ValueError("normalized symbol inventory changed")
    domains = {}
    for symbol in SYMBOLS:
        dataset = normalized.manifests[symbol]
        if (dataset.symbol != symbol or dataset.trade_date != DATE
                or dataset.source_type != "nasdaq_itch"
                or dataset.parser_config_sha256 != source.parser_config_sha256
                or dataset.dataset_id != prepared.dataset_ids[symbol]):
            raise ValueError("normalized dataset escaped its source domain")
        domains[symbol] = {"dataset_id": dataset.dataset_id,
            "source_stream_sha256": dataset.source_stream_sha256,
            "start_time_ms": dataset.start_time_ms, "end_time_ms": dataset.end_time_ms}
    controls, hybrids, streams = {}, [], {}
    for key, ref, (number, (symbol, family, seed)) in zip(
            keys[1:], prepared.comparison_checkpoints, COMPARISONS, strict=True):
        record = checkpoint(blobs[key], ref, prepared.checkpoint_binding_sha256, ComparisonCheckpoint)
        base = f"xnas-{DATE}-{symbol.lower()}"
        if ((record.comparison_number, record.symbol, record.attack_family, record.seed)
                != (number, symbol, family, seed)
                or record.control_run_id != f"{base}-control"
                or record.hybrid_run_id != f"{base}-{family}-s{seed}"):
            raise ValueError("comparison domain differs from frozen campaign")
        identity = (record.control_run_id, record.control_event_stream_sha256)
        if controls.setdefault(symbol, identity) != identity:
            raise ValueError("control event stream changed between replay variants")
        hybrids.append(record.hybrid_run_id)
        streams[record.hybrid_run_id] = record.hybrid_event_stream_sha256
    expected_controls = {symbol: value[0] for symbol, value in controls.items()}
    if (prepared.control_run_ids != expected_controls or list(prepared.campaign_run_ids) != hybrids
            or set(validation_run_ids) != set(hybrids) | set(expected_controls.values())
            or len(validation_run_ids) != 30):
        raise ValueError("replay runs do not exactly cover frozen validation shards")
    streams.update({run: sha for run, sha in controls.values()})
    return {"schema_version": "transformer_role_provenance_metadata_v1",
        "preparation_sha256": source.preparation_manifest_sha256,
        "checkpoint_binding_sha256": prepared.checkpoint_binding_sha256,
        "metadata_objects": len(blobs), "normalized_domains": domains,
        "replay_event_streams": streams, "metadata_chain_verified": True,
        "source_separation_verified": False, "gpu_ready": False,
        "remaining_proof": ["source_observation_overlap", "label_horizon_overlap",
            "replay_manifest_and_feature_lineage", "class_support_and_platform_readiness"]}
