from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ml.lightgbm import g6_campaign
from app.ml.lightgbm.g6_campaign import (
    G6CampaignPlan,
    G6SelectionPolicy,
    G6ValidationRecord,
    load_g6_plan,
    resolve_confirmation_experiment,
    seed_stability_gates,
    select_calibration,
    select_model,
    verify_g6_plan,
)
from app.ml.lightgbm.cloud_contracts import (
    APPROVED_FIXTURE_FEATURE_RELEASE_SHA256,
    LightGbmCloudJobRequest,
    Wave1FixtureInput,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "configs/experiments/lightgbm-wave1/g6-campaign-20260907.json"


def test_g6_committed_plan_freezes_exact_remaining_matrix() -> None:
    plan = load_g6_plan(PLAN)

    assert plan.development_jobs_consumed_before_g6 == 11
    assert plan.planned_job_count == 9
    assert plan.development_job_ceiling == 20
    assert [trial.group for trial in plan.trials].count("hyperparameter") == 2
    assert [trial.group for trial in plan.trials].count("feature_ablation") == 2
    assert [trial.group for trial in plan.trials].count("seed_stability") == 2
    assert [trial.group for trial in plan.trials].count("calibration") == 3
    assert {trial.random_seed for trial in plan.trials if trial.group == "seed_stability"} == {
        7,
        2027,
    }
    assert {
        trial.calibration_method_override
        for trial in plan.trials
        if trial.group == "calibration"
    } == {"raw", "platt", "isotonic"}
    assert plan.test_input_permitted is False
    assert plan.failure_replacement_permitted is False
    assert plan.mlflow_required is True
    assert plan.mlflow_experiment == "lob-arena/lightgbm-development"
    assert plan.raw_rows_uploaded_to_mlflow is False


def test_g6_plan_rejects_a_tenth_job_or_group_drift() -> None:
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    payload["trials"][0]["group"] = "feature_ablation"

    with pytest.raises(ValidationError, match="group counts"):
        G6CampaignPlan.model_validate(payload)

    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    payload["trials"].append(payload["trials"][0])
    with pytest.raises(ValidationError):
        G6CampaignPlan.model_validate(payload)


def test_g6_confirmation_is_derived_without_changing_the_selected_model() -> None:
    plan = load_g6_plan(PLAN)
    selected = plan.search_trials()[1].experiment
    assert selected is not None

    resolved = {
        trial.trial_id: resolve_confirmation_experiment(selected, trial)
        for trial in plan.confirmation_trials()
    }

    for trial in plan.confirmation_trials():
        experiment = resolved[trial.trial_id]
        assert experiment.hyperparameters == selected.hyperparameters
        assert experiment.excluded_features == selected.excluded_features
        assert experiment.calibration_method == (
            trial.calibration_method_override or selected.calibration_method
        )


def test_g6_model_selection_uses_predeclared_validation_tie_breaks() -> None:
    first = _record("first", balanced_f1=0.60, minimum_family_recall=0.70)
    second = _record("second", balanced_f1=0.61, minimum_family_recall=0.40)
    ineligible = _record(
        "ineligible",
        balanced_f1=0.99,
        minimum_family_recall=0.99,
        raw_brier=0.10,
        raw_ece=0.10,
        calibrated_brier=0.11,
        calibrated_ece=0.11,
    )

    assert select_model([first, second, ineligible]).trial_id == "second"

    tied = _record("tied", balanced_f1=0.61, minimum_family_recall=0.80)
    assert select_model([second, tied]).trial_id == "tied"


def test_g6_calibration_selection_and_seed_stability_fail_closed() -> None:
    raw = _record("raw", calibration_method="raw", calibrated_brier=0.08, calibrated_ece=0.07)
    platt = _record(
        "platt", calibration_method="platt", calibrated_brier=0.04, calibrated_ece=0.03
    )
    isotonic = _record(
        "isotonic",
        calibration_method="isotonic",
        calibrated_brier=0.05,
        calibrated_ece=0.01,
    )

    assert select_calibration([raw, platt, isotonic]).trial_id == "platt"
    with pytest.raises(ValueError, match="raw, Platt, and isotonic"):
        select_calibration([raw, platt])

    seed_42 = _record("seed-42", random_seed=42, balanced_f1=0.60)
    seed_7 = _record("seed-7", random_seed=7, balanced_f1=0.62)
    seed_2027 = _record("seed-2027", random_seed=2027, balanced_f1=0.64)
    gates = seed_stability_gates([seed_42, seed_7, seed_2027], G6SelectionPolicy())
    assert gates == {
        "balanced_f1_range": True,
        "minimum_family_recall_range": True,
        "validation_binary_logloss_range": True,
    }

    unstable = seed_2027.model_copy(update={"balanced_f1": 0.70})
    assert seed_stability_gates([seed_42, seed_7, unstable], G6SelectionPolicy())[
        "balanced_f1_range"
    ] is False


def test_g6_plan_preflight_binds_g5_c4_and_materializes_search_configs(tmp_path: Path) -> None:
    c4 = tmp_path / "c4.json"
    c4.write_text('{"schema_version":"test"}\n', encoding="utf-8")
    c4_sha = hashlib.sha256(c4.read_bytes()).hexdigest()
    plan_payload = json.loads(PLAN.read_text(encoding="utf-8"))
    plan_payload["c4_mlflow_receipt_sha256"] = c4_sha
    comparison = tmp_path / "g5.json"
    comparison.write_text(
        json.dumps(
            {
                "schema_version": "lightgbm_wave1_g5_repeat_comparison_v1",
                "status": "passed",
                "scope": "governed-cloud-g5",
                "comparisons": {
                    "reproducibility_hash": {
                        "matches": True,
                        "values": [plan_payload["baseline_g5_reproducibility_hash"]] * 3,
                    },
                    "experiment_hash": {
                        "matches": True,
                        "values": [plan_payload["baseline_g5_experiment_hash"]] * 3,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    plan_payload["baseline_g5_comparison_sha256"] = hashlib.sha256(
        comparison.read_bytes()
    ).hexdigest()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan_payload), encoding="utf-8")

    output = tmp_path / "receipt.json"
    experiment_dir = tmp_path / "experiments"
    verify_g6_plan(
        plan_path=plan_path,
        g5_comparison_path=comparison,
        c4_mlflow_evidence_path=c4,
        experiment_dir=experiment_dir,
        output=output,
    )

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "preflight_passed"
    assert len(receipt["search_configs"]) == 4
    assert sorted(path.name for path in experiment_dir.iterdir()) == [
        "ablate-behavior.json",
        "ablate-state.json",
        "hp-regularized.json",
        "hp-slow.json",
    ]


def test_g6_completion_keeps_all_rejections_and_reaches_the_twenty_job_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = load_g6_plan(PLAN)
    selected_experiment = plan.search_trials()[0].experiment
    assert selected_experiment is not None
    confirmation_experiments = {
        trial.trial_id: resolve_confirmation_experiment(selected_experiment, trial)
        for trial in plan.confirmation_trials()
    }
    search_records = [
        _record("g5-baseline", group="baseline", balanced_f1=0.58),
        _record("hp-slow", group="hyperparameter", balanced_f1=0.62),
        _record("hp-regularized", group="hyperparameter", balanced_f1=0.60),
        _record("ablate-behavior", group="feature_ablation", balanced_f1=0.55),
        _record("ablate-state", group="feature_ablation", balanced_f1=0.56),
    ]
    search_receipt = {
        "selected_trial_id": "hp-slow",
        "ranking": [record.model_dump(mode="json") for record in search_records],
    }
    monkeypatch.setattr(
        g6_campaign,
        "derive_confirmation_plan",
        lambda **_: (search_receipt, confirmation_experiments),
    )
    confirmation_records = {
        "seed-7": _record("seed-7", group="seed_stability", random_seed=7, balanced_f1=0.61),
        "seed-2027": _record(
            "seed-2027", group="seed_stability", random_seed=2027, balanced_f1=0.63
        ),
        "calibration-raw": _record(
            "calibration-raw",
            group="calibration",
            calibration_method="raw",
            calibrated_brier=0.08,
            model_sha256="b" * 64,
            validation_predictions_sha256="c" * 64,
        ),
        "calibration-platt": _record(
            "calibration-platt",
            group="calibration",
            calibration_method="platt",
            calibrated_brier=0.04,
            git_commit="b" * 40,
            model_sha256="b" * 64,
            validation_predictions_sha256="c" * 64,
        ),
        "calibration-isotonic": _record(
            "calibration-isotonic",
            group="calibration",
            calibration_method="isotonic",
            calibrated_brier=0.05,
            git_commit="b" * 40,
            model_sha256="b" * 64,
            validation_predictions_sha256="c" * 64,
        ),
    }

    def fake_collect(**kwargs):
        return confirmation_records[kwargs["trial_id"]], kwargs["expected_experiment"]

    monkeypatch.setattr(g6_campaign, "collect_validation_record", fake_collect)
    results = []
    collections = []
    for trial in plan.trials:
        result = tmp_path / trial.trial_id
        result.mkdir()
        experiment = trial.experiment or confirmation_experiments[trial.trial_id]
        request = LightGbmCloudJobRequest(
            campaign_id=plan.campaign_id,
            run_id=trial.run_id,
            mode="development",
            project_id="project-e00g6zvxpr00waz8t3y51k",
            image="ghcr.io/khab40/lob-arena-jobs@sha256:" + "0" * 64,
            created_at=datetime.now(UTC),
            git_commit="0" * 40,
            experiment=experiment,
            random_seed=trial.random_seed,
            input=Wave1FixtureInput(
                feature_release_sha256=APPROVED_FIXTURE_FEATURE_RELEASE_SHA256
            ),
            result_uri=(result / "unused").resolve().as_uri(),
        )
        (result / "request.json").write_bytes(request.canonical_bytes())
        results.append(result)
        collections.append(tmp_path / f"{trial.trial_id}-collection.json")

    report = g6_campaign.complete_g6_campaign(
        plan=plan,
        baseline_result=tmp_path / "baseline",
        baseline_collection=tmp_path / "baseline-collection.json",
        results=list(reversed(results)),
        collections=list(reversed(collections)),
    )

    assert report["status"] == "passed"
    assert report["job_count"] == 9
    assert report["development_jobs_consumed_after_g6"] == 20
    assert report["selected_trial_id"] == "calibration-platt"
    assert report["gates"]["nine_distinct_mlflow_runs"] is True
    assert report["gates"]["mlflow_dataset_lineage_logged"] is True
    assert report["gates"]["no_raw_rows_uploaded_to_mlflow"] is True
    assert report["gates"]["campaign_identity_consistency"] is True
    assert report["control_plane_git_commits"] == ["a" * 40, "b" * 40]
    assert len(report["rejected_trial_ids"]) == 8
    assert report["test_fold_accessed"] is False

    platt = confirmation_records["calibration-platt"]
    confirmation_records["calibration-platt"] = platt.model_copy(
        update={"image": "registry.example/jobs@sha256:" + "b" * 64}
    )
    image_drift = g6_campaign.complete_g6_campaign(
        plan=plan,
        baseline_result=tmp_path / "baseline",
        baseline_collection=tmp_path / "baseline-collection.json",
        results=results,
        collections=collections,
    )
    assert image_drift["gates"]["campaign_identity_consistency"] is False

    confirmation_records["calibration-platt"] = platt.model_copy(
        update={"input_identity_hash": "b" * 64}
    )
    input_drift = g6_campaign.complete_g6_campaign(
        plan=plan,
        baseline_result=tmp_path / "baseline",
        baseline_collection=tmp_path / "baseline-collection.json",
        results=results,
        collections=collections,
    )
    assert input_drift["gates"]["campaign_identity_consistency"] is False


def _record(
    trial_id: str,
    *,
    group: str = "baseline",
    random_seed: int = 42,
    calibration_method: str = "platt",
    balanced_f1: float = 0.60,
    minimum_family_recall: float = 0.70,
    raw_brier: float = 0.10,
    raw_ece: float = 0.10,
    calibrated_brier: float = 0.05,
    calibrated_ece: float = 0.04,
    model_sha256: str | None = None,
    validation_predictions_sha256: str | None = None,
    git_commit: str = "a" * 40,
) -> G6ValidationRecord:
    digest = hashlib.sha256(trial_id.encode("utf-8")).hexdigest()
    return G6ValidationRecord(
        trial_id=trial_id,
        run_id=f"run-{trial_id}",
        group=group,
        experiment_hash=digest,
        random_seed=random_seed,
        calibration_method=calibration_method,
        mlflow_run_id=f"mlflow-{trial_id}",
        mlflow_dataset_input_count=90,
        image="registry.example/jobs@sha256:" + "a" * 64,
        git_commit=git_commit,
        input_identity_hash="a" * 64,
        model_sha256=model_sha256 or digest,
        validation_predictions_sha256=validation_predictions_sha256 or digest,
        candidate_hash=digest,
        reproducibility_hash=digest,
        validation_binary_logloss=0.42,
        balanced_f1=balanced_f1,
        family_recalls={"layering_like": minimum_family_recall},
        minimum_family_recall=minimum_family_recall,
        raw_brier=raw_brier,
        raw_ece=raw_ece,
        calibrated_brier=calibrated_brier,
        calibrated_ece=calibrated_ece,
        test_fold_accessed=False,
        collection_receipt_verified=True,
    )
