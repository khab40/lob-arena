import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("lightgbm")

from app.ml.lightgbm.c4_evaluation import evaluate_c4_observations  # noqa: E402
from app.ml.lightgbm.tracking import _benchmark_metrics, _c4_benchmark_tags  # noqa: E402
from test_c4_evaluation import observations, profile  # noqa: E402
from test_c4_replay_evidence import fixture  # noqa: E402


def _logger_arguments(tmp_path, monkeypatch):
    from app.ml.lightgbm import tracking

    predictions = fixture(tmp_path)["predictions"]
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes(b"{}")
    checksum_path = tmp_path / "checksums.sha256"
    checksum_path.write_text("fixture")
    prediction_path = tmp_path / "prediction-manifest.json"
    prediction_path.write_bytes(predictions.canonical_bytes())
    # Isolate the report intake boundary; full bundle/lineage verification is
    # exercised by the real local MLflow integration and release tests below.
    monkeypatch.setattr(tracking, "verify_complete_lightgbm_v1_release", lambda *a, **kw: None)
    arguments = dict(
        artifact_root=tmp_path,
        training=None,
        calibration=None,
        predictions=predictions,
        bundle=SimpleNamespace(canonical_bytes=lambda: b"{}"),
        bundle_path=bundle_path,
        checksum_path=checksum_path,
        prediction_manifest_path=prediction_path,
    )
    report = evaluate_c4_observations(observations(), profile=profile(), frozen_threshold=0.5) | dict(
        same_observations_verified=True,
        prediction_manifest_sha256=predictions.manifest_hash(),
        model_binding=predictions.binding.model_dump(mode="json"),
        row_count=predictions.row_count,
    )
    return arguments, report


@pytest.mark.parametrize("variant", ["normal", "missing_schema", "legacy_schema", "wrapped", "duplicate"])
def test_self_asserted_report_is_rejected_before_mlflow(tmp_path, monkeypatch, variant):
    from app.ml.lightgbm import tracking

    arguments, report = _logger_arguments(tmp_path, monkeypatch)
    report["metrics"]["lightgbm.row_f1"] = 0.999
    if variant == "missing_schema":
        report.pop("schema_version")
    elif variant == "legacy_schema":
        report["schema_version"] = "governed_benchmark_results_v2"
    elif variant == "wrapped":
        report = {"metrics": {"precision": 0.9}, "extra_evidence": [report]}
    path = tmp_path / "forged.json"
    content = json.dumps(report)
    if variant == "duplicate":
        content = '{"same_observations_verified":false,' + content[1:]
    path.write_text(content)

    def forbidden_mlflow(_):
        pytest.fail("unverified C4 report reached MLflow")

    monkeypatch.setattr(tracking, "_mlflow", forbidden_mlflow)
    with pytest.raises(ValueError, match="C4|duplicate keys"):
        tracking.log_governed_evaluation_run(**arguments, benchmark_results_path=path)


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


