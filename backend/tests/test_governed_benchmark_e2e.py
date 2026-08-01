import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from app.corpus.governance import (
    ArtifactReference,
    CampaignManifest,
    GovernedSession,
    build_corpus_manifest,
    validate_corpus,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.corpus.splits import generate_split_manifest, write_split_manifest
from app.evaluation.canonical_bundle import (
    CanonicalJavaReplayManifest,
    canonical_java_event_stream_hash,
)
from app.exchange.schemas import exchange_event_from_dict
from app.evaluation.release import verify_governed_benchmark_release
from app.evaluation.governed_metrics import SessionMetricComponents
from app.evaluation.regimes import (
    GovernedRegimeEvidence,
    RegimeFitRow,
    fit_regime_thresholds,
)
from scripts.benchmark_feature_streaming import main as benchmark_features
from scripts.evaluate_governed_benchmark import (
    GovernedEvaluationPlan,
    main as evaluate_benchmark,
)
from scripts.generate_features import main as generate_features


def _artifact(path: Path, schema: str) -> ArtifactReference:
    payload = path.read_bytes()
    return ArtifactReference(
        name=path.name,
        uri=str(path),
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        schema_version=schema,
    )


def _event(
    sequence: int,
    timestamp: int,
    *,
    snapshot: bool,
    identity: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "event_type": "snapshot" if snapshot else "add",
        "event_id": f"{identity}-event-{sequence}",
        "sequence": sequence,
        "source": "simulation",
        "source_sequence": sequence,
        "symbol": "SPY",
        "venue": "LOBSTER",
        "tick": sequence,
        "exchange_timestamp_ns": timestamp,
        "received_timestamp_ns": timestamp,
        "scenario_id": "campaign-1",
        "scenario_name": "spoofing_like_wall",
        "scenario_family": "spoofing_like_wall",
    }
    if snapshot:
        payload.update(
            {
                "depth": 1,
                "book": {
                    "bids": [{"price": 99.0, "quantity": 10.0}],
                    "asks": [{"price": 101.0, "quantity": 10.0}],
                    "best_bid": 99.0,
                    "best_ask": 101.0,
                    "mid": 100.0,
                    "spread": 2.0,
                },
            }
        )
    else:
        payload.update(
            {
                "order_id": f"SYN:{identity}:order",
                "agent_id": f"SYN:{identity}:agent",
                "side": "buy",
                "price": 99.0,
                "quantity": 10.0,
                "owner": "abuser",
            }
        )
    return payload


def _replay_bundle(
    directory: Path,
    *,
    mode: str,
    base_session_id: str,
    dataset_id: str,
    session_date: date,
) -> tuple[Path, dict[str, ArtifactReference]]:
    directory.mkdir(parents=True)
    events_path = directory / "events.jsonl"
    events = [
        _event(1, 100, snapshot=False, identity=base_session_id),
        _event(2, 200, snapshot=True, identity=base_session_id),
        _event(3, 350, snapshot=True, identity=base_session_id),
    ]
    events_path.write_text(
        "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    snapshots_path = directory / "snapshots.parquet"
    pq.write_table(pa.Table.from_pylist([{"tick": 2}, {"tick": 3}]), snapshots_path)
    alerts_path = directory / "alerts.jsonl"
    run_id = f"{base_session_id}-{mode}"
    campaign_id = "campaign-1" if mode == "hybrid" else None
    alert = {
        "run_id": run_id,
        "alert_id": f"alert-{mode}",
        "detector": "detector-v1",
        "timestamp_ns": 120 if mode == "hybrid" else 350,
    }
    if campaign_id:
        alert["campaign_id"] = campaign_id
    alerts_path.write_text(json.dumps(alert) + "\n", encoding="utf-8")
    labels_path = directory / "labels.jsonl"
    if mode == "hybrid":
        labels_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "campaign_id": campaign_id,
                    "ground_truth": {
                        "campaign_id": campaign_id,
                        "scenario_family": "spoofing_like_wall",
                        "start_tick": 1,
                        "end_tick": 2,
                        "first_benefit_tick": 2,
                        "source": "synthetic_scenario",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    stream_hash = canonical_java_event_stream_hash(
        [exchange_event_from_dict(event) for event in events],
        price_tick_size=0.01,
        quantity_lot_size=1,
    )
    validation_path = directory / "validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "verdict": "pass",
                "run_id": run_id,
                "base_session_id": base_session_id,
                "dataset_id": dataset_id,
                "campaign_id": campaign_id,
                "session_start_timestamp_ns": 100,
                "session_end_timestamp_ns": 1_000,
                "complete_session": True,
                "canonical_event_stream_hash": stream_hash,
            }
        ),
        encoding="utf-8",
    )
    references = {
        "events": _artifact(events_path, "canonical_events_v1"),
        "snapshots": _artifact(snapshots_path, "canonical_snapshots_v1"),
        "alerts": _artifact(alerts_path, "canonical_alerts_v1"),
        "validation": _artifact(validation_path, "hybrid_dataset_validation_v1"),
    }
    if mode == "hybrid":
        references["labels"] = _artifact(labels_path, "scenario_ground_truth_v1")
    manifest = CanonicalJavaReplayManifest(
        run_id=run_id,
        base_session_id=base_session_id,
        dataset_id=dataset_id,
        mode=mode,
        campaign_id=campaign_id,
        attack_family="spoofing_like_wall" if mode == "hybrid" else None,
        instrument="SPY",
        venue="LOBSTER",
        session_id=base_session_id,
        session_date=session_date,
        seed=7 if mode == "hybrid" else None,
        price_tick_size=0.01,
        quantity_lot_size=1,
        tick_interval_ns=100,
        java_engine_version="java-test",
        canonical_event_stream_hash=stream_hash,
        event_count=3,
        snapshot_count=2,
        alert_count=1,
        label_count=1 if mode == "hybrid" else 0,
        last_sequence=3,
        first_timestamp_ns=100,
        last_timestamp_ns=350,
        events=references["events"],
        snapshots=references["snapshots"],
        alerts=references["alerts"],
        ground_truth=references.get("labels"),
        validation=references["validation"],
    )
    manifest_path = directory / "replay-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path, references


