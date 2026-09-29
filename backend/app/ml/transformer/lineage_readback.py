"""Offline semantic readback of the two bounded metadata phases; no S3 client."""
import json
from pathlib import Path
import sys

from app.market_data.projections import FrozenPublicSampleRoot, TabularProjectionManifest
from .lineage_context import PhaseVerifier, context
from .lineage_inventory import MAX_OBJECT, REQUEST_KEY, run_members, verify_request
from .lineage_semantics import verify_run
from .role_audit_bundle import MAX_BUNDLE, METADATA_NAMES, read_bounded
from .role_provenance import metadata_keys, verify_chain
from .verification_spec import canonical, digest


def phase_readback(anchor, phase, path, inventories=None):
    verifier = PhaseVerifier(anchor, phase, inventories)
    receipts = json.loads(read_bounded(path / "receipts.json", MAX_OBJECT))
    if not isinstance(receipts, list) or len(receipts) != len(verifier.keys):
        raise ValueError("phase receipts are incomplete")
    blobs = {}
    for index, key in enumerate(verifier.keys):
        raw = read_bounded(path / f"metadata-{index:02d}.json", MAX_OBJECT)
        verifier.accept(key, raw)
        blobs[key] = raw
    expected = verifier.result(receipts)
    if json.loads(read_bounded(path / "verification.json", MAX_OBJECT)) != expected:
        raise ValueError("phase verification receipt differs from authenticated metadata")
    return blobs, verifier.inventories, expected


def verify(bundle, phase_one, phase_two):
    raw = read_bounded(bundle, MAX_BUNDLE)
    anchor = context(raw)
    files = json.loads(raw)["files"]
    root = FrozenPublicSampleRoot.model_validate_json(files["frozen-root.json"])
    tabular = TabularProjectionManifest.model_validate_json(files["tabular-projection.json"])
    first, inventories, first_receipt = phase_readback(anchor, 1, phase_one)
    second, _, second_receipt = phase_readback(anchor, 2, phase_two, inventories)
    retained = {key: files[name].encode() for key, name in zip(metadata_keys(), METADATA_NAMES, strict=True)}
    shards = {s.run_id: s for s in tabular.shards if s.fold == "validation"}
    chain = verify_chain(retained, anchor["source"], list(shards))
    request = verify_request(first[REQUEST_KEY], anchor["source"], anchor["prepared"])
    members = run_members()
    if set(shards) != {m["run_id"] for m in members}:
        raise ValueError("semantic audit does not cover the frozen validation inventory")
    records = []
    for member in members:
        shard = shards[member["run_id"]]
        stream = chain["replay_event_streams"][member["run_id"]]
        # Frozen C4 uses this field for the canonical event-stream hash.
        if (shard.replay_manifest_sha256 != stream or shard.base_session_id != member["base_session_id"]
                or shard.campaign_id != (member["run_id"] if member["mode"] == "hybrid" else None)):
            raise ValueError("frozen projection identity differs from replay domain")
        record = verify_run(member, {**first, **second}, inventories,
            dataset_id=anchor["prepared"].dataset_ids[member["symbol"]],
            stream_sha=stream, feature_config_sha=root.feature_config_sha256)
        # The verified default_label=0 spec makes every emitted row supervised.
        if record["feature_row_count"] != shard.supervised_row_count:
            raise ValueError("feature row count differs from frozen supervised row count")
        record["supervised_row_count"] = shard.supervised_row_count
        records.append(record)
    return {"schema_version": "transformer_lineage_semantics_v1", "anchor_sha256": digest(raw),
        "phase_one_receipts_sha256": first_receipt["receipts_sha256"],
        "phase_two_receipts_sha256": second_receipt["receipts_sha256"],
        "producer_commit": request.git_commit, "producer_image": request.image,
        "authenticated_metadata_objects": len(first) + len(second), "runs": records,
        "metadata_lineage_verified": True, "source_separation_verified": False,
        "class_support_verified": False, "gpu_ready": False, "execution_authorized": False,
        "remaining_proof": ["source_observation_and_label_horizon_separation", "CPU_class_support",
            "MLflow_and_platform_readiness", "exact_execution_authorization"],
        "payload_reads": 0, "cloud_reads": 0, "model_runs": 0}


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: lineage_readback BUNDLE PHASE_ONE PHASE_TWO NEW_RECEIPT")
    try:
        output = Path(sys.argv[4])
        if output.exists():
            raise FileExistsError("receipt already exists")
        result = verify(*(Path(arg) for arg in sys.argv[1:4]))
        with output.open("xb") as stream:
            stream.write(canonical(result))
    except Exception as error:
        raise SystemExit(f"Lineage readback failed: {type(error).__name__}") from None
    print(canonical({"metadata_lineage_verified": True, "runs": len(result["runs"]),
        "source_separation_verified": False, "gpu_ready": False}).decode())


if __name__ == "__main__":
    main()
