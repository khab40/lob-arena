"""Source preparation is offline, portable and does not evaluate the final fold."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("lightgbm")

from app.ml.lightgbm import cloud_runner  # noqa: E402
from serverless.jobs import prepare_g8_native_sources as sources  # noqa: E402
from serverless.jobs.g8_rehearsal import prepare_sources  # noqa: E402


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-sources") / "source-build"
    calls = []
    original = cloud_runner.predict_governed_fold

    def predict(*args, **kwargs):
        calls.append(kwargs.get("fold"))
        if kwargs.get("fold") == "test":
            raise AssertionError("source preparation attempted final scoring")
        return original(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("source preparation attempted final scoring or MLflow logging")

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(cloud_runner, "predict_governed_fold", predict)
        patcher.setattr(cloud_runner, "_run_final", forbidden)
        patcher.setattr(cloud_runner, "log_governed_evaluation_run", forbidden)
        receipt = sources.prepare(root)
    assert "test" not in calls
    return root, receipt


def test_prepare_complete_sources_without_final_evaluation(prepared):
    root, receipt = prepared
    assert receipt["checkpoint_count"] == 27
    assert receipt["replay_domain_count"] == 30
    assert receipt["synthetic_test_row_count"] == 198
    assert receipt["local_source_verification_passed"]
    assert receipt["candidate_sha256"] != sources.PRODUCTION_CANDIDATE
    assert receipt["candidate_uri"] == sources.CANDIDATE_URI
    assert receipt["input_uri"] == sources.INPUT_URI
    assert not receipt["remote_sources_staged"]
    assert not receipt["remote_authentication_verified"]
    assert not receipt["native_storage_verified"]
    assert not receipt["production_g8_complete"]
    assert not (root / "build/mlruns").exists()
    assert not (root / "build/published").exists()


def test_verifies_relocated_package_without_build_workspace(prepared, tmp_path):
    root, receipt = prepared
    copy = tmp_path / "package"
    shutil.copytree(root / "package", copy)
    # The verifier cannot consult the original package or build directory.
    hidden = root.with_name(root.name + "-hidden")
    root.rename(hidden)
    try:
        assert sources.verify(copy, expected_sha256=receipt["source_package_sha256"]) == receipt
    finally:
        hidden.rename(root)


@pytest.mark.parametrize("change", ["candidate", "comparison", "extra", "symlink", "marker"])
def test_tampering_rejected(prepared, tmp_path, change):
    root, receipt = prepared
    copy = tmp_path / "package"
    shutil.copytree(root / "package", copy)
    if change == "candidate":
        (copy / "payload/sources/candidate/candidate.json").write_bytes(b"{}")
    elif change == "comparison":
        next((copy / "payload/sources/input/comparison-evidence").rglob("alerts.jsonl")).write_bytes(b"{}")
    elif change == "extra":
        (copy / "payload/unlisted").write_bytes(b"extra")
    elif change == "symlink":
        (copy / "payload/link").symlink_to(root / "build")
    else:
        (copy / "source-package.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        sources.verify(copy, expected_sha256=receipt["source_package_sha256"])


def test_rehashed_absolute_c4_path_rejected(prepared, tmp_path):
    root, _ = prepared
    copy = tmp_path / "package"
    shutil.copytree(root / "package", copy)
    path = copy / "payload/c4-inputs.json"
    data = json.loads(path.read_bytes())
    data["candidate"] = str(root / "build/selected/candidate.json")
    path.write_text(json.dumps(data))
    raw = sources.canonical(sources.SourcePackage(inventory=sources._inventory(copy / "payload", sources.LIMITS)))
    (copy / "source-package.json").write_bytes(raw)
    with pytest.raises(ValueError, match="fixed portable layout"):
        sources.verify(copy, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_preparation_never_overwrites_existing_output(prepared):
    with pytest.raises(FileExistsError):
        sources.prepare(prepared[0])


def test_preparation_rejects_production_campaign_before_creating_output(tmp_path):
    target = tmp_path / "never-created"
    with pytest.raises(ValueError, match="explicitly synthetic"):
        prepare_sources(target, campaign="nasdaq-g6-development-20260907", c4=True)
    assert not target.exists()


def test_relative_output_is_supported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receipt = sources.prepare(Path("relative-output"))
    assert sources.verify(Path("relative-output/package"), expected_sha256=receipt["source_package_sha256"]) == receipt


def test_rehashed_wrong_projection_layout_rejected(prepared, tmp_path):
    root, _ = prepared
    copy = tmp_path / "package"
    shutil.copytree(root / "package", copy)
    request_path = copy / "payload/request.json"
    data = json.loads(request_path.read_bytes())
    data["input"]["projection_artifact_root"] = "projection-artifacts"
    request_path.write_text(json.dumps(data))
    raw = sources.canonical(sources.SourcePackage(inventory=sources._inventory(copy / "payload", sources.LIMITS)))
    (copy / "source-package.json").write_bytes(raw)
    with pytest.raises(ValueError, match="isolated synthetic rehearsal"):
        sources.verify(copy, expected_sha256=hashlib.sha256(raw).hexdigest())