def test_evaluation_plan_rejects_duplicate_sessions_and_replays() -> None:
    common = {
        "schema_version": "governed_evaluation_plan_v1",
        "model_id": "detector",
        "fold": "test",
        "adjudications": "adjudications.jsonl",
        "regime_evidence": "regimes.json",
        "baseline_session_metrics": "baseline.jsonl",
        "streaming_evidence": ["stream.json"],
    }
    with pytest.raises(ValidationError, match="replay manifests must be unique"):
        GovernedEvaluationPlan.model_validate(
            {
                **common,
                "sessions": [
                    {
                        "base_session_id": "one",
                        "replay_manifests": ["same.json", "same.json"],
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="base sessions must be unique"):
        GovernedEvaluationPlan.model_validate(
            {
                **common,
                "sessions": [
                    {"base_session_id": "one", "replay_manifests": ["a.json"]},
                    {"base_session_id": "one", "replay_manifests": ["b.json"]},
                ],
            }
        )
    with pytest.raises(ValidationError, match="complete verified release"):
        GovernedEvaluationPlan.model_validate(
            {
                **common,
                "detector_predictions_manifest": "predictions.json",
                "detector_artifact_root": "artifacts",
                "sessions": [
                    {
                        "base_session_id": "one",
                        "replay_manifests": ["one.json"],
                    }
                ],
            }
        )


def test_governed_canonical_benchmark_produces_verified_signed_release(tmp_path: Path) -> None:
    protocol = GovernedBenchmarkProtocol(
        protocol_id="e2e-protocol",
        corpus={
            "complete_sessions": 5,
            "instruments": 1,
            "distinct_dates": 5,
            "seeds_per_attack_family": 1,
            "require_all_attack_families": False,
            "required_attack_families": ["spoofing_like_wall"],
        },
        splits={"embargo_sessions": 1},
        bootstrap={"resamples": 100, "seed": 9},
        metrics={"minimum_regime_cell_count": 1},
        streaming={"max_memory_growth_fraction": 1.0},
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(protocol.model_dump_json(indent=2), encoding="utf-8")
    sessions: list[GovernedSession] = []
    replay_paths: dict[str, list[Path]] = {}
    for index in range(5):
        base_id = f"base-{index}"
        dataset_id = f"dataset-{index}"
        session_date = date(2026, 1, 1) + timedelta(days=index)
        control_path, control = _replay_bundle(
            tmp_path / base_id / "control",
            mode="historical_control",
            base_session_id=base_id,
            dataset_id=dataset_id,
            session_date=session_date,
        )
        hybrid_path, hybrid = _replay_bundle(
            tmp_path / base_id / "hybrid",
            mode="hybrid",
            base_session_id=base_id,
            dataset_id=dataset_id,
            session_date=session_date,
        )
        source_path = tmp_path / base_id / "source.json"
        source_path.write_text('{"source":"fixture"}\n', encoding="utf-8")
        sessions.append(
            GovernedSession(
                base_session_id=base_id,
                dataset_id=dataset_id,
                instrument="SPY",
                venue="LOBSTER",
                session_id=base_id,
                session_date=session_date,
                timezone="America/New_York",
                start_timestamp_ns=100,
                end_timestamp_ns=1_000,
                complete_session=True,
                source_manifest=_artifact(source_path, "source_manifest_v1"),
                canonical_control_events=control["events"],
                control_validation=control["validation"],
                campaigns=[
                    CampaignManifest(
                        campaign_id="campaign-1",
                        attack_family="spoofing_like_wall",
                        master_seed=42,
                        derived_seed=7,
                        injection_timestamp_ns=100,
                        canonical_events=hybrid["events"],
                        ground_truth=hybrid["labels"],
                        validation=hybrid["validation"],
                    )
                ],
            )
        )
        replay_paths[base_id] = [control_path, hybrid_path]
    corpus = build_corpus_manifest(
        corpus_id="e2e-corpus",
        sessions=sessions,
        protocol=protocol,
        generated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    corpus_path = tmp_path / "corpus-manifest.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    corpus_validation = validate_corpus(corpus, protocol, artifact_root=tmp_path)
    assert corpus_validation.verdict == "pass"
    corpus_validation_path = tmp_path / "corpus-validation.json"
    corpus_validation_path.write_text(
        corpus_validation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    split = generate_split_manifest(
        split_id="e2e-split",
        corpus=corpus,
        protocol=protocol,
        generated_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )
    split_path = tmp_path / "split-manifest.json"
    write_split_manifest(split_path, split)
    test_base = next(item.base_session_id for item in split.assignments if item.fold == "test")
    evidence_path = tmp_path / "review-evidence.json"
    evidence_path.write_text('{"review":"clean"}\n', encoding="utf-8")
    evidence = _artifact(evidence_path, "clean_review_evidence_v1").model_dump(mode="json")
    adjudications_path = tmp_path / "adjudications.jsonl"
    adjudications_path.write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": "clean_window_adjudication_v1",
                    "window_id": f"clean-{session.base_session_id}",
                    "base_session_id": session.base_session_id,
                    "start_timestamp_ns": 300,
                    "end_timestamp_ns": 400,
                    "status": "verified_clean",
                    "reviewer_decisions": [
                        {
                            "reviewer_id": reviewer,
                            "decision": "clean",
                            "reviewed_at": "2026-02-01T00:00:00Z",
                            "method": "independent canonical-event review",
                            "model_outputs_hidden": True,
                            "evidence": [evidence],
                        }
                        for reviewer in ("reviewer-a", "reviewer-b")
                    ],
                    "label_source": "independently_verified_clean",
                },
                sort_keys=True,
            )
            + "\n"
            for session in sessions
        ),
        encoding="utf-8",
    )
    feature_output = tmp_path / "governed-features"
    assert (
        generate_features(
            [
                "--replay-manifest",
                str(replay_paths[test_base][0]),
                "--clean-adjudications",
                str(adjudications_path),
                "--corpus-manifest",
                str(corpus_path),
                "--benchmark-protocol",
                str(protocol_path),
                "--artifact-root",
                str(tmp_path),
                "--output",
                str(feature_output),
            ]
        )
        == 0
    )
    feature_rows = pq.read_table(feature_output / "features.parquet").to_pylist()
    assert [row["label"] for row in feature_rows] == [None, 0]
    assert feature_rows[1]["label_source"] == "independently_verified_clean"
    feature_metadata = json.loads((feature_output / "run-metadata.json").read_text())
    assert feature_metadata["input"]["clean_negative_window_ids"] == [f"clean-{test_base}"]
    assert feature_metadata["input"]["clean_label_artifact_verification_mode"] == "local"

    train_base = next(item.base_session_id for item in split.assignments if item.fold == "train")
    regime_rows = [
        RegimeFitRow(
            base_session_id=train_base,
            split="train",
            control_or_pre_attack=True,
            feature_schema_version="lob_features_v1",
            feature_config_hash="a" * 64,
            liquidity_score=float(index + 1),
            realized_volatility_long=float(index + 1),
            spread_bps=float(index + 1),
            message_rate_long=float(index + 1),
        )
        for index in range(3)
    ]
    regime_evidence = GovernedRegimeEvidence(
        protocol_hash=protocol.protocol_hash(),
        corpus_hash=corpus.corpus_hash(),
        assignment_hash=split.assignment_hash,
        fit_session_ids=[train_base],
        fit_rows=regime_rows,
        thresholds=fit_regime_thresholds(regime_rows),
        target_features={
            test_base: {
                "liquidity_score": 2.0,
                "realized_volatility_long": 2.0,
                "spread_bps": 2.0,
                "message_rate_long": 2.0,
            }
        },
    )
    regime_path = tmp_path / "regime-evidence.json"
    regime_path.write_text(regime_evidence.model_dump_json(indent=2), encoding="utf-8")
    baseline = SessionMetricComponents(
        base_session_id=test_base,
        instrument="SPY",
        regimes={"liquidity": "normal", "volatility": "normal"},
        true_positive=1,
        false_positive=0,
        false_negative=0,
        true_negative=1,
        evaluable_event_count=3,
        raw_false_alert_count=0,
        false_alert_cluster_count=0,
        raw_evaluable_alert_count=1,
        evaluable_alert_cluster_count=1,
        benefit_eligible_attack_count=1,
        detected_before_benefit_count=1,
        detection_latencies_ns=(20,),
    )
    baseline_path = tmp_path / "baseline-session-metrics.jsonl"
    baseline_path.write_text(json.dumps(asdict(baseline)) + "\n", encoding="utf-8")
    streaming_path = tmp_path / "streaming-evidence.json"
    assert (
        benchmark_features(
            [
                "--replay-manifest",
                str(replay_paths[test_base][0]),
                "--artifact-root",
                str(tmp_path),
                "--corpus",
                str(corpus_path),
                "--protocol",
                str(protocol_path),
                "--output",
                str(tmp_path / "streaming-primary"),
                "--comparison-output",
                str(tmp_path / "streaming-comparison"),
                "--report",
                str(streaming_path),
                "--row-group-size",
                "1",
                "--comparison-row-group-size",
                "2",
            ]
        )
        == 0
    )

    plan_path = tmp_path / "evaluation-plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "governed_evaluation_plan_v1",
                "model_id": "detector-v1",
                "fold": "test",
                "adjudications": str(adjudications_path),
                "regime_evidence": str(regime_path),
                "baseline_session_metrics": str(baseline_path),
                "streaming_evidence": [str(streaming_path)],
                "sessions": [
                    {
                        "base_session_id": test_base,
                        "replay_manifests": [str(path) for path in replay_paths[test_base]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    key = tmp_path / "private.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(key)],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "release"

    exit_code = evaluate_benchmark(
        [
            "--plan",
            str(plan_path),
            "--corpus",
            str(corpus_path),
            "--corpus-validation",
            str(corpus_validation_path),
            "--split",
            str(split_path),
            "--protocol",
            str(protocol_path),
            "--output",
            str(output),
            "--signing-key",
            str(key),
            "--signer",
            "Independent QA",
        ]
    )

    assert exit_code == 0
    verify_governed_benchmark_release(output)
    results = json.loads((output / "benchmark-results.json").read_text())
    assert results["metrics"]["true_positive"] == 1
    assert results["metrics"]["false_positive"] == 1
    assert results["metrics"]["attack_level_recall"] == 1.0
    assert results["metrics"]["detection_before_benefit_rate"] == 1.0
    assert results["confidence_intervals"]["f1"]["cluster_unit"] == "base_session"