@pytest.mark.parametrize("mutation", [None, "metrics", "candidate_sha256", "evaluation_profile_sha256", "profile_file"])
def test_c4_report_real_local_mlflow_roundtrip(tmp_path, monkeypatch, mutation):
    """Transport integration, not a canonical-comparison or remote rehearsal.

    The real evaluator verifies the candidate/model/root/projection. Only its
    canonical checkpoint/join input is substituted by a synthetic silent rules
    fixture (those validators have separate tests). The logger must invoke the
    evaluator again; a caller's previous result is never sufficient.
    """
    mlflow = pytest.importorskip("mlflow")
    import pyarrow.parquet as pq
    from app.ml.lightgbm import cloud_runner
    from app.ml.lightgbm import c4_replay_evidence
    from app.ml.lightgbm.c4_evaluation import C4EvaluationInputs, C4EvaluationProfile
    from app.market_data.projections import FrozenPublicSampleRoot
    from app.ml.lightgbm.artifacts import sha256_file
    from serverless.jobs.g8_rehearsal import rehearse

    previous_uri = mlflow.get_tracking_uri()
    original_log = cloud_runner.log_governed_evaluation_run
    expected = {}
    evaluations = []

    def log_with_synthetic_report(**kwargs):
        predictions = kwargs["predictions"]
        rows = pq.read_table(kwargs["artifact_root"] / predictions.predictions.uri).to_pylist()
        for row in rows:
            row.update(
                rules_alert=False,
                label_source=("synthetic_scenario" if row["label"] else "research_control_assumption"),
            )
        root_path = output / "final_test/manifests/frozen-root.json"
        root = FrozenPublicSampleRoot.model_validate_json(root_path.read_bytes())
        projection_path = output / "final_test/manifests/tabular-projection.json"
        comparison_path = output / "comparison.json"
        comparison_path.write_text("{}")
        candidate_path = output / "selected/candidate.json"
        evaluation_profile = C4EvaluationProfile(
            candidate_sha256=sha256_file(candidate_path),
            frozen_root_sha256=root.canonical_hash(),
            projection_sha256=sha256_file(projection_path),
            comparison_evidence_sha256=sha256_file(comparison_path),
        )
        profile_path = output / "profile.json"
        profile_path.write_text(evaluation_profile.model_dump_json())
        inputs = C4EvaluationInputs(
            profile=profile_path,
            frozen_root=root_path,
            projection=projection_path,
            comparison=comparison_path,
            candidate=candidate_path,
        )

        def paired_fixture(**arguments):
            evaluations.append(arguments["predictions"].manifest_hash())
            yield from rows

        monkeypatch.setattr(c4_replay_evidence, "verified_replay_paths", lambda *a, **kw: {})
        monkeypatch.setattr(c4_replay_evidence, "paired_observations", paired_fixture)
        report = c4_replay_evidence.evaluate_c4_release(
            profile=evaluation_profile,
            root=root,
            projection_path=projection_path,
            comparison_path=comparison_path,
            artifact_root=kwargs["artifact_root"],
            candidate_path=candidate_path,
            predictions=predictions,
        )
        if mutation == "metrics":
            report["metrics"]["lightgbm.row_f1"] = 0.123456
        elif mutation == "profile_file":
            profile_path.write_text(
                evaluation_profile.model_copy(update={"candidate_sha256": "0" * 64}).model_dump_json()
            )
        elif mutation is not None:
            report[mutation] = "0" * 64
        path = kwargs["artifact_root"] / "c4-metrics.json"
        path.write_text(json.dumps(report, allow_nan=False))
        expected.update(content=path.read_bytes(), metrics=_benchmark_metrics(path))
        expected["inputs"] = inputs
        return original_log(**kwargs, benchmark_results_path=path, c4_evaluation_inputs=inputs)

    monkeypatch.setattr(cloud_runner, "log_governed_evaluation_run", log_with_synthetic_report)
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    output = tmp_path / "rehearsal"
    try:
        if mutation is not None:
            with pytest.raises(ValueError, match="C4.*(evaluator output|frozen candidate)"):
                rehearse(output, Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py")
            assert not (output / "mlruns").exists()
            assert not (output / "published/SUCCESS").exists()
            return
        rehearse(output, Path(__file__).resolve().parents[2] / "serverless/jobs/run_lightgbm_g8.py")
        assert len(evaluations) == 2  # producer and independent logger verification
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
        import hashlib

        assert run.data.tags["c4_evaluation_report_sha256"] == hashlib.sha256(expected["content"]).hexdigest()
        assert run.inputs.dataset_inputs
        # The postprocessing CLI adds source identities. Verify these against
        # the completed immutable result while evaluating a separate copy.
        import shutil
        from app.ml.lightgbm.tracking import _verified_benchmark_snapshot
        from app.ml.lightgbm.contracts import DetectorPredictionsManifest

        copied = tmp_path / "artifact-copy"
        shutil.copytree(output / "published/artifacts", copied)
        source = cloud_runner.verify_wave1_result(output / "published")
        payload = json.loads(expected["content"])
        payload.update(
            source_result_inventory_sha256=sha256_file(output / "published/SUCCESS"),
            source_request_sha256=source.request_sha256,
            source_mlflow_run_id=source.mlflow_run_id,
        )
        report_path = copied / "c4-metrics.json"
        report_path.write_text(json.dumps(payload))
        inputs = expected["inputs"].model_copy(update={"source_result": output / "published"})
        predictions = DetectorPredictionsManifest.model_validate_json(
            (copied / "prediction/prediction-manifest.json").read_bytes()
        )
        with _verified_benchmark_snapshot(
            report_path, artifact_root=copied, predictions=predictions, c4_inputs=inputs
        ) as (_, tags, snapshot):
            original = snapshot.read_bytes()
            report_path.write_text("{}")
            assert snapshot.read_bytes() == original
            assert tags["same_observations_verified"] == "true"
        payload["source_request_sha256"] = "0" * 64
        report_path.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match="verified evaluator output"):
            with _verified_benchmark_snapshot(
                report_path, artifact_root=copied, predictions=predictions, c4_inputs=inputs
            ):
                pytest.fail("forged source identity was accepted")
    finally:
        mlflow.set_tracking_uri(previous_uri)


def test_legacy_benchmark_snapshot_cannot_be_swapped_after_validation(tmp_path):
    from app.ml.lightgbm.tracking import _verified_benchmark_snapshot

    predictions = fixture(tmp_path)["predictions"]
    path = tmp_path / "legacy.json"
    original = json.dumps({"metrics": {"precision": 0.75, "recall": 0.5, "f1": 0.6}}).encode()
    path.write_bytes(original)
    with _verified_benchmark_snapshot(
        path, artifact_root=tmp_path, predictions=predictions, c4_inputs=None
    ) as evidence:
        metrics, tags, snapshot = evidence
        path.write_text(json.dumps({"same_observations_verified": True, "metrics": {"precision": 1.0}}))
        assert metrics == {"test_precision": 0.75, "test_recall": 0.5, "test_f1": 0.6}
        assert tags == {}
        assert snapshot != path
        assert snapshot.read_bytes() == original
    assert not snapshot.exists()


def test_c4_input_manifest_resolves_relative_paths_and_rejects_assertions(tmp_path):
    from app.ml.lightgbm.c4_evaluation import C4EvaluationInputs

    path = tmp_path / "inputs.json"
    values = {name: name + ".json" for name in ("profile", "frozen_root", "projection", "comparison", "candidate")}
    path.write_text(json.dumps(values))
    inputs = C4EvaluationInputs.from_file(path)
    assert inputs.profile == tmp_path / "profile.json"
    path.write_text(json.dumps(values | {"same_observations_verified": True}))
    with pytest.raises(ValueError):
        C4EvaluationInputs.from_file(path)


def test_bundle_cli_requires_report_and_tracking_for_c4_inputs():
    from scripts.lightgbm_v1 import main, parse_args

    argv = ["bundle", "--created-at", "2026-09-14T00:00:00+00:00"]
    for flag in (
        "artifact-root",
        "output",
        "training-manifest",
        "calibration-manifest",
        "prediction-manifest",
        "feature-schema",
        "validation-metrics",
        "feature-importance",
        "contributions",
        "c4-evaluation-inputs",
    ):
        argv.extend(["--" + flag, "unused.json"])
    assert parse_args(argv).c4_evaluation_inputs == Path("unused.json")
    with pytest.raises(ValueError, match="require benchmark results and MLflow"):
        main(argv)
