"""Unexpected import bytecode must not escape the approved source inventory."""
import importlib.util
import os
from pathlib import Path
import py_compile
import subprocess

import pytest


def test_authenticated_sources_do_not_authorize_cached_bytecode(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/collect_transformer_lineage_metadata.py"
    spec = importlib.util.spec_from_file_location("bytecode_operator", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    source = repo / "backend/app/inert.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 'approved'\n")
    check_output = subprocess.check_output
    def git(*args):
        return check_output(["git", *args], cwd=repo, text=True).strip()
    def proxy(args, **kwargs):
        assert args[:3] == ["rtk", "proxy", "git"]
        return check_output(args[2:], **kwargs)
    monkeypatch.setattr(module.subprocess, "check_output", proxy)
    git("init", "-q")
    git("add", "backend")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "inert source")
    commit = git("rev-parse", "HEAD")
    proposal = {"implementation_commit": commit, "backend_tree": git("rev-parse", "HEAD:backend")}
    out = tmp_path / "audit"
    code = out / ("runtime-" + commit[:7])
    target = code / "backend/app/inert.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    assert module.pinned_backend(repo, out, proposal) == code
    # Valid timestamp/size header, but different executable bytes than the source.
    malicious = tmp_path / "unapproved.py"
    malicious.write_text("value = 'injected'\n")
    assert malicious.stat().st_size == target.stat().st_size
    os.utime(malicious, (target.stat().st_atime, target.stat().st_mtime))
    cache = Path(importlib.util.cache_from_source(str(target)))
    cache.parent.mkdir()
    py_compile.compile(str(malicious), cfile=str(cache), doraise=True)
    probe = importlib.util.spec_from_file_location("inert", target)
    loaded = importlib.util.module_from_spec(probe)
    probe.loader.exec_module(loaded)
    assert loaded.value == "injected"  # Demonstrate Python accepts the cache.
    with pytest.raises(ValueError, match="unexpected files"):
        module.pinned_backend(repo, out, proposal)
