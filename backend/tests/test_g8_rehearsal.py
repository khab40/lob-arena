"""Exercise real C4 projection scoring, not a mocked execute_wave1_request."""

from pathlib import Path

import pytest

pytest.importorskip("lightgbm")
mlflow = pytest.importorskip("mlflow")

from serverless.jobs.g8_rehearsal import rehearse  # noqa: E402


@pytest.fixture(autouse=True)
def restore_tracking_uri():
    previous = mlflow.get_tracking_uri()
    yield
    mlflow.set_tracking_uri(previous)


def test_c4_shaped_final_scoring_publication_and_mlflow_roundtrip(tmp_path: Path) -> None:
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    receipt = rehearse(tmp_path / "rehearsal", runner)
    assert receipt["local_mlflow_status"] == "FINISHED"
    assert receipt["final_download_count"] == 1
    assert receipt["mlflow_artifact_readback_verified"]
    assert receipt["mlflow_metric_readback_verified"]
    assert receipt["conditional_publication_verified"]
    assert receipt["publication_object_count"] > 3
    assert not receipt["production_g8_complete"]
    assert not receipt["production_test_accessed"]
    assert not receipt["remote_storage_verified"]


def test_r4_wrong_root_fails_in_the_real_loader(tmp_path: Path) -> None:
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    with pytest.raises(ValueError, match="projection artifact root is missing"):
        rehearse(tmp_path / "negative-control", runner, wrong_root=True)
    assert not (tmp_path / "negative-control/mlruns").exists()
    assert not (tmp_path / "negative-control/published/SUCCESS").exists()


def test_complete_c4_canonical_comparison_and_mlflow_roundtrip(tmp_path: Path) -> None:
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    receipt = rehearse(tmp_path / "c4-rehearsal", runner, c4=True)
    assert receipt["rules_comparison_verified"]
    assert receipt["final_scoring_call_count"] == 1
    assert receipt["c4_report_sha256"]
    assert receipt["local_mlflow_status"] == "FINISHED"
    assert receipt["final_download_count"] == 1
    assert not receipt["production_test_accessed"]
    from app.ml.lightgbm.artifacts import sha256_file
    from app.ml.lightgbm.g8_evaluation import _verify_final_projection_layout

    final = tmp_path / "c4-rehearsal/c4-final_test"
    prefix = "releases/synthetic-c4/staging/"
    objects = tuple(
        dict(key=prefix + path.relative_to(final).as_posix(), sha256=sha256_file(path), size_bytes=path.stat().st_size)
        for path in final.rglob("*")
        if path.is_file()
    )
    _verify_final_projection_layout(objects, "s3://fixture/" + prefix.rstrip("/"))


def test_complete_c4_corrupt_checkpoint_cannot_create_mlflow_run(tmp_path: Path, monkeypatch) -> None:
    from app.ml.lightgbm import g8_c4_fixture

    original = g8_c4_fixture.complete_c4_fixtures

    def corrupt(*args):
        result = original(*args)
        checkpoint = result[2].parent / "checkpoint-1"
        alerts = next(checkpoint.rglob("alerts.jsonl"))
        alerts.write_bytes(alerts.read_bytes() + b"{}\n")
        return result

    monkeypatch.setattr(g8_c4_fixture, "complete_c4_fixtures", corrupt)
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    output = tmp_path / "corrupt-c4"
    with pytest.raises(ValueError, match="checksum mismatch"):
        rehearse(output, runner, c4=True)
    assert not (output / "mlruns").exists()
    assert not (output / "published/SUCCESS").exists()


def test_c4_metadata_mismatch_rejected_before_any_remote_access(tmp_path: Path, monkeypatch) -> None:
    from serverless.jobs import g8_rehearsal

    original = g8_rehearsal.write_manifest

    def corrupt(path, value):
        if path.name == "c4-profile.json":
            value = value.model_copy(update={"candidate_sha256": "f" * 64})
        return original(path, value)

    monkeypatch.setattr(g8_rehearsal, "write_manifest", corrupt)
    # This spy observes, rather than replaces, the real runner's entry point.
    # Any readiness, intent, or download call must occur after metadata validation.
    remote_calls = []
    original_patch = g8_rehearsal.patch.object

    def track_patch(target, attribute, *args, **kwargs):
        if attribute in ("_verify_mlflow_ready", "_require_empty_result", "download_s3_release"):
            def unexpected(*args, **kwargs):
                remote_calls.append(attribute)
                raise AssertionError("remote access before metadata rejection")
            return original_patch(target, attribute, unexpected)
        return original_patch(target, attribute, *args, **kwargs)

    monkeypatch.setattr(g8_rehearsal.patch, "object", track_patch)
    runner = Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py"
    with pytest.raises(ValueError, match="C4 evaluation inputs differ"):
        rehearse(tmp_path / "bad-metadata", runner, c4=True)
    assert not remote_calls
