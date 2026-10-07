import io
import json
import sys

import pytest

from scripts import publication_secret_scan as gate
from test_publication_secret_scan import git


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "inert test")
    git(tmp_path, "config", "user.email", "inert@example.invalid")
    (tmp_path / "readme.txt").write_text("base\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_push_uses_destination_url_instead_of_fetch_repository(repo, monkeypatch):
    fetch = repo.parent / f"{repo.name}-fetch.git"
    destination = repo.parent / f"{repo.name}-push.git"
    for remote in (fetch, destination):
        git(repo, "init", "--bare", "-q", str(remote))
        git(repo, "push", "-q", str(remote), "HEAD:refs/heads/main")
    git(repo, "remote", "add", "origin", str(fetch))
    git(repo, "remote", "set-url", "--push", "origin", str(destination))
    (repo / "readme.txt").write_text("new outgoing content")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "new outgoing commit")
    tip = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "-q", str(fetch), "HEAD:refs/heads/main")
    updates = f"refs/heads/task {tip} refs/heads/task {'0' * 40}\n"
    assert gate.outgoing(repo, "origin", updates) == []
    assert gate.outgoing(repo, str(destination), updates) == [tip]
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["gate", "pre-push", "origin", str(destination),
                                     "--gitleaks", "unused", "--ggshield", "unused"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(updates))

    def inspect(_repo, material, *_tools):
        assert b"new outgoing content" in material["readme.txt"]

    monkeypatch.setattr(gate, "scan", inspect)
    assert gate.main() == 0


@pytest.mark.parametrize("filename", ["public.png", "--exit-zero", "@response"])
def test_neutral_gg_paths_preserve_text_without_option_or_extension_skips(repo, monkeypatch, filename):
    monkeypatch.setattr(gate.shutil, "which", lambda name: name)
    original = gate.run

    def inspect(argv, cwd, **kwargs):
        if argv[0] == "git":
            return original(argv, cwd, **kwargs)
        if argv[0] == "ggshield":
            assert argv[-1] == "./document-0.txt"
            assert (cwd / "document-0.txt").read_bytes() == b"captured text"
            return json.dumps({"entities_with_incidents": [
                {"filename": str((cwd / "document-0.txt").resolve())}], "errors": []}).encode()
        assert gate.git(cwd, "show", f":{filename}") == b"captured text"
        return b""

    monkeypatch.setattr(gate, "run", inspect)
    gate.scan(repo, {filename: b"captured text"}, "gitleaks", "ggshield")


@pytest.mark.parametrize("report", [{}, {"entities_with_incidents": [], "errors": []},
                                   {"entities_with_incidents": [{"filename": "document-0.txt"}],
                                    "errors": ["partial scan"]}])
def test_incomplete_gg_coverage_is_failure(repo, monkeypatch, report):
    monkeypatch.setattr(gate.shutil, "which", lambda name: name)
    original = gate.run
    monkeypatch.setattr(gate, "run", lambda argv, cwd, **kwargs:
                        original(argv, cwd, **kwargs) if argv[0] == "git" else
                        json.dumps(report).encode() if argv[0] == "ggshield" else b"")
    with pytest.raises(gate.ScanFailure, match="coverage incomplete"):
        gate.scan(repo, {"public.txt": b"text"}, "gitleaks", "ggshield")


def test_gitleaks_snapshot_disables_filters_encoding_and_line_conversion(repo, monkeypatch):
    monkeypatch.setattr(gate.shutil, "which", lambda name: name)
    original = gate.run

    def inspect(argv, cwd, **kwargs):
        if argv[0] == "git":
            return original(argv, cwd, **kwargs)
        if argv[0] == "gitleaks":
            assert gate.git(cwd, "show", ":public.txt") == b"exact\r\nbytes\n"
            attributes = gate.git(cwd, "check-attr", "--all", "--", "public.txt").decode()
            assert "filter: unset" in attributes and "working-tree-encoding: unset" in attributes
            assert "diff: set" in attributes and "text: unset" in attributes
        return json.dumps({"entities_with_incidents": [
            {"filename": str((cwd / f"document-{index}.txt").resolve())} for index in range(2)],
            "errors": []}).encode()

    monkeypatch.setattr(gate, "run", inspect)
    gate.scan(repo, {"public.txt": b"exact\r\nbytes\n",
                    ".gitattributes": b"public.txt filter=unexpected working-tree-encoding=UTF-16 text -diff\n"},
              "gitleaks", "ggshield")


def test_public_templates_remain_scannable():
    gate.public_path(".env.example")
    gate.public_path(".env.template")
