"""Inert preparation admission tests; no credentials, models or network."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("cryptography")
from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY  # noqa: E402
from app.ml.transformer.research_execution_spec import replacement_template  # noqa: E402

spec = importlib.util.spec_from_file_location("confirmation_prepare",
    Path(__file__).resolve().parents[2] / "scripts/transformer_confirmation_prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_create_has_exact_single_attempt_and_no_secret_values(tmp_path):
    request = replacement_template("seed-7", "a" * 40, "sha256:" + "b" * 64,
                                   CONTEXT_PUBLIC_KEY, "c" * 32)
    path = tmp_path / "request.json"
    command = prepare.create_command(request, path)
    assert command[:4] == ["nebius", "ai", "job", "create"]
    for flag, expected in (("--timeout", "2h"), ("--retries", "1"),
            ("--restart-policy", "never"), ("--auth-timeout", "120s")):
        assert command[command.index(flag) + 1] == expected
    assert "--async" in command and "--no-browser" in command
    selectors = [command[i + 1] for i, v in enumerate(command) if v == "--env-secret"]
    assert len(selectors) == 2 and all("=mbsec-" in x and "@mbsecver-" in x for x in selectors)
    assert str(path.resolve()) + ":/opt/research/request.json" in command


def test_modified_verification_blocks_before_output_or_custody(tmp_path):
    legacy = tmp_path / "legacy"
    directory = legacy / "smoke"
    directory.mkdir(parents=True)
    (directory / "request.json").write_text("{}")
    (directory / "verification.json").write_text(json.dumps({"status": "verified"}))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="legacy verification"):
        prepare.prepare(legacy, output, tmp_path / "missing-key", "a" * 40, "sha256:" + "b" * 64)
    assert not output.exists()


def test_prepare_is_exclusive_and_keeps_signing_key_out_of_package(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "verify_legacy", lambda _: [])
    public = SimpleNamespace(public_bytes_raw=lambda: bytes.fromhex(CONTEXT_PUBLIC_KEY))
    key = SimpleNamespace(public_key=lambda: public)
    monkeypatch.setattr(prepare, "Ed25519PrivateKey", SimpleNamespace(from_private_bytes=lambda _: key))
    custody = tmp_path / "key"
    custody.write_bytes(b"inert key fixture")
    output = tmp_path / "execution"
    result = prepare.prepare(tmp_path, output, custody, "a" * 40, "sha256:" + "b" * 64)
    assert [r["slot"] for r in result["trials"]] == ["seed-7", "seed-2027"]
    assert not (output / "context-private.key").exists()
    originals = [Path(r["request_path"]).read_bytes() for r in result["trials"]]
    with pytest.raises(FileExistsError):
        prepare.prepare(tmp_path, output, custody, "a" * 40, "sha256:" + "b" * 64)
    assert originals == [Path(r["request_path"]).read_bytes() for r in result["trials"]]
