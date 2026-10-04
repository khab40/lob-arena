"""Inert operator preflight; no model execution or cloud access."""
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import transformer_comparison_prepare as prepare  # noqa: E402


def test_sdk_drift_blocks_before_any_file_or_custody_read(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare.importlib.metadata, "version", lambda _: "different")
    with pytest.raises(ValueError, match="dependency"):
        prepare.prepare(*(tmp_path / name for name in
            ("legacy", "confirmations", "bundle", "source", "output", "custody")),
            "a" * 40, "sha256:" + "b" * 64)
    assert not (tmp_path / "output").exists()


def test_preparation_preserves_checkpoint_and_cannot_overwrite_attempt(tmp_path, monkeypatch):
    previous = json.loads((Path(__file__).parent / "fixtures/transformer_selected_origin.json").read_bytes())
    previous["inventory"] = {"fixture": {}}
    monkeypatch.setattr(prepare, "local_preflight", lambda *args:
                        ({"search-128-0003": previous}, {"passed": True}))
    public = SimpleNamespace(public_bytes_raw=lambda: bytes.fromhex(prepare.CONTEXT_PUBLIC_KEY))
    key = SimpleNamespace(public_key=lambda: public)
    monkeypatch.setattr(prepare, "Ed25519PrivateKey", SimpleNamespace(from_private_bytes=lambda _: key))
    custody, output = tmp_path / "custody", tmp_path / "output"
    custody.write_bytes(b"inert fixture")
    args = (tmp_path, tmp_path, tmp_path, tmp_path, output, custody, "a" * 40, "sha256:" + "b" * 64)
    result = prepare.prepare(*args)
    command = shlex.split(result["create_command"])
    assert command[:4] == ["nebius", "ai", "job", "create"]
    for flag, value in (("--timeout", "1h"), ("--retries", "1"), ("--restart-policy", "never")):
        assert command[command.index(flag) + 1] == value
    assert result["checkpoint_origin"]["checkpoint"] == previous["result"]["selected_checkpoint"]
    assert not result["jobs_created"] and not result["context_attestation_started"]
    assert not (output / "context-private.key").exists()
    original = Path(result["request_path"]).read_bytes()
    with pytest.raises(FileExistsError):
        prepare.prepare(*args)
    assert Path(result["request_path"]).read_bytes() == original
