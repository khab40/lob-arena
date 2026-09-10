from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import (
    IMMUTABLE_IMAGE_PATTERN,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
)
from app.ml.lightgbm.contracts import (
    IDENTIFIER_PATTERN,
    GIT_COMMIT_PATTERN,
    SHA256_PATTERN,
    CalibrationManifest,
    LightGbmTrainingRun,
)


G6_GROUP_COUNTS = {
    "hyperparameter": 2,
    "feature_ablation": 2,
    "seed_stability": 2,
    "calibration": 3,
}
G6_SEARCH_GROUPS = frozenset({"hyperparameter", "feature_ablation"})
G6_DERIVED_GROUPS = frozenset({"seed_stability", "calibration"})
G6_SEEDS = frozenset({7, 2027})
G6_CALIBRATION_METHODS = frozenset({"raw", "platt", "isotonic"})
G6_ELIGIBILITY = (
    "verified_successful_development_result",
    "test_fold_not_accessed",
    "calibration_not_worse_on_both_brier_and_ece",
)
G6_MODEL_ORDER = (
    "balanced_f1_desc",
    "minimum_family_recall_desc",
    "calibrated_brier_asc",
    "calibrated_ece_asc",
    "validation_binary_logloss_asc",
    "experiment_hash_asc",
)
G6_CALIBRATION_ORDER = (
    "calibrated_brier_asc",
    "calibrated_ece_asc",
    "balanced_f1_desc",
    "calibration_method_asc",
)


class _CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class G6SelectionPolicy(_CanonicalModel):
    schema_version: Literal["lightgbm_wave1_g6_selection_policy_v1"] = (
        "lightgbm_wave1_g6_selection_policy_v1"
    )
    input_scope: Literal["validation_only"] = "validation_only"
    eligibility: tuple[
        Literal[
            "verified_successful_development_result",
            "test_fold_not_accessed",
            "calibration_not_worse_on_both_brier_and_ece",
        ],
        ...,
    ] = (
        "verified_successful_development_result",
        "test_fold_not_accessed",
        "calibration_not_worse_on_both_brier_and_ece",
    )
    model_order: tuple[
        Literal[
            "balanced_f1_desc",
            "minimum_family_recall_desc",
            "calibrated_brier_asc",
            "calibrated_ece_asc",
            "validation_binary_logloss_asc",
            "experiment_hash_asc",
        ],
        ...,
    ] = (
        "balanced_f1_desc",
        "minimum_family_recall_desc",
        "calibrated_brier_asc",
        "calibrated_ece_asc",
        "validation_binary_logloss_asc",
        "experiment_hash_asc",
    )
    calibration_order: tuple[
        Literal[
            "calibrated_brier_asc",
            "calibrated_ece_asc",
            "balanced_f1_desc",
            "calibration_method_asc",
        ],
        ...,
    ] = (
        "calibrated_brier_asc",
        "calibrated_ece_asc",
        "balanced_f1_desc",
        "calibration_method_asc",
    )
    seed_balanced_f1_max_range: float = Field(default=0.05, ge=0, le=1)
    seed_minimum_family_recall_max_range: float = Field(default=0.10, ge=0, le=1)
    seed_validation_logloss_max_range: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def validate_exact_policy(self) -> "G6SelectionPolicy":
        if tuple(self.eligibility) != G6_ELIGIBILITY:
            raise ValueError("G6 eligibility rules must retain their exact declared order")
        if tuple(self.model_order) != G6_MODEL_ORDER:
            raise ValueError("G6 model ordering must retain its exact declared order")
        if tuple(self.calibration_order) != G6_CALIBRATION_ORDER:
            raise ValueError("G6 calibration ordering must retain its exact declared order")
        return self


