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
