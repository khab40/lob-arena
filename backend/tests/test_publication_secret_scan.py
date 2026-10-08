import json
from pathlib import Path
import subprocess

import pytest

from scripts import install_publication_hooks as hooks
from scripts import publication_secret_scan as gate


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo).decode().strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "inert test")
    git(tmp_path, "config", "user.email", "inert@example.invalid")
    (tmp_path / "readme.txt").write_text("base\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_staged_snapshot_excludes_working_tree_and_untracked(repo):
    (repo / "readme.txt").write_text("staged\n")
    git(repo, "add", "readme.txt")
    (repo / "readme.txt").write_text("unstaged\n")
    (repo / "untracked.txt").write_text("not outgoing\n")
    assert gate.captured(repo, "pre-commit", "origin", "") == {"readme.txt": b"staged\n\n"}


def test_initial_commit_staging(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "first.txt").write_text("first")
    git(tmp_path, "add", "first.txt")
    assert gate.captured(tmp_path, "pre-commit", "origin", "") == {"first.txt": b"first\n"}


@pytest.mark.parametrize("name", ["outputs/custody.json", "nested/.aws/credentials",
                                 ".env", ".env.production", ".ssh/id_ed25519",
                                 "signing.key", "../escape", "/escape"])
def test_private_paths_refused(name):
    with pytest.raises(gate.ScanFailure, match="no content transmitted"):
        gate.public_path(name)


def test_deleted_custody_refused_before_any_blob_read(repo, monkeypatch):
    (repo / "outputs").mkdir()
    (repo / "outputs" / "custody.json").write_text("private")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture only")
    git(repo, "rm", "outputs/custody.json")
    original = gate.git

    def guarded(*args):
        assert "cat-file" not in args
        return original(*args)

    monkeypatch.setattr(gate, "git", guarded)
    with pytest.raises(gate.ScanFailure, match="no content transmitted"):
        gate.captured(repo, "pre-commit", "origin", "")


def test_all_61_outgoing_commits_and_removed_content_are_captured(repo, tmp_path):
    remote = repo.parent / f"{repo.name}-remote.git"
    git(repo, "init", "--bare", "-q", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    for number in range(61):
        (repo / "readme.txt").write_text(f"version {number}\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", f"iteration {number}")
    tip = git(repo, "rev-parse", "HEAD")
    # A stale tracking ref at our tip must not hide commits absent on the remote.
    git(repo, "update-ref", "refs/remotes/origin/task", tip)
    updates = f"refs/heads/task {tip} refs/heads/task {'0' * 40}\n"
    assert len(gate.outgoing(repo, "origin", updates)) == 61
    material = gate.captured(repo, "pre-push", "origin", updates)
    assert all(f"version {number}\n".encode() in material["readme.txt"] for number in range(61))
    assert b"iteration 0" in material[".publication-commit-messages.txt"]


def test_deletion_only_push_is_empty(repo):
    assert gate.outgoing(repo, "origin", f"(delete) {'0' * 40} refs/heads/task {'a' * 40}") == []


@pytest.mark.parametrize("kind", ["binary", "oversize", "symlink"])
def test_unscannable_content_fails_closed(repo, kind):
    target = repo / "new.txt"
    if kind == "symlink":
        target.symlink_to("readme.txt")
    else:
        target.write_bytes(b"\0" if kind == "binary" else b"x" * (gate.MAX_TEXT_BYTES + 1))
    git(repo, "add", "new.txt")
    with pytest.raises(gate.ScanFailure):
        gate.captured(repo, "pre-commit", "origin", "")


def test_missing_scanner_blocks_without_running_tools(repo, monkeypatch):
    monkeypatch.setattr(gate.shutil, "which", lambda _: None)
    with pytest.raises(gate.ScanFailure, match="missing"):
        gate.scan(repo, {"readme.txt": b"safe"}, "missing", "missing")


@pytest.mark.parametrize("failed", ["gitleaks", "ggshield"])
def test_scanner_failure_never_echoes_tool_content(repo, monkeypatch, capsys, failed):
    monkeypatch.setattr(gate.shutil, "which", lambda name: name)
    original = gate.run
    calls = []

    def fake(argv, cwd, **kwargs):
        if argv[0] == "git":
            return original(argv, cwd, **kwargs)
        calls.append(argv[0])
        if argv[0] == failed:
            raise gate.ScanFailure("scanner failed; publication blocked")
        return b""

    monkeypatch.setattr(gate, "run", fake)
    with pytest.raises(gate.ScanFailure):
        gate.scan(repo, {"readme.txt": b"safe"}, "gitleaks", "ggshield")
    assert calls == (["gitleaks"] if failed == "gitleaks" else ["gitleaks", "ggshield"])
    assert capsys.readouterr().out == ""


def test_actual_failure_output_is_hidden(tmp_path):
    with pytest.raises(gate.ScanFailure) as result:
        gate.run(["sh", "-c", "echo confidential; echo confidential >&2; exit 1"], tmp_path)
    assert "confidential" not in str(result.value)


def test_exact_snapshot_and_env_are_used_for_both_scanners(repo, monkeypatch):
    monkeypatch.setattr(gate.shutil, "which", lambda name: name)
    monkeypatch.setenv("GITGUARDIAN_EXIT_ZERO", "true")
    monkeypatch.setenv("GITGUARDIAN_INSTANCE", "https://invalid.example")
    monkeypatch.setenv("GG_MAX_DOC_SIZE", "1")
    original = gate.run
    calls = []

    def inspect(argv, cwd, **kwargs):
        if argv[0] == "git":
            return original(argv, cwd, **kwargs)
        assert not (cwd / "outputs").exists()
        calls.append(argv)
        if argv[0] == "ggshield":
            assert "GITGUARDIAN_EXIT_ZERO" not in gate.os.environ
            assert "GITGUARDIAN_INSTANCE" not in gate.os.environ
            assert "GG_MAX_DOC_SIZE" not in gate.os.environ
            assert argv[-1] == "./document-0.txt"
            assert "--yes" in argv
            config = Path(argv[argv.index("--config-path") + 1])
            assert config.read_text() == gate.GG_CONFIG
            assert (cwd / "document-0.txt").read_bytes() == b"index bytes"
            return json.dumps({"entities_with_incidents": [
                {"filename": str((cwd / "document-0.txt").resolve())}], "errors": []}).encode()
        assert (cwd / "readme.txt").read_bytes() == b"index bytes"
        return b""

    monkeypatch.setattr(gate, "run", inspect)
    gate.scan(repo, {"readme.txt": b"index bytes"}, "gitleaks", "ggshield")
    assert len(calls) == 2
    assert gate.os.environ["GITGUARDIAN_EXIT_ZERO"] == "true"


def test_installer_preserves_foreign_hook(repo):
    (repo / "scripts").mkdir()
    (repo / "scripts" / "publication_secret_scan.py").write_text("source")
    existing = repo / ".git/hooks/pre-push"
    existing.write_text("existing hook\n")
    binary = Path("/bin/sh")
    with pytest.raises(ValueError, match="preserved"):
        hooks.install(repo, binary, binary, binary)
    assert existing.read_text() == "existing hook\n"
    assert not (repo / ".git/hooks/pre-commit").exists()


def test_installation_is_idempotent_and_shared_by_worktrees(repo):
    (repo / "scripts").mkdir()
    (repo / "scripts" / "publication_secret_scan.py").write_text("source")
    binary = Path("/bin/sh")
    assert hooks.install(repo, binary, binary, binary) == hooks.install(repo, binary, binary, binary)
    assert (repo / ".git/hooks/pre-commit").stat().st_mode & 0o111
    assert '"$@"' in (repo / ".git/hooks/pre-push").read_text()
