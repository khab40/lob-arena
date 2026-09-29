"""Exact, bounded metadata GETs; no listings, payloads, writes or permission changes."""
import json
from pathlib import Path
import sys

from .lineage_context import PhaseVerifier, context
from .lineage_inventory import MAX_OBJECT, PHASE_SECONDS, phase_keys
from .lineage_proposal import require_proposal
from .role_audit_bundle import MAX_BUNDLE, read_bounded
from .verification_spec import INPUT_BUCKET, canonical, digest
from .verification_transport import client, deadline


def read_metadata(s3, phase, key):
    if key not in phase_keys(phase):
        raise ValueError("object escaped exact phase allowlist")
    response = s3.get_object(Bucket=INPUT_BUCKET, Key=key)
    body = response["Body"]
    try:
        size, version = response.get("ContentLength"), response.get("VersionId")
        if (type(size) is not int or not 0 < size <= MAX_OBJECT
                or not isinstance(version, str) or not version or version == "null"):
            raise ValueError("metadata size or immutable version is invalid")
        raw = body.read(size + 1)
        if len(raw) != size:
            raise ValueError("metadata body differs from declared length")
        return raw, {"key": key, "version_id": version, "size_bytes": size, "sha256": digest(raw)}
    finally:
        body.close()


def restore_phase_one(anchor, path):
    verifier = PhaseVerifier(anchor, 1)
    receipts = json.loads(read_bounded(path / "receipts.json", MAX_OBJECT))
    if not isinstance(receipts, list) or len(receipts) != len(verifier.keys):
        raise ValueError("phase one receipts are incomplete")
    for index, (key, receipt) in enumerate(zip(verifier.keys, receipts, strict=True)):
        raw = read_bounded(path / f"metadata-{index:02d}.json", MAX_OBJECT)
        version = receipt.get("version_id")
        if (not isinstance(version, str) or not version or version == "null"
                or receipt != {"key": key, "version_id": version, "size_bytes": len(raw), "sha256": digest(raw)}):
            raise ValueError("retained metadata differs from phase one receipt")
        verifier.accept(key, raw)
    if json.loads(read_bounded(path / "verification.json", MAX_OBJECT)) != verifier.result(receipts):
        raise ValueError("phase one verification receipt changed")
    return verifier.inventories


def collect(s3, bundle, phase, output, phase_one=None):
    anchor = context(read_bounded(bundle, MAX_BUNDLE))
    if (phase == 1 and phase_one is not None) or (phase == 2 and phase_one is None):
        raise ValueError("phase two requires retained phase one; phase one must not supply it")
    inventories = restore_phase_one(anchor, phase_one) if phase == 2 else None
    verifier = PhaseVerifier(anchor, phase, inventories)
    output.mkdir(parents=True, exist_ok=False)
    receipts, attempts = [], 0
    try:
        with deadline(PHASE_SECONDS):
            for index, key in enumerate(verifier.keys):
                attempts += 1
                raw, receipt = read_metadata(s3, phase, key)
                receipts.append(receipt)
                (output / f"metadata-{index:02d}.json").write_bytes(raw)
                verifier.accept(key, raw)
            result = verifier.result(receipts)
    except Exception as error:
        (output / "failure.json").write_bytes(canonical({"error_type": type(error).__name__,
            "source_separation_verified": False, "gpu_ready": False}))
        raise
    finally:
        (output / "receipts.json").write_bytes(canonical(receipts))
        (output / "measurements.json").write_bytes(canonical({"get_attempts": attempts,
            "completed_response_bytes": sum(item["size_bytes"] for item in receipts),
            "response_byte_bound": len(verifier.keys) * (MAX_OBJECT + 1),
            "deadline_seconds": PHASE_SECONDS, "payload_reads": 0, "model_runs": 0}))
    (output / "verification.json").write_bytes(canonical(result))
    return result


def main():
    if len(sys.argv) not in (5, 6):
        raise SystemExit("usage: lineage_transport APPROVED_PROPOSAL_SHA BUNDLE PHASE NEW_OUTPUT [RETAINED_PHASE_ONE]")
    try:
        require_proposal(sys.argv[1])
        result = collect(client(), Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4]),
            Path(sys.argv[5]) if len(sys.argv) == 6 else None)
    except Exception as error:
        raise SystemExit(f"Lineage metadata collection failed: {type(error).__name__}") from None
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
