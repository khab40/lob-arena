"""Offline, bounded evidence for the future CPU role audit; no cloud authority."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from app.market_data.projections import (
    FrozenPublicSampleRoot, SequenceProjectionManifest, TabularProjectionManifest,
)
from .campaign_spec import configuration, configuration_sha256
from .contracts import InputContract, Normalization
from .data import baseline_order
from .role_manifest import metadata_plan
from .role_provenance import metadata_keys, verify_chain
from .verification_spec import ROOT_SHA, SEQUENCE_SHA, TABULAR_SHA, canonical, digest

MAX_BUNDLE = 512 * 1024
MAX_FILE = 256 * 1024
RECEIPTS_SHA = "0d8f588de3248127276a3c10b3d928d9f2477d3977897d49422e7313cc4bf020"
MANIFESTS = {"frozen-root.json": ROOT_SHA, "tabular-projection.json": TABULAR_SHA,
             "sequence-projection.json": SEQUENCE_SHA}
METADATA_NAMES = tuple(f"metadata-{i:02d}.json" for i in range(29))
NAMES = {*MANIFESTS, *METADATA_NAMES, "receipts.json", "normalization.json"}


def read_bounded(path: Path, limit: int):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError("evidence file exceeds its byte bound or is empty")
    return raw


def verify(raw: bytes):
    """Authenticate every byte before interpreting lineage; never opens row shards."""
    if not 0 < len(raw) <= MAX_BUNDLE:
        raise ValueError("audit bundle exceeds its byte bound or is empty")
    bundle = json.loads(raw)
    if (not isinstance(bundle, dict) or canonical(bundle) != raw
            or set(bundle) != {"schema_version", "campaign_sha256", "files"}
            or bundle["schema_version"] != "transformer_role_audit_bundle_v1"
            or bundle["campaign_sha256"] != configuration_sha256()):
        raise ValueError("noncanonical or unrelated audit bundle")
    files = bundle["files"]
    if not isinstance(files, dict) or set(files) != NAMES:
        raise ValueError("audit evidence inventory changed")
    if any(not isinstance(value, str) for value in files.values()):
        raise ValueError("audit evidence must retain exact UTF-8 text")
    files = {name: value.encode("utf-8") for name, value in files.items()}
    if any(not 0 < len(value) <= MAX_FILE for value in files.values()):
        raise ValueError("audit evidence exceeds its byte bound")
    pins = {**MANIFESTS, "receipts.json": RECEIPTS_SHA,
            "normalization.json": configuration()["inputs"]["normalization_sha256"]}
    if any(digest(files[name]) != sha for name, sha in pins.items()):
        raise ValueError("audit evidence differs from its frozen checksum")
    receipts = json.loads(files["receipts.json"])
    keys = metadata_keys()
    if not isinstance(receipts, list) or len(receipts) != len(keys):
        raise ValueError("metadata receipts are incomplete")
    blobs = {}
    for name, key, receipt in zip(METADATA_NAMES, keys, receipts, strict=True):
        content = files[name]
        if (receipt != {"key": key, "version_id": "1", "size_bytes": len(content),
                        "sha256": digest(content)}):
            raise ValueError("metadata differs from the verified object receipt")
        blobs[key] = content
    root = FrozenPublicSampleRoot.model_validate_json(files["frozen-root.json"])
    tabular = TabularProjectionManifest.model_validate_json(files["tabular-projection.json"])
    sequences = SequenceProjectionManifest.model_validate_json(files["sequence-projection.json"])
    roles = metadata_plan(root, tabular, sequences)
    sources = [source for source in root.sources if source.fold == "validation"]
    if len(sources) != 1:
        raise ValueError("audit requires the single frozen validation source")
    provenance = verify_chain(blobs, sources[0],
        [s.run_id for s in tabular.shards if s.fold == "validation"])
    contract = InputContract(root=root, tabular_manifest_sha256=TABULAR_SHA,
        sequence_manifest_sha256=SEQUENCE_SHA, training_shards=tuple(sorted(
            (s for s in tabular.shards if s.fold == "train"), key=baseline_order)))
    normalizer = Normalization.model_validate_json(files["normalization.json"])
    if normalizer.training_binding_sha256 != contract.training_binding():
        raise ValueError("normalizer belongs to another training release")
    return {"schema_version": "transformer_role_audit_bundle_receipt_v1",
        "bundle_sha256": digest(raw), "bundle_size_bytes": len(raw),
        "campaign_sha256": configuration_sha256(), "metadata_sha256": digest(canonical(roles)),
        "metadata_objects": len(blobs), "metadata_chain_verified": provenance["metadata_chain_verified"],
        "normalization_sha256": pins["normalization.json"], "training_binding_verified": True,
        "source_separation_verified": False, "gpu_ready": False,
        "execution_authorized": False, "payload_reads": 0, "model_runs": 0}


def prepare(inputs: Path, metadata: Path, normalizer: Path, output: Path):
    paths = {name: inputs / "manifests" / name for name in MANIFESTS}
    paths.update({name: metadata / name for name in (*METADATA_NAMES, "receipts.json")})
    paths["normalization.json"] = normalizer
    raw = canonical({"schema_version": "transformer_role_audit_bundle_v1",
        "campaign_sha256": configuration_sha256(),
        "files": {name: read_bounded(path, MAX_FILE).decode("utf-8") for name, path in paths.items()}})
    result = verify(raw)
    with output.open("xb") as stream:
        stream.write(raw)
    return result


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: role_audit_bundle INPUT_DIRECTORY METADATA_DIRECTORY NORMALIZER NEW_BUNDLE")
    print(canonical(prepare(*(Path(arg) for arg in sys.argv[1:]))).decode())


if __name__ == "__main__":
    main()