class G6Trial(_CanonicalModel):
    trial_id: str = Field(pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    group: Literal["hyperparameter", "feature_ablation", "seed_stability", "calibration"]
    phase: Literal["search", "confirmation"]
    mode: Literal["development"] = "development"
    random_seed: int = Field(ge=0)
    experiment: Wave1ExperimentSpec | None = None
    derive_experiment_from: Literal["validation_selected_search_candidate"] | None = None
    calibration_method_override: Literal["raw", "platt", "isotonic"] | None = None

    @model_validator(mode="after")
    def validate_phase_contract(self) -> "G6Trial":
        if self.group in G6_SEARCH_GROUPS:
            if (
                self.phase != "search"
                or self.random_seed != 42
                or self.experiment is None
                or self.derive_experiment_from is not None
                or self.calibration_method_override is not None
            ):
                raise ValueError("G6 search trials require a concrete seed-42 experiment")
        else:
            if (
                self.phase != "confirmation"
                or self.experiment is not None
                or self.derive_experiment_from != "validation_selected_search_candidate"
            ):
                raise ValueError("G6 confirmation trials must derive the selected search experiment")
            if self.group == "seed_stability" and self.calibration_method_override is not None:
                raise ValueError("G6 seed trials preserve the selected calibration method")
            if self.group == "calibration" and self.calibration_method_override is None:
                raise ValueError("G6 calibration trials require a predeclared method")
        return self


class G6CampaignPlan(_CanonicalModel):
    schema_version: Literal["lightgbm_wave1_g6_campaign_plan_v1"] = (
        "lightgbm_wave1_g6_campaign_plan_v1"
    )
    campaign_id: str = Field(pattern=IDENTIFIER_PATTERN)
    baseline_g5_campaign_id: str = Field(pattern=IDENTIFIER_PATTERN)
    baseline_g5_comparison_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_g5_reproducibility_hash: str = Field(pattern=SHA256_PATTERN)
    baseline_g5_experiment_hash: str = Field(pattern=SHA256_PATTERN)
    c4_mlflow_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    development_job_ceiling: Literal[20] = 20
    development_jobs_consumed_before_g6: Literal[11] = 11
    planned_job_count: Literal[9] = 9
    spend_ceiling_usd: Literal[50] = 50
    stop_submission_spend_usd: Literal[40] = 40
    test_input_permitted: Literal[False] = False
    failure_replacement_permitted: Literal[False] = False
    mlflow_required: Literal[True] = True
    mlflow_tracking_uri: Literal["http://10.4.0.54:5500"] = "http://10.4.0.54:5500"
    mlflow_experiment: Literal["lob-arena/lightgbm-development"] = (
        "lob-arena/lightgbm-development"
    )
    raw_rows_uploaded_to_mlflow: Literal[False] = False
    selection_policy: G6SelectionPolicy = Field(default_factory=G6SelectionPolicy)
    trials: tuple[G6Trial, ...] = Field(min_length=9, max_length=9)

    @model_validator(mode="after")
    def validate_fixed_matrix(self) -> "G6CampaignPlan":
        if self.development_jobs_consumed_before_g6 + self.planned_job_count != self.development_job_ceiling:
            raise ValueError("G6 plan must consume exactly the nine remaining development slots")
        if len({trial.trial_id for trial in self.trials}) != len(self.trials):
            raise ValueError("G6 trial IDs must be unique")
        if len({trial.run_id for trial in self.trials}) != len(self.trials):
            raise ValueError("G6 run IDs must be unique")
        counts = Counter(trial.group for trial in self.trials)
        if dict(counts) != G6_GROUP_COUNTS:
            raise ValueError(f"G6 group counts must equal {G6_GROUP_COUNTS}")
        seed_trials = [trial for trial in self.trials if trial.group == "seed_stability"]
        if {trial.random_seed for trial in seed_trials} != G6_SEEDS:
            raise ValueError(f"G6 seed trials must use {sorted(G6_SEEDS)}")
        calibration_trials = [trial for trial in self.trials if trial.group == "calibration"]
        if any(trial.random_seed != 42 for trial in calibration_trials):
            raise ValueError("G6 calibration comparison must use seed 42")
        if {trial.calibration_method_override for trial in calibration_trials} != G6_CALIBRATION_METHODS:
            raise ValueError("G6 calibration comparison must contain raw, Platt, and isotonic")
        search = [trial for trial in self.trials if trial.group in G6_SEARCH_GROUPS]
        experiment_hashes = {trial.experiment.canonical_hash() for trial in search if trial.experiment}
        if len(experiment_hashes) != 4:
            raise ValueError("G6 search experiments must be four distinct configurations")
        return self

    def search_trials(self) -> tuple[G6Trial, ...]:
        return tuple(trial for trial in self.trials if trial.group in G6_SEARCH_GROUPS)

    def confirmation_trials(self) -> tuple[G6Trial, ...]:
        return tuple(trial for trial in self.trials if trial.group in G6_DERIVED_GROUPS)


class G6ValidationRecord(_CanonicalModel):
    trial_id: str = Field(pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    group: Literal["baseline", "hyperparameter", "feature_ablation", "seed_stability", "calibration"]
    experiment_hash: str = Field(pattern=SHA256_PATTERN)
    random_seed: int = Field(ge=0)
    calibration_method: Literal["raw", "platt", "isotonic"]
    mlflow_run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    mlflow_dataset_input_count: int = Field(ge=1)
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    input_identity_hash: str = Field(pattern=SHA256_PATTERN)
    model_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_predictions_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_hash: str = Field(pattern=SHA256_PATTERN)
    reproducibility_hash: str = Field(pattern=SHA256_PATTERN)
    validation_binary_logloss: float = Field(ge=0, allow_inf_nan=False)
    balanced_f1: float = Field(ge=0, le=1, allow_inf_nan=False)
    family_recalls: dict[str, float] = Field(min_length=1)
    minimum_family_recall: float = Field(ge=0, le=1, allow_inf_nan=False)
    raw_brier: float = Field(ge=0, allow_inf_nan=False)
    raw_ece: float = Field(ge=0, allow_inf_nan=False)
    calibrated_brier: float = Field(ge=0, allow_inf_nan=False)
    calibrated_ece: float = Field(ge=0, allow_inf_nan=False)
    test_fold_accessed: Literal[False] = False
    collection_receipt_verified: Literal[True] = True

    @model_validator(mode="after")
    def validate_family_recalls(self) -> "G6ValidationRecord":
        if any(not family or not 0 <= recall <= 1 for family, recall in self.family_recalls.items()):
            raise ValueError("G6 family recalls must be named probabilities")
        if self.minimum_family_recall != min(self.family_recalls.values()):
            raise ValueError("G6 minimum family recall does not match the observed families")
        return self

    @property
    def calibration_eligible(self) -> bool:
        return not (
            self.calibrated_brier > self.raw_brier
            and self.calibrated_ece > self.raw_ece
        )


def load_g6_plan(path: Path) -> G6CampaignPlan:
    return G6CampaignPlan.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_confirmation_experiment(
    selected: Wave1ExperimentSpec,
    trial: G6Trial,
) -> Wave1ExperimentSpec:
    if trial.group not in G6_DERIVED_GROUPS:
        raise ValueError("only G6 confirmation trials derive an experiment")
    method = trial.calibration_method_override or selected.calibration_method
    return selected.model_copy(update={"calibration_method": method})


def collect_validation_record(
    *,
    result: Path,
    collection: Path,
    trial_id: str,
    group: Literal["baseline", "hyperparameter", "feature_ablation", "seed_stability", "calibration"],
    expected_campaign_id: str,
    expected_run_id: str | None = None,
    expected_experiment: Wave1ExperimentSpec | None = None,
    expected_seed: int | None = None,
    expected_c4_receipt_sha256: str | None = None,
) -> tuple[G6ValidationRecord, Wave1ExperimentSpec]:
    # The model stack is optional for plan-only governance checks. Import it only
    # when a completed cloud result is actually being verified.
    from app.ml.lightgbm.cloud_runner import FrozenCandidate, verify_wave1_result
    from app.ml.lightgbm.reproducibility import _verified_collection_receipt

    run = verify_wave1_result(result)
    request = LightGbmCloudJobRequest.model_validate_json((result / "request.json").read_text(encoding="utf-8"))
    if run.status != "succeeded" or request.mode != "development":
        raise ValueError("G6 accepts only successful development results")
    if request.campaign_id != expected_campaign_id:
        raise ValueError("G6 result belongs to another campaign")
    if expected_run_id is not None and request.run_id != expected_run_id:
        raise ValueError("G6 result run ID does not match the plan")
    if expected_experiment is not None and request.experiment.canonical_hash() != expected_experiment.canonical_hash():
        raise ValueError("G6 result experiment does not match the plan")
    if expected_seed is not None and request.random_seed != expected_seed:
        raise ValueError("G6 result seed does not match the plan")
    if expected_c4_receipt_sha256 is not None and not (
        request.input.kind == "tabular-projection"
        and request.input.dataset_lineage_receipt.sha256 == expected_c4_receipt_sha256
    ):
        raise ValueError("G6 result is not bound to the planned C4 MLflow receipt")
    metrics = json.loads((result / "metrics.json").read_text(encoding="utf-8"))
    if metrics.get("test_fold_accessed") is not False:
        raise ValueError("G6 result does not prove test-fold isolation")
    artifact_root = result / "artifacts"
    candidate = FrozenCandidate.model_validate_json((result / "candidate.json").read_text(encoding="utf-8"))
    training_path = _verified_artifact(artifact_root, candidate.training_manifest.uri, candidate.training_manifest.sha256)
    calibration_path = _verified_artifact(
        artifact_root,
        candidate.calibration_manifest.uri,
        candidate.calibration_manifest.sha256,
    )
    validation_path = _verified_artifact(
        artifact_root,
        candidate.validation_metrics.uri,
        candidate.validation_metrics.sha256,
    )
    training = LightGbmTrainingRun.model_validate_json(training_path.read_text(encoding="utf-8"))
    calibration = CalibrationManifest.model_validate_json(calibration_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if training.data_policy.test_fold_accessed or calibration.test_fold_accessed:
        raise ValueError("G6 governed manifests show test-fold access")
    if run.mlflow_run_id is None or request.mlflow_tracking_uri != "http://10.4.0.54:5500":
        raise ValueError("G6 requires a run in the approved private MLflow tracker")
    if not (
        validation.get("schema_version") == "lightgbm_validation_metrics_v1"
        and validation.get("calibration_id") == calibration.calibration_id
        and validation.get("binding") == training.binding.model_dump(mode="json")
        and validation.get("row_count") == calibration.row_count
        and validation.get("raw_metrics") == calibration.raw_metrics.model_dump(mode="json")
        and validation.get("calibrated_metrics")
        == calibration.calibrated_metrics.model_dump(mode="json")
        and validation.get("operating_points")
        == [point.model_dump(mode="json") for point in calibration.operating_points]
    ):
        raise ValueError("G6 validation metrics do not match the governed calibration manifest")
    receipt = _verified_collection_receipt(collection, result, request, run.mlflow_run_id)
    if not receipt:
        raise ValueError("G6 requires a verified collection receipt")
    balanced = next(
        point for point in validation["operating_points"] if point["mode"] == "balanced"
    )
    prediction_path = _verified_artifact(
        artifact_root,
        calibration.input_predictions.uri,
        calibration.input_predictions.sha256,
    )
    family_recalls = _all_family_recalls(prediction_path, calibration)
    record = G6ValidationRecord(
        trial_id=trial_id,
        run_id=request.run_id,
        group=group,
        experiment_hash=request.experiment.canonical_hash(),
        random_seed=request.random_seed,
        calibration_method=calibration.parameters.method,
        mlflow_run_id=run.mlflow_run_id,
        mlflow_dataset_input_count=len(training.input_features),
        image=request.image,
        git_commit=request.git_commit,
        input_identity_hash=request.input.canonical_hash(),
        model_sha256=training.model_artifact.sha256,
        validation_predictions_sha256=calibration.input_predictions.sha256,
        candidate_hash=run.candidate_hash,
        reproducibility_hash=run.reproducibility_hash,
        validation_binary_logloss=training.early_stopping.best_score,
        balanced_f1=balanced["validation_metrics"]["f1"],
        family_recalls=family_recalls,
        minimum_family_recall=min(family_recalls.values()),
        raw_brier=calibration.raw_metrics.brier_score,
        raw_ece=calibration.raw_metrics.expected_calibration_error,
        calibrated_brier=calibration.calibrated_metrics.brier_score,
        calibrated_ece=calibration.calibrated_metrics.expected_calibration_error,
        test_fold_accessed=False,
        collection_receipt_verified=True,
    )
    return record, request.experiment


def select_model(records: list[G6ValidationRecord]) -> G6ValidationRecord:
    eligible = [record for record in records if record.calibration_eligible]
    if not eligible:
        raise ValueError("G6 has no model candidate passing the calibration eligibility rule")
    return min(
        eligible,
        key=lambda record: (
            -record.balanced_f1,
            -record.minimum_family_recall,
            record.calibrated_brier,
            record.calibrated_ece,
            record.validation_binary_logloss,
            record.experiment_hash,
        ),
    )


def select_calibration(records: list[G6ValidationRecord]) -> G6ValidationRecord:
    if {record.calibration_method for record in records} != G6_CALIBRATION_METHODS:
        raise ValueError("G6 calibration selection requires raw, Platt, and isotonic results")
    eligible = [record for record in records if record.calibration_eligible]
    if not eligible:
        raise ValueError("G6 has no calibration candidate passing the eligibility rule")
    return min(
        eligible,
        key=lambda record: (
            record.calibrated_brier,
            record.calibrated_ece,
            -record.balanced_f1,
            record.calibration_method,
        ),
    )


def seed_stability_gates(
    records: list[G6ValidationRecord],
    policy: G6SelectionPolicy,
) -> dict[str, bool]:
    if len(records) != 3 or len({record.random_seed for record in records}) != 3:
        raise ValueError("G6 seed stability requires the selected seed-42 result and two distinct repeats")
    return {
        "balanced_f1_range": _range(record.balanced_f1 for record in records)
        <= policy.seed_balanced_f1_max_range,
        "minimum_family_recall_range": _range(
            record.minimum_family_recall for record in records
        )
        <= policy.seed_minimum_family_recall_max_range,
        "validation_binary_logloss_range": _range(record.validation_binary_logloss for record in records)
        <= policy.seed_validation_logloss_max_range,
    }


def _range(values) -> float:
    collected = list(values)
    return max(collected) - min(collected)


def _verified_artifact(root: Path, uri: str, expected_sha256: str) -> Path:
    path = (root.resolve() / uri).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError("G6 candidate artifact is missing or escaped its result root")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("G6 candidate artifact checksum mismatch")
    return path


def _all_family_recalls(
    prediction_path: Path,
    calibration: CalibrationManifest,
) -> dict[str, float]:
    import numpy as np
    import pyarrow.parquet as pq

    from app.ml.lightgbm.scoring import apply_calibration

    table = pq.read_table(
        prediction_path,
        columns=["label", "attack_family", "raw_probability"],
    )
    labels = np.asarray(table.column("label").to_numpy(zero_copy_only=False), dtype=np.int8)
    families = np.asarray(table.column("attack_family").to_pylist(), dtype=object)
    raw = np.asarray(
        table.column("raw_probability").to_numpy(zero_copy_only=False),
        dtype=np.float64,
    )
    probabilities = apply_calibration(calibration.parameters, raw)
    threshold = next(
        point.threshold for point in calibration.operating_points if point.mode == "balanced"
    )
    observed = sorted(
        {
            family
            for family, label in zip(families, labels, strict=True)
            if label == 1 and isinstance(family, str) and family
        }
    )
    if not observed:
        raise ValueError("G6 validation predictions contain no named positive attack families")
    return {
        family: float(np.mean(probabilities[(labels == 1) & (families == family)] >= threshold))
        for family in observed
    }


def plan_receipt(plan: G6CampaignPlan) -> dict[str, object]:
    return {
        "schema_version": "lightgbm_wave1_g6_plan_receipt_v1",
        "status": "preflight_passed",
        "campaign_id": plan.campaign_id,
        "plan_sha256": plan.canonical_hash(),
        "development_jobs_consumed_before_g6": plan.development_jobs_consumed_before_g6,
        "planned_job_count": plan.planned_job_count,
        "development_job_ceiling": plan.development_job_ceiling,
        "group_counts": G6_GROUP_COUNTS,
        "test_input_permitted": plan.test_input_permitted,
        "failure_replacement_permitted": plan.failure_replacement_permitted,
        "mlflow_required": plan.mlflow_required,
        "mlflow_tracking_uri": plan.mlflow_tracking_uri,
        "mlflow_experiment": plan.mlflow_experiment,
        "raw_rows_uploaded_to_mlflow": plan.raw_rows_uploaded_to_mlflow,
        "search_run_ids": [trial.run_id for trial in plan.search_trials()],
        "confirmation_run_ids": [trial.run_id for trial in plan.confirmation_trials()],
    }


def verify_g6_plan(
    *,
    plan_path: Path,
    g5_comparison_path: Path,
    c4_mlflow_evidence_path: Path,
    experiment_dir: Path,
    output: Path,
) -> None:
    plan = load_g6_plan(plan_path)
    if sha256_file(c4_mlflow_evidence_path) != plan.c4_mlflow_receipt_sha256:
        raise ValueError("G6 plan does not match the governed C4 MLflow receipt")
    g5 = json.loads(g5_comparison_path.read_text(encoding="utf-8"))
    if sha256_file(g5_comparison_path) != plan.baseline_g5_comparison_sha256:
        raise ValueError("G6 plan does not match the formal G5 comparison receipt")
    comparisons = g5.get("comparisons", {})
    reproducibility = comparisons.get("reproducibility_hash", {})
    experiment = comparisons.get("experiment_hash", {})
    if not (
        g5.get("schema_version") == "lightgbm_wave1_g5_repeat_comparison_v1"
        and g5.get("status") == "passed"
        and g5.get("scope") == "governed-cloud-g5"
        and reproducibility.get("matches") is True
        and set(reproducibility.get("values", []))
        == {plan.baseline_g5_reproducibility_hash}
        and experiment.get("matches") is True
        and set(experiment.get("values", [])) == {plan.baseline_g5_experiment_hash}
    ):
        raise ValueError("G6 plan requires the formally passed governed G5 comparison")
    if experiment_dir.exists():
        raise FileExistsError(f"G6 experiment directory already exists: {experiment_dir}")
    experiment_dir.mkdir(parents=True)
    search_configs = []
    for trial in plan.search_trials():
        assert trial.experiment is not None
        path = experiment_dir / f"{trial.trial_id}.json"
        path.write_bytes(trial.experiment.canonical_bytes())
        search_configs.append(
            {
                "trial_id": trial.trial_id,
                "run_id": trial.run_id,
                "random_seed": trial.random_seed,
                "experiment_path": path.name,
                "experiment_sha256": sha256_file(path),
                "experiment_hash": trial.experiment.canonical_hash(),
            }
        )
    receipt = plan_receipt(plan)
    receipt.update(
        {
            "plan_file_sha256": sha256_file(plan_path),
            "g5_comparison_sha256": sha256_file(g5_comparison_path),
            "c4_mlflow_receipt_sha256": sha256_file(c4_mlflow_evidence_path),
            "search_configs": search_configs,
        }
    )
    if output.exists():
        raise FileExistsError(f"G6 plan receipt already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def derive_confirmation_plan(
    *,
    plan: G6CampaignPlan,
    baseline_result: Path,
    baseline_collection: Path,
    search_results: list[Path],
    search_collections: list[Path],
) -> tuple[dict[str, object], dict[str, Wave1ExperimentSpec]]:
    if len(search_results) != 4 or len(search_collections) != 4:
        raise ValueError("G6 search selection requires four results and four collection receipts")
    baseline_record, baseline_experiment = collect_validation_record(
        result=baseline_result,
        collection=baseline_collection,
        trial_id="g5-baseline",
        group="baseline",
        expected_campaign_id=plan.baseline_g5_campaign_id,
        expected_c4_receipt_sha256=plan.c4_mlflow_receipt_sha256,
    )
    if (
        baseline_record.reproducibility_hash != plan.baseline_g5_reproducibility_hash
        or baseline_record.experiment_hash != plan.baseline_g5_experiment_hash
    ):
        raise ValueError("G6 baseline does not match the formally closed G5 identity")
    records = [baseline_record]
    experiments = {baseline_record.trial_id: baseline_experiment}
    for trial, result, collection in zip(
        plan.search_trials(), search_results, search_collections, strict=True
    ):
        assert trial.experiment is not None
        record, experiment = collect_validation_record(
            result=result,
            collection=collection,
            trial_id=trial.trial_id,
            group=trial.group,
            expected_campaign_id=plan.campaign_id,
            expected_run_id=trial.run_id,
            expected_experiment=trial.experiment,
            expected_seed=trial.random_seed,
            expected_c4_receipt_sha256=plan.c4_mlflow_receipt_sha256,
        )
        records.append(record)
        experiments[trial.trial_id] = experiment
    selected = select_model(records)
    selected_experiment = experiments[selected.trial_id]
    confirmation = {
        trial.trial_id: resolve_confirmation_experiment(selected_experiment, trial)
        for trial in plan.confirmation_trials()
    }
    ranking = sorted(
        records,
        key=lambda record: (
            not record.calibration_eligible,
            -record.balanced_f1,
            -record.minimum_family_recall,
            record.calibrated_brier,
            record.calibrated_ece,
            record.validation_binary_logloss,
            record.experiment_hash,
        ),
    )
    receipt = {
        "schema_version": "lightgbm_wave1_g6_search_selection_v1",
        "status": "passed",
        "scope": "validation_only",
        "campaign_id": plan.campaign_id,
        "plan_sha256": plan.canonical_hash(),
        "selected_trial_id": selected.trial_id,
        "selected_experiment_hash": selected.experiment_hash,
        "selected_source_candidate_hash": selected.candidate_hash,
        "selection_policy_sha256": plan.selection_policy.canonical_hash(),
        "ranking": [record.model_dump(mode="json") for record in ranking],
        "rejected_trial_ids": [
            record.trial_id for record in ranking if record.trial_id != selected.trial_id
        ],
        "confirmation_trials": [
            {
                "trial_id": trial.trial_id,
                "run_id": trial.run_id,
                "group": trial.group,
                "random_seed": trial.random_seed,
                "experiment_hash": confirmation[trial.trial_id].canonical_hash(),
                "calibration_method": confirmation[trial.trial_id].calibration_method,
            }
            for trial in plan.confirmation_trials()
        ],
        "test_fold_accessed": False,
    }
    return receipt, confirmation


def write_confirmation_plan(
    *,
    output_dir: Path,
    receipt: dict[str, object],
    experiments: dict[str, Wave1ExperimentSpec],
) -> None:
    if output_dir.exists():
        raise FileExistsError(f"G6 confirmation output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    for trial_id, experiment in experiments.items():
        (output_dir / f"{trial_id}.json").write_bytes(experiment.canonical_bytes())
    (output_dir / "search-selection.json").write_text(
        json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def complete_g6_campaign(
    *,
    plan: G6CampaignPlan,
    baseline_result: Path,
    baseline_collection: Path,
    results: list[Path],
    collections: list[Path],
) -> dict[str, object]:
    if len(results) != 9 or len(collections) != 9:
        raise ValueError("G6 completion requires exactly nine results and nine collection receipts")
    pairs: dict[str, tuple[Path, Path]] = {}
    for result, collection in zip(results, collections, strict=True):
        request = LightGbmCloudJobRequest.model_validate_json(
            (result / "request.json").read_text(encoding="utf-8")
        )
        if request.run_id in pairs:
            raise ValueError("G6 completion received a duplicate run ID")
        pairs[request.run_id] = (result, collection)
    expected_run_ids = {trial.run_id for trial in plan.trials}
    if set(pairs) != expected_run_ids:
        raise ValueError("G6 completion results do not match the exact nine planned run IDs")

    search_results = [pairs[trial.run_id][0] for trial in plan.search_trials()]
    search_collections = [pairs[trial.run_id][1] for trial in plan.search_trials()]
    search_receipt, confirmation_experiments = derive_confirmation_plan(
        plan=plan,
        baseline_result=baseline_result,
        baseline_collection=baseline_collection,
        search_results=search_results,
        search_collections=search_collections,
    )
    search_records = [
        G6ValidationRecord.model_validate(item) for item in search_receipt["ranking"]
    ]
    selected_search = next(
        record
        for record in search_records
        if record.trial_id == search_receipt["selected_trial_id"]
    )
    confirmation_records: list[G6ValidationRecord] = []
    for trial in plan.confirmation_trials():
        result, collection = pairs[trial.run_id]
        record, _ = collect_validation_record(
            result=result,
            collection=collection,
            trial_id=trial.trial_id,
            group=trial.group,
            expected_campaign_id=plan.campaign_id,
            expected_run_id=trial.run_id,
            expected_experiment=confirmation_experiments[trial.trial_id],
            expected_seed=trial.random_seed,
            expected_c4_receipt_sha256=plan.c4_mlflow_receipt_sha256,
        )
        confirmation_records.append(record)
    seed_records = [record for record in confirmation_records if record.group == "seed_stability"]
    seed_gates = seed_stability_gates(
        [selected_search, *seed_records],
        plan.selection_policy,
    )
    calibration_records = [record for record in confirmation_records if record.group == "calibration"]
    selected_calibration = select_calibration(calibration_records)
    campaign_records = [
        record
        for record in [*search_records, *confirmation_records]
        if record.group != "baseline"
    ]
    calibration_model_consistency = (
        len({record.model_sha256 for record in calibration_records}) == 1
        and len({record.validation_predictions_sha256 for record in calibration_records}) == 1
    )
    control_plane_git_commits = sorted({record.git_commit for record in campaign_records})
    # The immutable image is the runtime code identity. The local control-plane
    # commit may advance for receipt-only fixes while the governed image, inputs,
    # and predeclared experiment specifications remain unchanged.
    campaign_identity_consistency = (
        len({record.input_identity_hash for record in campaign_records}) == 1
        and len({record.image for record in campaign_records}) == 1
    )
    gates = {
        "exactly_nine_planned_results": True,
        "verified_collection_receipts": all(
            record.collection_receipt_verified for record in campaign_records
        ),
        "nine_distinct_mlflow_runs": (
            len({record.mlflow_run_id for record in campaign_records}) == len(campaign_records)
        ),
        "mlflow_dataset_lineage_logged": all(
            record.mlflow_dataset_input_count > 0 for record in campaign_records
        ),
        "no_raw_rows_uploaded_to_mlflow": plan.raw_rows_uploaded_to_mlflow is False,
        "development_validation_only": all(
            record.test_fold_accessed is False for record in campaign_records
        ),
        "campaign_identity_consistency": campaign_identity_consistency,
        "seed_balanced_f1_stable": seed_gates["balanced_f1_range"],
        "seed_minimum_family_recall_stable": seed_gates["minimum_family_recall_range"],
        "seed_validation_logloss_stable": seed_gates["validation_binary_logloss_range"],
        "calibration_model_consistency": calibration_model_consistency,
        "selected_calibration_eligible": selected_calibration.calibration_eligible,
    }
    passed = all(gates.values())
    calibration_ranking = sorted(
        calibration_records,
        key=lambda record: (
            not record.calibration_eligible,
            record.calibrated_brier,
            record.calibrated_ece,
            -record.balanced_f1,
            record.calibration_method,
        ),
    )
    return {
        "schema_version": "lightgbm_wave1_g6_campaign_comparison_v1",
        "status": "passed" if passed else "failed",
        "disposition": "g6_candidate_selected" if passed else "g6_campaign_blocked",
        "scope": "governed_cloud_validation_only",
        "campaign_id": plan.campaign_id,
        "plan_sha256": plan.canonical_hash(),
        "selection_policy_sha256": plan.selection_policy.canonical_hash(),
        "job_count": len(campaign_records),
        "development_jobs_consumed_after_g6": (
            plan.development_jobs_consumed_before_g6 + len(campaign_records)
        ),
        "control_plane_git_commits": control_plane_git_commits,
        "gates": gates,
        "search_selection": search_receipt,
        "seed_stability": {
            "gates": seed_gates,
            "records": [record.model_dump(mode="json") for record in [selected_search, *seed_records]],
        },
        "calibration_ranking": [record.model_dump(mode="json") for record in calibration_ranking],
        "selected_trial_id": selected_calibration.trial_id if passed else None,
        "selected_candidate_hash": selected_calibration.candidate_hash if passed else None,
        "selected_reproducibility_hash": (
            selected_calibration.reproducibility_hash if passed else None
        ),
        "rejected_trial_ids": [
            record.trial_id
            for record in [*search_records, *confirmation_records]
            if record.trial_id
            not in {search_receipt["selected_trial_id"], selected_calibration.trial_id}
        ],
        "test_fold_accessed": False,
    }
