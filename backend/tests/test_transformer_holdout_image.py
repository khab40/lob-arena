import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("holdout_image", ROOT / "scripts/transformer_holdout_image.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def context(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    lock = root / "configs/experiments/transformer/holdout-runtime-lock-20261005.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"base_image": CLI.BASE, "files": {"numerical.py": "a" * 64}}))
    dockerfile = root / "serverless/transformer_research/Dockerfile.holdout"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text("FROM " + CLI.BASE + "\n")
    for name in CLI.OVERLAY:
        path = root / "backend/app/ml/transformer" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("declared static overlay: " + name)
    package = tmp_path / "package.json"
    package.write_bytes(b"declared metadata, no weights")
    monkeypatch.setattr(CLI, "PACKAGE_SHA", hashlib.sha256(package.read_bytes()).hexdigest())
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
    git("init", "--object-format=sha1")
    git("add", ".")
    git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture")
    return root, tmp_path / "image-context", package, "cr.eu-north1.nebius.cloud/fixture/tr", git("rev-parse", "HEAD").decode().strip()


def test_image_context_preserves_immutable_base_and_never_overwrites(tmp_path, monkeypatch):
    args = context(tmp_path, monkeypatch)
    receipt = CLI.prepare(*args)
    assert receipt["base_image"] == CLI.BASE and receipt["model_execution"] is False
    assert receipt["cloud_gets"] == receipt["jobs_created"] == 0
    assert not receipt["execution_authorized"]
    assert receipt["source_commit"] == args[4]
    assert (args[1] / "source-commit").read_text() == args[4]
    for name, item in receipt["files"].items():
        raw = (args[1] / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"] and len(raw) == item["size_bytes"]
    before = (args[1] / "context-manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        CLI.prepare(*args)
    assert (args[1] / "context-manifest.json").read_bytes() == before


@pytest.mark.parametrize("defect", ["package", "base", "protected_overlay", "dockerfile", "missing"])
def test_invalid_image_context_fails_before_creation(tmp_path, monkeypatch, defect):
    root, output, package, repository, source = context(tmp_path, monkeypatch)
    lock = root / "configs/experiments/transformer/holdout-runtime-lock-20261005.json"
    if defect == "package":
        package.write_bytes(b"changed")
    elif defect in ("base", "protected_overlay"):
        value = json.loads(lock.read_bytes())
        if defect == "base":
            value["base_image"] += "changed"
        else:
            value["files"]["backend/app/ml/transformer/" + CLI.OVERLAY[0]] = "a" * 64
        lock.write_text(json.dumps(value))
    elif defect == "dockerfile":
        (root / "serverless/transformer_research/Dockerfile.holdout").write_text("FROM mutable:tag\n")
    else:
        (root / "backend/app/ml/transformer" / CLI.OVERLAY[-1]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        CLI.prepare(root, output, package, repository, source)
    assert not output.exists()


@pytest.mark.parametrize("defect", ["wrong_commit", "dirty_overlay", "staged_overlay", "dirty_lock", "missing_git"])
def test_source_provenance_failure_never_creates_context(tmp_path, monkeypatch, defect):
    args = list(context(tmp_path, monkeypatch))
    if defect == "wrong_commit":
        args[4] = "0" * 40
    elif defect in ("dirty_overlay", "staged_overlay"):
        (args[0] / "backend/app/ml/transformer" / CLI.OVERLAY[0]).write_text("wrong source")
        if defect == "staged_overlay":
            subprocess.check_call(["git", "-C", str(args[0]), "add", "."])
    elif defect == "dirty_lock":
        (args[0] / "configs/experiments/transformer/holdout-runtime-lock-20261005.json").write_text("changed")
    else:
        (args[0] / ".git").rename(args[0] / "retained-git")
    with pytest.raises(ValueError, match="Git"):
        CLI.prepare(*args)
    assert not args[1].exists()


def test_context_capture_cannot_substitute_bytes_after_dirty_check(tmp_path, monkeypatch):
    args = context(tmp_path, monkeypatch)
    original = CLI.source_tree
    def raced(root, source):
        original(root, source)
        (root / "backend/app/ml/transformer" / CLI.OVERLAY[0]).write_text("raced source")
    monkeypatch.setattr(CLI, "source_tree", raced)
    with pytest.raises(ValueError, match="declared Git commit"):
        CLI.prepare(*args)
    assert not args[1].exists()


def test_dockerfile_has_no_free_form_source_argument():
    raw = (ROOT / "serverless/transformer_research/Dockerfile.holdout").read_text()
    assert "SOURCE_COMMIT" not in raw
    assert "context-manifest.json source-commit Dockerfile" in raw


@pytest.mark.parametrize("length", [64, 65])
def test_image_repository_length_boundary(length):
    prefix = "cr.eu-north1.nebius.cloud/fixture/"
    repository = prefix + "a" * (length - len(prefix))
    if length == 64:
        assert CLI.repository(repository) == repository
    else:
        with pytest.raises(ValueError, match="64-character"):
            CLI.repository(repository)
