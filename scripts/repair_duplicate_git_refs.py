"""Inspect copied loose refs; use --apply to preserve and quarantine them."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="preserve commits and quarantine invalid refs")
    args = parser.parse_args()
    common = Path(git("rev-parse", "--git-common-dir")).resolve()
    candidates = []
    for path in sorted((common / "refs").rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(common).as_posix()
        if subprocess.run(["git", "check-ref-format", name], capture_output=True).returncode == 0:
            continue
        if path.is_symlink() or not re.search(r" [2-9][0-9]*$", name):
            raise SystemExit(f"Unsupported invalid ref, inspect manually: {name}")
        raw = path.read_bytes()
        oid = raw.decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
            raise SystemExit(f"Not a plain object hash: {name}")
        if git("cat-file", "-t", oid) != "commit":
            raise SystemExit(f"Not a commit: {name}")
        recovery = f"refs/recovery/copied-refs/{oid}"
        backup = common / "ref-copy-backups" / name
        if backup.exists() and backup.read_bytes() != raw:
            raise SystemExit(f"Conflicting backup: {backup}")
        existing = subprocess.run(
            ["git", "rev-parse", "--verify", recovery], capture_output=True, text=True
        )
        if existing.returncode == 0 and existing.stdout.strip() != oid:
            raise SystemExit(f"Conflicting recovery ref: {recovery}")
        candidates.append((path, name, raw, oid, recovery, backup))
    for path, name, raw, oid, recovery, backup in candidates:
        print(f"{name} -> {recovery}")
        if not args.apply:
            continue
        # Preserve reachability before removing the malformed ref. Never overwrite.
        existing = subprocess.run(["git", "rev-parse", "--verify", recovery], capture_output=True, text=True)
        if existing.returncode == 0:
            if existing.stdout.strip() != oid:
                raise SystemExit(f"Conflicting recovery ref: {recovery}")
        else:
            git("update-ref", recovery, oid, "0" * len(oid))
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            with backup.open("xb") as stream:
                stream.write(raw)
        if path.read_bytes() != raw:
            raise SystemExit(f"Ref changed during repair: {name}")
        path.unlink()
    print(f"{len(candidates)} copied ref(s) {'repaired' if args.apply else 'found; rerun with --apply to repair'}.")


if __name__ == "__main__":
    main()
