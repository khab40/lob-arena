"""Read-only, bounded metadata collection; caller supplies an authorized identity."""
from __future__ import annotations

from pathlib import Path
import sys

from .role_manifest import load_metadata
from .role_provenance import PREPARATION_KEY, metadata_keys, preparation, verify_chain
from .verification_spec import INPUT_BUCKET, canonical, digest
from .verification_transport import client, deadline

MAX_OBJECT = 256 * 1024
MAX_SECONDS = 300


def read_metadata(s3, key):
    if key not in metadata_keys():
        raise ValueError("object is outside the exact validation metadata inventory")
    response = s3.get_object(Bucket=INPUT_BUCKET, Key=key)
    body = response["Body"]
    try:
        size = response.get("ContentLength")
        version = response.get("VersionId")
        if (type(size) is not int or not 0 < size <= MAX_OBJECT
                or not isinstance(version, str) or not version or version == "null"):
            raise ValueError("metadata size or immutable version is missing or invalid")
        raw = body.read(size + 1)
        if len(raw) != size:
            raise ValueError("metadata body differs from its declared length")
        return raw, {"key": key, "version_id": version,
            "size_bytes": size, "sha256": digest(raw)}
    finally:
        body.close()


def collect(s3, inputs: Path, output: Path):
    root, tabular, _ = load_metadata(inputs)
    sources = [source for source in root.sources if source.fold == "validation"]
    if len(sources) != 1:
        raise ValueError("expected one frozen validation source")
    source = sources[0]
    output.mkdir(parents=True, exist_ok=False)
    receipts, blobs = [], {}
    requests = 0
    try:
        with deadline(MAX_SECONDS):
            for index, key in enumerate(metadata_keys()):
                requests += 1
                raw, receipt = read_metadata(s3, key)
                receipts.append(receipt)
                (output / f"metadata-{index:02d}.json").write_bytes(raw)
                blobs[key] = raw
                if key == PREPARATION_KEY:
                    # Authenticate references before any checkpoint GET.
                    preparation(raw, source)
            result = verify_chain(blobs, source,
                [s.run_id for s in tabular.shards if s.fold == "validation"])
            result["root_identity_sha256"] = root.canonical_hash()
            result["object_receipts_sha256"] = digest(canonical(receipts))
            (output / "provenance.json").write_bytes(canonical(result))
    except Exception as error:
        # Never serialize SDK exception text, which may contain request secrets.
        (output / "failure.json").write_bytes(canonical({"error_type": type(error).__name__,
            "source_separation_verified": False, "gpu_ready": False}))
        raise
    finally:
        (output / "receipts.json").write_bytes(canonical(receipts))
        (output / "measurements.json").write_bytes(canonical({"get_attempts": requests,
            "completed_response_bytes": sum(item["size_bytes"] for item in receipts),
            "response_byte_bound": len(metadata_keys()) * (MAX_OBJECT + 1),
            "deadline_seconds": MAX_SECONDS, "payload_reads": 0, "model_runs": 0}))
    return result


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: role_provenance_transport INPUT_DIRECTORY NEW_OUTPUT_DIRECTORY")
    try:
        result = collect(client(), Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception as error:
        raise SystemExit(f"Metadata collection failed: {type(error).__name__}") from None
    print(canonical({"metadata_chain_verified": result["metadata_chain_verified"],
        "source_separation_verified": False, "gpu_ready": False}).decode())


if __name__ == "__main__":
    main()
