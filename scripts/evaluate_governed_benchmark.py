import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.governance import (  # noqa: E402
    CorpusValidationReport,
    GovernedCorpusManifest,
    load_adjudications,
    validate_adjudications,
)
from app.corpus.models import load_benchmark_protocol  # noqa: E402
from app.corpus.splits import load_split_manifest, validate_split_manifest  # noqa: E402
from app.evaluation.canonical_bundle import (  # noqa: E402
    CanonicalJavaReplayManifest,
    bind_replay_manifest_to_corpus_session,
)
from app.evaluation.governed_metrics import (  # noqa: E402
    SessionMetricComponents,
    aggregate_governed_metrics,
    combine_session_components,
    evaluate_governed_session,
    governed_unit_from_canonical_bundle,
)
from app.evaluation.regimes import (  # noqa: E402
    GovernedRegimeEvidence,
    assign_regimes,
    regime_metric_matrix,
    worst_decile_results,
)
from app.evaluation.release import write_governed_benchmark_release  # noqa: E402
from app.evaluation.results import GovernedBenchmarkResults  # noqa: E402
from app.evaluation.statistics import (  # noqa: E402
    bootstrap_metric_matrix,
    paired_session_comparison,
)
from app.features.streaming import StreamingValidationEvidence  # noqa: E402


class SessionEvaluationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_session_id: str = Field(min_length=1)
    replay_manifests: list[str] = Field(min_length=1)
    artifact_root: str | None = None

    @model_validator(mode="after")
    def validate_unique_replays(self) -> "SessionEvaluationPlan":
        if len(self.replay_manifests) != len(set(self.replay_manifests)):
            raise ValueError("session replay manifests must be unique")
        return self


class GovernedEvaluationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["governed_evaluation_plan_v1"] = "governed_evaluation_plan_v1"
    model_id: str = Field(min_length=1)
    fold: Literal["train", "validation", "test"]
    adjudications: str
    regime_evidence: str
    baseline_session_metrics: str
    streaming_evidence: list[str] = Field(min_length=1)
    sessions: list[SessionEvaluationPlan] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_sessions(self) -> "GovernedEvaluationPlan":
        session_ids = [item.base_session_id for item in self.sessions]
        if len(session_ids) != len(set(session_ids)):
            raise ValueError("evaluation plan base sessions must be unique")
        if len(self.streaming_evidence) != len(set(self.streaming_evidence)):
            raise ValueError("streaming evidence paths must be unique")
        return self


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate canonical Java replays under a frozen governed corpus protocol."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--corpus-validation", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs" / "benchmark" / "governed-benchmark-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path)
    parser.add_argument("--adjudication-artifact-root", type=Path)
    parser.add_argument("--signer", default="Market Surveillance QA")
    parser.add_argument("--allow-unsigned", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    protocol = load_benchmark_protocol(args.protocol)
    corpus = GovernedCorpusManifest.model_validate_json(args.corpus.read_text(encoding="utf-8"))
    split = load_split_manifest(args.split)
    plan = GovernedEvaluationPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    corpus_validation = CorpusValidationReport.model_validate_json(
        args.corpus_validation.read_text(encoding="utf-8")
    )
    if (
        corpus_validation.verdict != "pass"
        or corpus_validation.corpus_id != corpus.corpus_id
        or corpus_validation.corpus_hash != corpus.corpus_hash()
        or corpus_validation.protocol_hash != protocol.protocol_hash()
        or corpus_validation.artifact_verification_mode != "local"
    ):
        raise ValueError("governed corpus lacks a bound passing local artifact validation")
    validate_split_manifest(split, corpus=corpus, protocol=protocol)
    if protocol.require_signed_release_manifest and args.signing_key is None and not args.allow_unsigned:
        raise ValueError("the governed protocol requires --signing-key for a releasable benchmark")

    plan_root = args.plan.parent.resolve()
    adjudications_path = _resolve(plan_root, plan.adjudications)
    adjudications = load_adjudications(adjudications_path)
    validate_adjudications(
        adjudications,
        manifest=corpus,
        protocol=protocol,
        artifact_root=args.adjudication_artifact_root or plan_root,
    )
    adjudications_by_session: dict[str, list] = defaultdict(list)
    for window in adjudications:
        adjudications_by_session[window.base_session_id].append(window)

    expected_session_ids = {
        item.base_session_id
        for item in split.assignments
        if item.fold == plan.fold
    }
    planned_session_ids = {item.base_session_id for item in plan.sessions}
    if planned_session_ids != expected_session_ids:
        raise ValueError("evaluation plan must cover every and only session in the selected frozen fold")
    regime_path = _resolve(plan_root, plan.regime_evidence)
    regime_evidence = GovernedRegimeEvidence.model_validate_json(
        regime_path.read_text(encoding="utf-8")
    )
    if (
        regime_evidence.protocol_hash != protocol.protocol_hash()
        or regime_evidence.corpus_hash != corpus.corpus_hash()
        or regime_evidence.assignment_hash != split.assignment_hash
    ):
        raise ValueError("regime evidence is not bound to this protocol, corpus, and split")
    train_session_ids = {
        item.base_session_id
        for item in split.assignments
        if item.fold == "train"
    }
    if not set(regime_evidence.fit_session_ids) <= train_session_ids:
        raise ValueError("regime evidence contains non-training fit sessions")
    if set(regime_evidence.target_features) != expected_session_ids:
        raise ValueError("regime evidence must cover every selected-fold base session")
    regimes_by_session = {
        session_id: assign_regimes(features, regime_evidence.thresholds)
        for session_id, features in regime_evidence.target_features.items()
    }
    streaming_evidence = [
        StreamingValidationEvidence.model_validate_json(
            _resolve(plan_root, value).read_text(encoding="utf-8")
        )
        for value in plan.streaming_evidence
    ]
    streaming_by_session = {
        item.base_session_id: item
        for item in streaming_evidence
    }
    if (
        {item.base_session_id for item in streaming_evidence} != expected_session_ids
        or len(streaming_evidence) != len(expected_session_ids)
        or any(
            item.protocol_hash != protocol.protocol_hash()
            or item.corpus_hash != corpus.corpus_hash()
            or item.memory_growth_fraction > protocol.streaming.max_memory_growth_fraction
            for item in streaming_evidence
        )
    ):
        raise ValueError("streaming evidence does not satisfy the governed full-session gate")
    baseline_path = _resolve(plan_root, plan.baseline_session_metrics)
    baseline_metrics = _load_session_metrics(baseline_path)
    if {item.base_session_id for item in baseline_metrics} != expected_session_ids:
        raise ValueError("paired baseline metrics must cover every selected-fold base session")
    corpus_sessions = {session.base_session_id: session for session in corpus.sessions}
    session_metrics: list[SessionMetricComponents] = []
    input_artifacts: list[dict[str, object]] = []
    input_artifacts.extend(
        [
            {
                "kind": "benchmark_protocol",
                "manifest": str(args.protocol),
                "manifest_sha256": _sha256(args.protocol),
            },
            {
                "kind": "governed_corpus",
                "manifest": str(args.corpus),
                "manifest_sha256": _sha256(args.corpus),
            },
            {
                "kind": "corpus_validation",
                "manifest": str(args.corpus_validation),
                "manifest_sha256": _sha256(args.corpus_validation),
            },
            {
                "kind": "split_manifest",
                "manifest": str(args.split),
                "manifest_sha256": _sha256(args.split),
            },
            {
                "kind": "evaluation_plan",
                "manifest": str(args.plan),
                "manifest_sha256": _sha256(args.plan),
            },
            {
                "kind": "clean_adjudications",
                "manifest": str(adjudications_path),
                "manifest_sha256": _sha256(adjudications_path),
            },
            {
                "kind": "regime_evidence",
                "manifest": str(regime_path),
                "manifest_sha256": _sha256(regime_path),
            },
            {
                "kind": "paired_baseline_session_metrics",
                "manifest": str(baseline_path),
                "manifest_sha256": _sha256(baseline_path),
            },
        ]
    )
    input_artifacts.extend(
        {
            "kind": "streaming_validation",
            "base_session_id": item.base_session_id,
            "manifest": str(_resolve(plan_root, path)),
            "manifest_sha256": _sha256(_resolve(plan_root, path)),
        }
        for path, item in zip(plan.streaming_evidence, streaming_evidence, strict=True)
    )
    for session_plan in sorted(plan.sessions, key=lambda item: item.base_session_id):
        corpus_session = corpus_sessions[session_plan.base_session_id]
        replay_components: list[SessionMetricComponents] = []
        observed_replays: set[tuple[str, str | None]] = set()
        for replay_name in session_plan.replay_manifests:
            replay_path = _resolve(plan_root, replay_name)
            artifact_root = (
                _resolve(plan_root, session_plan.artifact_root)
                if session_plan.artifact_root is not None
                else replay_path.parent
            )
            replay_manifest = CanonicalJavaReplayManifest.model_validate_json(
                replay_path.read_text(encoding="utf-8")
            )
            bind_replay_manifest_to_corpus_session(replay_manifest, corpus_session)
            if replay_manifest.mode == "historical_control":
                stream_evidence = streaming_by_session[session_plan.base_session_id]
                if (
                    stream_evidence.control_replay_manifest_sha256 != _sha256(replay_path)
                    or stream_evidence.canonical_event_stream_hash
                    != replay_manifest.canonical_event_stream_hash
                    or stream_evidence.canonical_event_count != replay_manifest.event_count
                ):
                    raise ValueError(
                        "streaming evidence is not bound to the evaluated control replay"
                    )
            replay_identity = (replay_manifest.mode, replay_manifest.campaign_id)
            if replay_identity in observed_replays:
                raise ValueError("evaluation plan contains a duplicate replay identity")
            observed_replays.add(replay_identity)
            session_adjudications = adjudications_by_session[session_plan.base_session_id]
            if replay_manifest.mode == "historical_control":
                clean_windows = [
                    window
                    for window in session_adjudications
                    if window.status == "verified_clean"
                    and window.transferred_from_control_window_id is None
                ]
            else:
                clean_windows = [
                    window
                    for window in session_adjudications
                    if window.status == "verified_clean"
                    and window.transferred_from_control_window_id is not None
                ]
            unit = governed_unit_from_canonical_bundle(
                replay_path,
                verified_clean_windows=clean_windows,
                artifact_root=artifact_root,
                regimes=regimes_by_session[session_plan.base_session_id],
            )
            replay_components.append(
                evaluate_governed_session(
                    unit,
                    alert_deduplication_window_ns=protocol.metrics.alert_deduplication_window_ns,
                    alert_matching_horizon_ns=protocol.splits.purge_alert_horizon_ns,
                )
            )
            input_artifacts.append(
                {
                    "kind": "canonical_java_replay",
                    "base_session_id": session_plan.base_session_id,
                    "run_id": replay_manifest.run_id,
                    "mode": replay_manifest.mode,
                    "campaign_id": replay_manifest.campaign_id,
                    "manifest": str(replay_path),
                    "manifest_sha256": _sha256(replay_path),
                    "java_canonical_event_stream_hash": replay_manifest.canonical_event_stream_hash,
                }
            )
        expected_replays = {
            ("historical_control", None),
            *[
                ("hybrid", campaign.campaign_id)
                for campaign in corpus_session.campaigns
            ],
        }
        if observed_replays != expected_replays:
            raise ValueError("evaluation plan must include one control and every registered hybrid campaign")
        session_metrics.append(
            combine_session_components(
                replay_components,
                base_session_id=session_plan.base_session_id,
                instrument=corpus_session.instrument,
                regimes=regimes_by_session[session_plan.base_session_id],
            )
        )
    if (
        protocol.metrics.require_realized_benefit_event
        and sum(item.true_positive + item.false_negative for item in session_metrics)
        != sum(item.benefit_eligible_attack_count for item in session_metrics)
    ):
        raise ValueError("every governed attack requires a realized-benefit event")

    metrics = aggregate_governed_metrics(session_metrics)
    interval_metrics = [
        "precision",
        "attack_level_recall",
        "f1",
        "false_alerts_per_million_events",
        "detection_before_benefit_rate",
        "duplicate_alert_load",
    ]
    confidence_intervals = bootstrap_metric_matrix(
        session_metrics,
        metrics=interval_metrics,
        resamples=protocol.bootstrap.resamples,
        confidence_level=protocol.bootstrap.confidence_level,
        seed=protocol.bootstrap.seed,
    )
    metric_directions = {
        "precision": True,
        "attack_level_recall": True,
        "f1": True,
        "false_alerts_per_million_events": False,
        "detection_before_benefit_rate": True,
        "duplicate_alert_load": False,
    }
    paired_comparisons = {
        metric: paired_session_comparison(
            baseline_metrics,
            session_metrics,
            metric=metric,
            higher_is_better=metric_directions[metric],
            resamples=protocol.bootstrap.resamples,
            confidence_level=protocol.bootstrap.confidence_level,
            seed=protocol.bootstrap.seed,
        )
        for metric in interval_metrics
    }
    regimes = regime_metric_matrix(
        session_metrics,
        minimum_cell_count=protocol.metrics.minimum_regime_cell_count,
    )
    worst = worst_decile_results(
        session_metrics,
        metric_directions={
            "attack_level_recall": "lower",
            "f1": "lower",
            "detection_before_benefit_rate": "lower",
            "false_alerts_per_million_events": "higher",
            "duplicate_alert_load": "higher",
        },
        fraction=protocol.metrics.worst_decile_fraction,
    )
    results = GovernedBenchmarkResults(
        model_id=plan.model_id,
        protocol_id=protocol.protocol_id,
        protocol_hash=protocol.protocol_hash(),
        corpus_id=corpus.corpus_id,
        corpus_hash=corpus.corpus_hash(),
        split_id=split.split_id,
        assignment_hash=split.assignment_hash,
        fold=plan.fold,
        metrics=metrics,
        confidence_intervals=confidence_intervals,
        paired_comparisons=paired_comparisons,
        regime_matrix=regimes,
        worst_decile=worst,
        input_artifacts=input_artifacts,
    ).model_dump(mode="json")
    signed = args.signing_key is not None
    realized_benefit_covered = (
        not protocol.metrics.require_realized_benefit_event
        or sum(item.true_positive + item.false_negative for item in session_metrics)
        == sum(item.benefit_eligible_attack_count for item in session_metrics)
    )
    checks = {
        "corpus_validation": corpus_validation.verdict == "pass",
        "split_validation": split.corpus_hash == corpus.corpus_hash(),
        "complete_fold_coverage": planned_session_ids == expected_session_ids,
        "canonical_java_artifact_binding": len(
            [
                artifact
                for artifact in input_artifacts
                if artifact["kind"] == "canonical_java_replay"
            ]
        )
        == sum(1 + len(corpus_sessions[item].campaigns) for item in expected_session_ids),
        "independent_negative_label_validation": any(
            window.status == "verified_clean"
            for session_id in expected_session_ids
            for window in adjudications_by_session[session_id]
        ),
        "session_cluster_statistics": set(confidence_intervals) == set(interval_metrics),
        "paired_session_comparisons": set(paired_comparisons) == set(interval_metrics),
        "regime_and_worst_decile_reporting": (
            regimes.get("schema_version") == "regime_metric_matrix_v1"
            and worst.get("schema_version") == "worst_decile_results_v1"
        ),
        "train_fitted_regime_evidence": (
            set(regime_evidence.fit_session_ids) <= train_session_ids
            and set(regime_evidence.target_features) == expected_session_ids
        ),
        "full_session_streaming_gate": (
            {item.base_session_id for item in streaming_evidence} == expected_session_ids
            and all(item.full_session for item in streaming_evidence)
        ),
        "realized_benefit_coverage": realized_benefit_covered,
        "signed_release": signed,
    }
    validation = {
        "schema_version": "governed_benchmark_release_validation_v1",
        "verdict": "pass" if all(value for name, value in checks.items() if name != "signed_release") else "fail",
        "checks": checks,
        "training_gate_passed": signed or not protocol.require_signed_release_manifest,
    }
    manifest = write_governed_benchmark_release(
        args.output,
        results=results,
        session_metrics=session_metrics,
        validation=validation,
        signing_key=args.signing_key,
        signer=args.signer,
        overwrite=args.overwrite,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if validation["training_gate_passed"] else 2


def _resolve(root: Path, value: str | None) -> Path:
    if value is None:
        raise ValueError("required evaluation plan path is missing")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_session_metrics(path: Path) -> list[SessionMetricComponents]:
    rows = [
        SessionMetricComponents(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows or len({item.base_session_id for item in rows}) != len(rows):
        raise ValueError("baseline session metrics must contain unique base sessions")
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
