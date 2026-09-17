"""Small, immutable Job injections for the already-staged synthetic G8 sources.

Build/verify inspect bytes only. Hydration belongs inside the approved Nebius
Job; it downloads synthetic sources without training, scoring or MLflow writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = "792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9"
ACCESS_ID_SHA256 = "4f129534101211604ce259cd5ded383065384b86797e8f7b407a810750062d5d"
# Transport headroom below the observed 64 KiB KMS plaintext boundary.
# This is our conservative bound, not a documented Nebius encoding formula.
MAX_INJECTION = 40 * 1024
METADATA = (
    "authorization/authorization-public.pem", "authorization/authorization.json",
    "authorization/authorization.sig", "c4-inputs.json", "c4-profile.json", "request.json",
)
PREFIXES = {
    "candidate": ("aimada-wave1-results-e00g6zvxpr00",
                  "campaigns/g8-native-rehearsal-20260914/development/synthetic-development"),
    "input": ("aimada-wave1-final-e00g6zvxpr00", "releases/g8-native-rehearsal-20260914/staging"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, *, size):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise ValueError("missing, linked or incorrectly sized capsule member: " + path.name)
    return path.read_bytes()


def canonical_root(root):
    if root.absolute() != root.resolve() or not root.is_dir():
        raise ValueError("canonical real directory required")


def inventory(raw):
    if sha(raw) != SOURCE_SHA256:
        raise ValueError("source inventory differs from the frozen synthetic package")
    return json.loads(raw)["inventory"]["files"]


def build(source: Path, output: Path):
    canonical_root(source)
    raw = regular(source / "source-package.json", size=74744)
    entries = inventory(raw)
    # Check retained bytes, including the 350 remote-source files, without
    # importing the model runtime or regenerating any fixtures.
    expected = {"source-package.json"} | {"payload/" + e["path"] for e in entries}
    if any(p.is_symlink() for p in source.rglob("*")) or {
        p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()
    } != expected:
        raise ValueError("retained source tree has missing, linked or unexpected members")
    for entry in entries:
        if sha(regular(source / "payload" / entry["path"], size=entry["size_bytes"])) != entry["sha256"]:
            raise ValueError("retained source bytes differ: " + entry["path"])
    if (output.absolute() != output.resolve() or output.resolve().is_relative_to(source.resolve())
            or source.resolve().is_relative_to(output.resolve())):
        raise ValueError("capsule output must be canonical")
    output.mkdir(parents=True, exist_ok=False)
    for index, start in enumerate(range(0, len(raw), MAX_INJECTION)):
        (output / f"inventory-{index}.part").write_bytes(raw[start:start + MAX_INJECTION])
    for index, name in enumerate(METADATA):
        (output / f"metadata-{index}.part").write_bytes((source / "payload" / name).read_bytes())
    return verify(output)


def verify(capsule: Path):
    canonical_root(capsule)
    names = {"inventory-0.part", "inventory-1.part"} | {f"metadata-{i}.part" for i in range(6)}
    if {p.name for p in capsule.iterdir()} != names:
        raise ValueError("capsule has missing or unexpected members")
    raw = regular(capsule / "inventory-0.part", size=MAX_INJECTION)
    raw += regular(capsule / "inventory-1.part", size=74744 - MAX_INJECTION)
    entries = inventory(raw)
    metadata = {e["path"]: e for e in entries if not e["path"].startswith("sources/")}
    if set(metadata) != set(METADATA):
        raise ValueError("unexpected source metadata")
    for index, name in enumerate(METADATA):
        entry = metadata[name]
        if sha(regular(capsule / f"metadata-{index}.part", size=entry["size_bytes"])) != entry["sha256"]:
            raise ValueError("capsule metadata differs: " + name)
    return {
        "schema_version": "g8_native_source_capsule_v2", "source_package_sha256": SOURCE_SHA256,
        "injections": {name: {"sha256": sha((capsule / name).read_bytes()),
                              "size_bytes": (capsule / name).stat().st_size} for name in sorted(names)},
        "remote_object_count": sum(e["path"].startswith("sources/") for e in entries),
        "submission_authorized": False, "native_storage_verified": False,
        "remote_mlflow_verified": False,
    }


def hydrate(capsule: Path, destination: Path, *, s3=None):
    """Restore original sealed bytes from S3, using only the fixed source prefixes.

    Caller owns native-mount/Job readback, deadline and credential-version gates.
    The access-ID fingerprint below does not attest secret-version provenance.
    """
    verify(capsule)
    if __package__:
        from .g8_source_sdk import SourceSDK
        from .stage_g8_native_sources import _credential_identity, PRODUCTION_BUCKET, PRODUCTION_KEY
    else:
        from g8_source_sdk import SourceSDK
        from stage_g8_native_sources import _credential_identity, PRODUCTION_BUCKET, PRODUCTION_KEY
    if _credential_identity() != ACCESS_ID_SHA256:
        raise ValueError("unexpected synthetic source access identity")
    if destination.absolute() != destination.resolve():
        raise ValueError("hydration destination must be canonical")
    destination.mkdir(parents=True, exist_ok=False)
    s3 = s3 or SourceSDK()
    s3.production_head_denied(PRODUCTION_BUCKET, PRODUCTION_KEY)
    raw = b"".join((capsule / f"inventory-{i}.part").read_bytes() for i in range(2))
    entries = inventory(raw)
    for entry in entries:
        name = entry["path"]
        target = destination / "payload" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in METADATA:
            target.write_bytes((capsule / f"metadata-{METADATA.index(name)}.part").read_bytes())
        else:
            _, source, relative = name.split("/", 2)
            bucket, prefix = PREFIXES[source]
            s3._transfer_json(entry["size_bytes"], "s3api", "get-object", "--bucket", bucket,
                              "--key", prefix + "/" + relative, str(target))
        if sha(regular(target, size=entry["size_bytes"])) != entry["sha256"]:
            raise ValueError("hydrated bytes differ: " + name)
    # The source seal appears only after every remote/local member verifies.
    (destination / "source-package.json").write_bytes(raw)
    return {"source_package_sha256": SOURCE_SHA256,
            "remote_objects_verified": sum(e["path"].startswith("sources/") for e in entries),
            "production_head_denied": True, "credential_version_provenance_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="build from the retained, independently verified source tree")
    args = parser.parse_args()
    result = build(args.source, args.capsule) if args.source else verify(args.capsule)
    print(json.dumps(result, indent=2))
