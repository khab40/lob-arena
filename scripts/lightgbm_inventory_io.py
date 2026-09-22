"""Standard-library byte inspection; never deserialize model or tabular payloads."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_file(root, name):
    require(isinstance(name, str) and name, 'Missing relative artifact path')
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts
            and str(relative) == name and '\\' not in name, 'Noncanonical artifact path')
    path = root / name
    require(path.resolve() == path.absolute() and path.is_relative_to(root), 'Artifact symlink or escape')
    require(stat.S_ISREG(path.stat().st_mode), 'Artifact is not a regular file')
    return path


def load_json(path):
    require(path.stat().st_size <= 4 * 1024 * 1024, 'Metadata exceeds inspection bound')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate metadata key')
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError('Nonfinite metadata number')

    return json.loads(path.read_bytes(), object_pairs_hook=unique, parse_constant=invalid_constant)


def verify_ref(root, ref):
    path = safe_file(root, ref['uri'])
    require(re.fullmatch(r'[a-f0-9]{64}', ref['sha256']) is not None, 'Invalid artifact digest')
    require(type(ref['size_bytes']) is int and path.stat().st_size == ref['size_bytes'], 'Artifact size differs')
    require(digest(path) == ref['sha256'], 'Artifact digest differs')
    return path


def verify_result(root, expected_success):
    success = safe_file(root, 'SUCCESS')
    require(digest(success) == expected_success, 'Result inventory differs from freeze')
    inventory = load_json(success)
    require(inventory['schema_version'] == 'lightgbm_wave1_input_inventory_v1', 'Unknown inventory schema')
    entries = inventory['files']
    require(isinstance(entries, list) and entries, 'Empty result inventory')
    names = [entry['path'] for entry in entries]
    require(len(names) == len(set(names)), 'Duplicate inventory path')
    require(not {'SUCCESS', 'checksums.sha256'} & set(names), 'Recursive inventory marker')
    for entry in entries:
        verify_ref(root, {**entry, 'uri': entry['path']})
    actual = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'Symlink in result tree')
        if not path.is_dir():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(names) | {'SUCCESS', 'checksums.sha256'}, 'Result file set differs')
    expected = ''.join(f"{e['sha256']}  {e['path']}\n" for e in sorted(entries, key=lambda e: e['path']))
    require(safe_file(root, 'checksums.sha256').read_text() == expected, 'Checksum inventory differs')
    return sorted(entries, key=lambda entry: entry['path'])


def write_new(path, report, source):
    path = Path(path).absolute()
    require(path.resolve() == path, 'Output symlink or noncanonical path')
    require(not path.is_relative_to(source), 'Output must be outside frozen evidence')
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n'
    with path.open('x') as stream:
        stream.write(raw)
