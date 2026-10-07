"""Export a strict non-executable view; never modify the exact execution package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


VALUES = {
    "--parent-id": r"project-[a-z0-9]{5,64}",
    "--name": r"[a-z0-9][a-z0-9-]{0,63}",
    "--platform": r"(?:cpu|gpu)-[a-z0-9-]{1,50}",
    "--preset": r"[1-9][0-9]*(?:gpu-[1-9][0-9]*)?vcpu-[1-9][0-9]*gb",
    "--disk-size": r"[1-9][0-9]*[KMGT]i",
    "--shm-size": r"[1-9][0-9]*[KMGT]i",
    "--subnet-id": r"vpcsubnet-[a-z0-9]{5,64}",
    "--timeout": r"[1-9][0-9]*h",
    "--restart-policy": r"never|on-failure",
    "--format": r"json",
    "--retries": r"[0-3]",
}
SWITCHES = {"--on-demand", "--async", "--no-browser", "--dry-run"}
ROLES = {"AWS_ACCESS_KEY_ID": "s3_access_key_id", "AWS_SECRET_ACCESS_KEY": "s3_secret_access_key"}
INJECTIONS = {
    "request.json.gz": "/opt/research/holdout-request.json.gz",
    "approval-preview.json": "/opt/research/holdout-approval.json",
}
SENSITIVE = re.compile(r"PRIVATE KEY|\bbearer\s|(?:AKIA|ASIA|NAKI)[A-Z0-9]{16}|\beyJ[\w-]+\.[\w-]+\.[\w-]+", re.I)
REQUIRED = {"--parent-id", "--name", "--image", "--platform", "--preset", "--timeout", "--restart-policy"}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def strict_json(raw: bytes) -> object:
    def unique_object(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate JSON keys rejected")
            result[name] = value
        return result

    return json.loads(raw, object_pairs_hook=unique_object)


def metadata_view(metadata: object) -> dict:
    if metadata is None:
        return {}
    if type(metadata) is not dict:
        raise ValueError("metadata must be a flat allowlisted object")
    for name, value in metadata.items():
        if name == "issue" and type(value) is int and value > 0:
            continue
        width = {"source_commit": 40, "proposal_sha256": 64, "request_sha256": 64, "provider_spec_sha256": 64}.get(name)
        if not width or type(value) is not str or not re.fullmatch(r"[a-f0-9]{" + str(width) + "}", value):
            raise ValueError("metadata field or value is not allowed")
    return dict(metadata)


def public_view(command_bytes: bytes, metadata: object = None) -> dict:
    if type(command_bytes) is not bytes or len(command_bytes) > 65536:
        raise ValueError("bounded JSON command bytes required")
    try:
        command = strict_json(command_bytes)
    except (ValueError, UnicodeError):
        raise ValueError("invalid command JSON") from None
    if type(command) is not list or any(type(item) is not str for item in command):
        raise ValueError("command must contain only string tokens")
    if command[:4] != ["nebius", "ai", "job", "create"]:
        raise ValueError("only the recognized Job creation command is supported")
    if any(SENSITIVE.search(item) or "://" in item or "\n" in item or "\r" in item for item in command):
        raise ValueError("credential, URL or multiline command input rejected")
    options, credentials, injections = {}, [], []
    index = 4
    while index < len(command):
        flag = command[index]
        if flag not in {*VALUES, *SWITCHES, "--image", "--env-secret", "--inject-file"}:
            raise ValueError("unknown command flag rejected")
        if flag in options:
            raise ValueError("duplicate command flag rejected")
        if flag in SWITCHES:
            options[flag] = True
            index += 1
            continue
        if index + 1 == len(command):
            raise ValueError("flag value required")
        value = command[index + 1]
        if flag == "--env-secret":
            match = re.fullmatch(r"([A-Z_]+)=mbsec-[a-z0-9]+@mbsecver-[a-z0-9]+", value)
            role = ROLES.get(match[1]) if match else None
            if not role or role in credentials:
                raise ValueError("version-pinned known credential role required")
            credentials.append(role)
        elif flag == "--inject-file":
            source, separator, target = value.partition(":")
            name = Path(source).name
            if not separator or not re.fullmatch(r"/[A-Za-z0-9_./ -]+", source) or INJECTIONS.get(name) != target:
                raise ValueError("unknown injection file or destination rejected")
            if name in injections:
                raise ValueError("duplicate injection rejected")
            injections.append(name)
        else:
            pattern = VALUES.get(flag, r"cr\.[a-z0-9-]+\.nebius\.cloud/[a-z0-9-]+/[a-z0-9_-]+@sha256:[a-f0-9]{64}")
            if not re.fullmatch(pattern, value):
                raise ValueError("command value does not match the public schema")
            if flag == "--image" and len(value.split("@sha256:")[0]) > 64:
                raise ValueError("image repository exceeds 64 characters")
            if flag == "--timeout" and int(value[:-1]) > 168:
                raise ValueError("Job timeout exceeds documented limit")
            options[flag] = value
        index += 2
    if not REQUIRED.issubset(options):
        raise ValueError("required explicit Job settings missing")
    return {"schema_version": 1, "artifact_kind": "public_job_command_view", "executable": False,
        "operation": "nebius.ai.job.create", "exact_command_sha256": hashlib.sha256(command_bytes).hexdigest(),
        "settings": {name.removeprefix("--"): value for name, value in options.items()},
        "credential_roles": sorted(credentials), "injected_file_roles": sorted(injections),
        "metadata": metadata_view(metadata)}


def write_public_view(command_path: Path, output_path: Path, metadata: object = None) -> dict:
    if command_path.is_symlink() or command_path.resolve() == output_path.resolve():
        raise ValueError("exact command must be a separate regular input")
    view = public_view(command_path.read_bytes(), metadata)
    payload = canonical(view)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output_path)  # Atomic publication refuses existing files and symlinks.
    finally:
        if temporary is not None:
            temporary.unlink()
    return {"exact_command_sha256": view["exact_command_sha256"],
            "public_view_sha256": hashlib.sha256(payload).hexdigest(), "executable": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    metadata = strict_json(args.metadata.read_bytes()) if args.metadata else None
    print(json.dumps(write_public_view(args.command, args.output, metadata), sort_keys=True))


if __name__ == "__main__":
    main()
