"""Stage a hash-bound package on the existing native filesystem before Job creation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .publish_g8_native_context import MOUNT, check_mount, immutable_write, read_input, sync_directory
else:
    from publish_g8_native_context import MOUNT, check_mount, immutable_write, read_input, sync_directory


def publish(source, inventory, inventory_sha256):
    value = json.loads(read_input(inventory, inventory_sha256, 16384))
    if set(value) != {"files"} or not isinstance(value["files"], dict) or not 1 <= len(value["files"]) <= 32:
        raise ValueError("bounded package inventory required")
    if source.absolute() != source.resolve() or not source.is_dir():
        raise ValueError("canonical source directory required")
    contents = {}
    for name, ref in value["files"].items():
        path = Path(name)
        if (path.is_absolute() or name != path.as_posix() or not path.parts
                or any(p in {".", ".."} for p in path.parts)
                or not isinstance(ref, dict) or set(ref) != {"sha256", "size_bytes"}
                or type(ref["size_bytes"]) is not int or not 0 < ref["size_bytes"] <= 40960):
            raise ValueError("invalid package member")
        raw = read_input(source / name, ref["sha256"], ref["size_bytes"])
        if len(raw) != ref["size_bytes"]:
            raise ValueError("package member size differs")
        contents[name] = raw
    if any(p.is_symlink() for p in source.rglob("*")) or {
        p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()
    } != set(contents):
        raise ValueError("source package inventory differs")
    check_mount()
    destination = MOUNT / "package"
    destination.mkdir(mode=0o700, exist_ok=False)  # Never overwrite or reuse a partial package.
    directories = {destination}
    for name, raw in sorted(contents.items()):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        directories.update(target.parents[:len(Path(name).parts)])
        immutable_write(target, raw)
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        directory.chmod(0o500)
        sync_directory(directory)
    sync_directory(MOUNT)
    observed = {p.relative_to(destination).as_posix(): {
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size_bytes": p.stat().st_size}
        for p in destination.rglob("*") if p.is_file()}
    if observed != value["files"]:
        raise ValueError("native package readback differs; do not submit")
    return {"inventory_sha256": inventory_sha256, "file_count": len(observed),
            "native_package_bytes_verified": True, "job_read_only_mount_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--inventory-sha256", required=True)
    print(json.dumps(publish(**vars(parser.parse_args())), sort_keys=True))
