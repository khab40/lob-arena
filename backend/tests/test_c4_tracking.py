import json
from pathlib import Path

import pytest

pytest.importorskip("lightgbm")

from app.ml.lightgbm.c4_evaluation import evaluate_c4_observations  # noqa: E402
from app.ml.lightgbm.tracking import _benchmark_metrics, _c4_benchmark_tags  # noqa: E402
from test_c4_evaluation import observations, profile  # noqa: E402
from test_c4_replay_evidence import fixture  # noqa: E402


def test_c4_metrics_are_namespaced_and_do_not_claim_canonical_event_rates(tmp_path):
    report = evaluate_c4_observations(observations(), profile=profile(), frozen_threshold=0.5)
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(report))
    metrics = _benchmark_metrics(path)
    assert metrics["c4.test.lightgbm.row_f1"] == 0.5
    assert metrics["c4.test.rules.row_f1"] == 1
    assert all(name.startswith("c4.test.") for name in metrics)
    assert not any("canonical_events" in name for name in metrics)
    report["metrics"]["lightgbm.false_alerts_per_million_events"] = 0
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="exact observation metric inventory"):
        _benchmark_metrics(path)


def test_c4_report_must_bind_prediction_release_and_observation_semantics(tmp_path):
    predictions = fixture(tmp_path)["predictions"]
    report = evaluate_c4_observations(observations(), profile=profile(), frozen_threshold=0.5) | dict(
        same_observations_verified=True,
        prediction_manifest_sha256=predictions.manifest_hash(),
        model_binding=predictions.binding.model_dump(mode="json"),
        row_count=predictions.row_count,
    )
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(report))
    tags = _c4_benchmark_tags(path, predictions)
    assert tags["seven_date_benchmark_compliance"] == "false"
    assert tags["evaluation_contract"] == "g8_c4_supervised_observations_v1"
    for change in (
        {"row_count": 900},
        {"same_observations_verified": False},
        {"prediction_manifest_sha256": "e" * 64},
        {"frozen_threshold": 0.9},
        {"negative_label_source": "verified_clean"},
        {"model_binding": {}},
    ):
        path.write_text(json.dumps(report | change))
        with pytest.raises(ValueError, match="verified comparison"):
            _c4_benchmark_tags(path, predictions)


def test_c4_report_real_local_mlflow_roundtrip(tmp_path, monkeypatch):
    """Transport integration, not a canonical-comparison or remote rehearsal.

    This synthetic fixture supplies an all-silent rules detector. Production
    callers must instead use evaluate_c4_release to establish provenance.
    """
    mlflow = pytest.importorskip("mlflow")
    import pyarrow.parquet as pq
    from app.ml.lightgbm import cloud_runner
    from serverless.jobs.g8_rehearsal import rehearse

    previous_uri = mlflow.get_tracking_uri()
    original_log = cloud_runner.log_governed_evaluation_run
    expected = {}

    def log_with_synthetic_report(**kwargs):
        predictions = kwargs["predictions"]
        rows = pq.read_table(kwargs["artifact_root"] / predictions.predictions.uri).to_pylist()
        for row in rows:
            row.update(
                rules_alert=False,
                label_source=("synthetic_scenario" if row["label"] else "research_control_assumption"),
            )
        report = evaluate_c4_observations(rows, profile=profile(), frozen_threshold=predictions.threshold)
        report.update(
            same_observations_verified=True,
            prediction_manifest_sha256=predictions.manifest_hash(),
            model_binding=predictions.binding.model_dump(mode="json"),
        )
        path = kwargs["artifact_root"] / "c4-metrics.json"
        path.write_text(json.dumps(report, allow_nan=False))
        expected.update(content=path.read_bytes(), metrics=_benchmark_metrics(path))
        return original_log(**kwargs, benchmark_results_path=path)

    monkeypatch.setattr(cloud_runner, "log_governed_evaluation_run", log_with_synthetic_report)
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    output = tmp_path / "rehearsal"
    try:
        rehearse(output, Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py")
        client = mlflow.MlflowClient(tracking_uri=(output / "mlruns").as_uri())
        experiment = client.get_experiment_by_name("lob-arena/governed-evaluation")
        runs = client.search_runs([experiment.experiment_id])
        assert len(runs) == 1
        run = runs[0]
        assert run.info.status == "FINISHED"
        assert run.data.tags["seven_date_benchmark_compliance"] == "false"
        assert run.data.tags["evaluation_contract"] == "g8_c4_supervised_observations_v1"
        assert {key: run.data.metrics[key] for key in expected["metrics"]} == expected["metrics"]
        assert "c4.test.rules.row_precision" not in run.data.metrics  # undefined, not zero
        artifact = client.download_artifacts(run.info.run_id, "governed-evaluation/c4-metrics.json")
        assert Path(artifact).read_bytes() == expected["content"]
        assert run.inputs.dataset_inputs
    finally:
        mlflow.set_tracking_uri(previous_uri)
