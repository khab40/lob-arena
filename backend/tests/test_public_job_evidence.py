"""Inert public-export boundaries; never execute a Job or load signing custody."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts/public_job_evidence.py"
SPEC = importlib.util.spec_from_file_location("public_job_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def command():
    return ["nebius", "ai", "job", "create", "--parent-id", "project-fixture123", "--name", "fixture",
        "--image", "cr.eu-north1.nebius.cloud/fixture/tr@sha256:" + "a" * 64,
        "--platform", "gpu-l40s-a", "--preset", "1gpu-8vcpu-32gb", "--timeout", "1h",
        "--restart-policy", "never", "--on-demand", "--env-secret",
        "AWS_ACCESS_KEY_ID=mbsec-fixtureid@mbsecver-fixtureversion", "--env-secret",
        "AWS_SECRET_ACCESS_KEY=mbsec-fixturekey@mbsecver-fixtureversion", "--inject-file",
        "/tmp/package/request.json.gz:/opt/research/holdout-request.json.gz", "--async", "--format", "json"]


def raw(argv=None):
    return json.dumps(command() if argv is None else argv).encode()


def test_view_is_non_executable_deterministic_and_binds_exact_bytes():
    original = raw()
    metadata = {"issue": 341, "proposal_sha256": "b" * 64}
    view = MODULE.public_view(original, metadata)
    assert view["executable"] is False
    assert view["operation"] == "nebius.ai.job.create"
    assert "command" not in view and "argv" not in view
    assert view["exact_command_sha256"] == hashlib.sha256(original).hexdigest()
    assert view["credential_roles"] == ["s3_access_key_id", "s3_secret_access_key"]
    encoded = MODULE.canonical(view)
    assert b"mbsec-" not in encoded and b"mbsecver-" not in encoded and b"/tmp/package" not in encoded
    assert MODULE.canonical(MODULE.public_view(original, dict(reversed(list(metadata.items()))))) == encoded
    assert raw() == original


def test_byte_identity_is_preserved_instead_of_rehashing_normalized_input():
    compact = raw()
    pretty = json.dumps(command(), indent=2).encode()
    left, right = MODULE.public_view(compact), MODULE.public_view(pretty)
    assert left["exact_command_sha256"] != right["exact_command_sha256"]
    left.pop("exact_command_sha256")
    right.pop("exact_command_sha256")
    assert left == right


@pytest.mark.parametrize("metadata", [[], {"password": "fixture"}, {"note": "# Markdown"},
    {"request_sha256": {"password": "nested"}}, {"issue": True}, {"source_commit": "https://example.invalid"}])
def test_unsafe_metadata_writes_no_output(tmp_path, metadata):
    exact = tmp_path / "create-argv.json"
    exact.write_bytes(raw())
    destination = tmp_path / "public.json"
    with pytest.raises(ValueError):
        MODULE.write_public_view(exact, destination, metadata)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == [exact]
    assert exact.read_bytes() == raw()


@pytest.mark.parametrize("extra", [
    ["--env", "PASSWORD=fixture"], ["--registry-password", "fixture"], ["--unknown", "value"],
    ["--name", "duplicate"], ["--inject-file", "/tmp/private.key:/opt/research/context-private.key"],
    ["--env-secret", "OTHER_ROLE=mbsec-fixture@mbsecver-fixture"],
    ["--env-secret", "AWS_ACCESS_KEY_ID=mbsec-fixture@mbsecver-fixture"],
    ["--inject-file", "https://example.invalid/request.json.gz:/opt/research/holdout-request.json.gz"],
    ["--env-secret", "AWS_ACCESS_KEY_ID=" + "AK" + "IA" + "A" * 16],
    ["--inject-file", "-----BEGIN " + "PRIVATE KEY-----"], ["--name", "Bearer fixture"],
    ["--args", "# arbitrary Markdown"], ["--retries"],
])
def test_unsafe_command_writes_no_output(tmp_path, extra):
    exact = tmp_path / "create-argv.json"
    original = raw(command() + extra)
    exact.write_bytes(original)
    output = tmp_path / "public.json"
    with pytest.raises(ValueError):
        MODULE.write_public_view(exact, output)
    assert not output.exists() and exact.read_bytes() == original
    assert list(tmp_path.iterdir()) == [exact]


@pytest.mark.parametrize("value", [b"not json", b"{}", b"[]", b"[false]", b"[\"bash\",\"-c\",\"x\"]", b"x" * 65537])
def test_malformed_command_rejected(value):
    with pytest.raises(ValueError):
        MODULE.public_view(value)


def test_atomic_export_returns_separate_hash_and_cannot_overwrite_package(tmp_path):
    exact = tmp_path / "create-argv.json"
    original = raw()
    exact.write_bytes(original)
    public = tmp_path / "public.json"
    receipt = MODULE.write_public_view(exact, public, {"issue": 341})
    assert receipt["public_view_sha256"] == hashlib.sha256(public.read_bytes()).hexdigest()
    assert receipt["exact_command_sha256"] == hashlib.sha256(original).hexdigest()
    assert receipt["public_view_sha256"] != receipt["exact_command_sha256"]
    assert receipt["executable"] is False
    with pytest.raises(FileExistsError):
        MODULE.write_public_view(exact, public)
    with pytest.raises(ValueError):
        MODULE.write_public_view(exact, exact)
    assert exact.read_bytes() == original
    assert len(list(tmp_path.iterdir())) == 2


def test_output_symlink_is_not_followed(tmp_path):
    exact = tmp_path / "create-argv.json"
    exact.write_bytes(raw())
    output = tmp_path / "public.json"
    output.symlink_to(exact)
    with pytest.raises(ValueError):
        MODULE.write_public_view(exact, output)
    assert exact.read_bytes() == raw()


def test_staged_public_command_fixture_is_supported_without_private_package_reads():
    fixture = SCRIPT.parents[1] / "docs/evidence/transformer-holdout-recovery-create-argv-20261007.json"
    original = fixture.read_bytes()
    view = MODULE.public_view(original, {"issue": 341})
    assert view["settings"]["timeout"] == "1h"
    assert view["injected_file_roles"] == ["approval-preview.json", "request.json.gz"]
    assert view["exact_command_sha256"] == hashlib.sha256(original).hexdigest()
    assert fixture.read_bytes() == original


@pytest.mark.parametrize("metadata_bytes", [
    b'{"source_commit":{"password":"fixture"},"source_commit":"' + b"a" * 40 + b'"}',
    b'{"source_commit":"' + b"a" * 40 + b'","\\u0073ource_commit":"' + b"b" * 40 + b'"}',
])
def test_cli_rejects_duplicate_metadata_without_publishing(tmp_path, metadata_bytes):
    exact = tmp_path / "create-argv.json"
    exact.write_bytes(raw())
    metadata = tmp_path / "metadata.json"
    metadata.write_bytes(metadata_bytes)
    output = tmp_path / "public.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "--command", str(exact), "--output", str(output),
        "--metadata", str(metadata)], capture_output=True, check=False)
    assert result.returncode != 0 and not result.stdout
    assert b"duplicate JSON keys rejected" in result.stderr
    assert not output.exists() and exact.read_bytes() == raw()
    assert metadata.read_bytes() == metadata_bytes
    assert set(tmp_path.iterdir()) == {exact, metadata}


def test_strict_json_rejects_nested_duplicate_objects():
    with pytest.raises(ValueError, match="duplicate JSON keys rejected"):
        MODULE.strict_json(b'{"outer":{"same":1,"same":2}}')
    with pytest.raises(ValueError, match="invalid command JSON"):
        MODULE.public_view(b'["nebius",{"same":1,"same":2}]')


def test_cli_valid_metadata_still_exports_separately_hashed_view(tmp_path):
    exact = tmp_path / "create-argv.json"
    exact.write_bytes(raw())
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"issue": 341, "source_commit": "a" * 40}))
    output = tmp_path / "public.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "--command", str(exact), "--output", str(output),
        "--metadata", str(metadata)], capture_output=True, check=False)
    assert result.returncode == 0 and not result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["public_view_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads(output.read_bytes())["metadata"] == {"issue": 341, "source_commit": "a" * 40}
    assert exact.read_bytes() == raw()
