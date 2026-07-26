import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.corpus.governance import (
    AdjudicatorDecision,
    ArtifactReference,
    CampaignManifest,
    CleanWindowAdjudication,
    GovernedSession,
    GovernedCorpusManifest,
    ReviewDecision,
    build_corpus_manifest,
    merge_verified_clean_feature_labels,
    validate_adjudications,
    validate_corpus,
    write_corpus_bundle,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.features.models import LabelSpec, LabelWindow, assign_label


def _artifact(name: str, *, payload: bytes = b"x") -> ArtifactReference:
    return ArtifactReference(
        name=name,
        uri=name,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        schema_version="fixture_v1",
    )


def _campaign(family: str, seed: int) -> CampaignManifest:
    return CampaignManifest(
        campaign_id=f"{family}-{seed}",
        attack_family=family,
        master_seed=42,
        derived_seed=seed,
        injection_timestamp_ns=150,
        canonical_events=_artifact(f"{family}-{seed}-events.jsonl"),
        ground_truth=_artifact(f"{family}-{seed}-labels.jsonl"),
        validation=_artifact(f"{family}-{seed}-validation.json"),
    )


def _session(index: int = 0) -> GovernedSession:
    return GovernedSession(
        base_session_id=f"session-{index}",
        dataset_id=f"dataset-{index}",
        instrument=f"SYM{index % 3}",
        venue="LOBSTER",
        session_id=f"regular-{index}",
        session_date=date(2026, 1, index + 1),
        timezone="America/New_York",
        start_timestamp_ns=100,
        end_timestamp_ns=1_000,
        complete_session=True,
        source_manifest=_artifact(f"source-{index}.json"),
        canonical_control_events=_artifact(f"control-{index}.jsonl"),
        control_validation=_artifact(f"validation-{index}.json"),
        campaigns=[
            _campaign(family, seed)
            for family in ("spoofing_like_wall", "layering_like", "quote_stuffing")
            for seed in (1, 2, 3)
        ],
    )


def _small_protocol() -> GovernedBenchmarkProtocol:
    return GovernedBenchmarkProtocol(
        protocol_id="test-protocol",
        corpus={
            "complete_sessions": 1,
            "instruments": 1,
            "distinct_dates": 1,
            "seeds_per_attack_family": 3,
            "require_all_attack_families": True,
            "required_attack_families": [
                "spoofing_like_wall",
                "layering_like",
                "quote_stuffing",
            ],
        },
    )


def _review(reviewer: str, decision: str = "clean") -> ReviewDecision:
    return ReviewDecision(
        reviewer_id=reviewer,
        decision=decision,
        reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        method="independent raw-event and data-quality review",
        model_outputs_hidden=True,
        evidence=[_artifact(f"{reviewer}-evidence.json")],
    )


def test_corpus_registry_computes_coverage_and_passes_explicit_minimums() -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(
        corpus_id="corpus-v1",
        sessions=[_session()],
        protocol=protocol,
        generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    validation = validate_corpus(manifest, protocol)

    assert validation.verdict == "pass"
    assert manifest.coverage.complete_sessions == 1
    assert manifest.coverage.attack_families == [
        "layering_like",
        "quote_stuffing",
        "spoofing_like_wall",
    ]
    assert validation.checks["artifact_integrity"]["verification_mode"] == "metadata_only"
    assert validation.artifact_verification_mode == "metadata_only"


def test_default_protocol_rejects_small_provisional_corpus() -> None:
    protocol = GovernedBenchmarkProtocol(protocol_id="production")
    manifest = build_corpus_manifest(corpus_id="too-small", sessions=[_session()], protocol=protocol)

    validation = validate_corpus(manifest, protocol)

    assert validation.verdict == "fail"


def test_corpus_validation_recomputes_and_rejects_forged_coverage() -> None:
    protocol = GovernedBenchmarkProtocol(protocol_id="production")
    manifest = build_corpus_manifest(
        corpus_id="forged",
        sessions=[_session()],
        protocol=protocol,
    )
    payload = manifest.model_dump(mode="json")
    payload["coverage"] = {
        "complete_sessions": 30,
        "instruments": ["A", "B", "C"],
        "distinct_dates": [f"2026-02-{day:02d}" for day in range(1, 11)],
        "attack_families": ["layering_like", "quote_stuffing", "spoofing_like_wall"],
        "seeds_by_attack_family": {
            family: [1, 2, 3]
            for family in ("layering_like", "quote_stuffing", "spoofing_like_wall")
        },
    }
    forged = GovernedCorpusManifest.model_validate(payload)

    validation = validate_corpus(forged, protocol)

    assert validation.verdict == "fail"
    assert validation.checks["coverage_consistency"]["passed"] is False
    assert validation.checks["complete_session_coverage"]["observed"] == 1
    assert validation.checks["complete_session_coverage"]["passed"] is False
    assert validation.checks["instrument_coverage"]["passed"] is False


def test_local_artifact_verification_fails_closed_on_digest_mismatch(tmp_path: Path) -> None:
    protocol = _small_protocol()
    session = _session()
    for reference in [
        session.source_manifest,
        session.canonical_control_events,
        session.control_validation,
        *[
            artifact
            for campaign in session.campaigns
            for artifact in (campaign.canonical_events, campaign.ground_truth, campaign.validation)
        ],
    ]:
        (tmp_path / reference.uri).write_bytes(b"x")
    (tmp_path / session.source_manifest.uri).write_bytes(b"tampered")
    manifest = build_corpus_manifest(corpus_id="tampered", sessions=[session], protocol=protocol)

    validation = validate_corpus(manifest, protocol, artifact_root=tmp_path)

    assert validation.verdict == "fail"
    assert validation.checks["artifact_integrity"]["passed"] is False


def test_verified_clean_requires_independent_blinded_reviews() -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    verified = CleanWindowAdjudication(
        window_id="clean-1",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("reviewer-a"), _review("reviewer-b")],
        label_source="independently_verified_clean",
    )

    validate_adjudications([verified], manifest=manifest, protocol=protocol)

    missing_reviewer = verified.model_copy(update={"reviewer_decisions": [_review("reviewer-a")]})
    with pytest.raises(ValueError, match="lacks independent reviewers"):
        validate_adjudications([missing_reviewer], manifest=manifest, protocol=protocol)

    with pytest.raises(ValidationError, match="model_outputs_hidden"):
        ReviewDecision(
            reviewer_id="leaky",
            decision="clean",
            reviewed_at=datetime.now(timezone.utc),
            method="looked at model alerts",
            model_outputs_hidden=False,
            evidence=[_artifact("evidence")],
        )


def test_adjudication_evidence_is_verified_when_artifact_root_is_supplied(tmp_path: Path) -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    verified = CleanWindowAdjudication(
        window_id="clean-evidence",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("reviewer-a"), _review("reviewer-b")],
        label_source="independently_verified_clean",
    )

    with pytest.raises(ValueError, match="evidence failed artifact verification"):
        validate_adjudications(
            [verified],
            manifest=manifest,
            protocol=protocol,
            artifact_root=tmp_path,
        )

    for reviewer in ("reviewer-a", "reviewer-b"):
        (tmp_path / f"{reviewer}-evidence.json").write_bytes(b"x")
    validate_adjudications(
        [verified],
        manifest=manifest,
        protocol=protocol,
        artifact_root=tmp_path,
    )


def test_reviewer_disagreement_requires_independent_clean_adjudicator() -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    disputed = CleanWindowAdjudication(
        window_id="disputed",
        base_session_id="session-0",
        start_timestamp_ns=300,
        end_timestamp_ns=400,
        status="verified_clean",
        reviewer_decisions=[_review("reviewer-a"), _review("reviewer-b", "not_clean")],
        label_source="independently_verified_clean",
    )
    with pytest.raises(ValueError, match="unresolved reviewer disagreement"):
        validate_adjudications([disputed], manifest=manifest, protocol=protocol)

    resolved = disputed.model_copy(
        update={
            "adjudicator_decision": AdjudicatorDecision(
                adjudicator_id="adjudicator",
                decision="clean",
                decided_at=datetime.now(timezone.utc),
                rationale="independent source review resolved the discrepancy",
            )
        }
    )
    validate_adjudications([resolved], manifest=manifest, protocol=protocol)


def test_supervised_windows_cannot_overlap_and_history_is_not_default_negative() -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    first = CleanWindowAdjudication(
        window_id="clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=400,
        status="verified_clean",
        reviewer_decisions=[_review("a"), _review("b")],
        label_source="independently_verified_clean",
    )
    second_clean = CleanWindowAdjudication(
        window_id="second-clean",
        base_session_id="session-0",
        start_timestamp_ns=350,
        end_timestamp_ns=500,
        status="verified_clean",
        reviewer_decisions=[_review("c"), _review("d")],
        label_source="independently_verified_clean",
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_adjudications([first, second_clean], manifest=manifest, protocol=protocol)
    assert protocol.clean_labels.historical_default_label is None


def test_verified_clean_windows_become_only_explicit_replay_appropriate_negatives() -> None:
    control_clean = CleanWindowAdjudication(
        window_id="control-clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("control-a"), _review("control-b")],
        label_source="independently_verified_clean",
    )
    transferred_clean = CleanWindowAdjudication(
        window_id="hybrid-clean",
        base_session_id="session-0",
        start_timestamp_ns=400,
        end_timestamp_ns=500,
        status="verified_clean",
        reviewer_decisions=[_review("hybrid-a"), _review("hybrid-b")],
        label_source="independently_verified_clean",
        transferred_from_control_window_id="control-source",
        exact_equivalence_validation=_artifact("hybrid-equivalence.json"),
    )
    ambiguous = CleanWindowAdjudication(
        window_id="ambiguous",
        base_session_id="session-0",
        start_timestamp_ns=600,
        end_timestamp_ns=700,
        status="ambiguous",
    )
    adjudications = [control_clean, transferred_clean, ambiguous]
    attack_labels = LabelSpec(
        labels=[LabelWindow(attack_family="layering_like", start_tick=4, end_tick=5)]
    )

    control = merge_verified_clean_feature_labels(
        LabelSpec(),
        adjudications,
        base_session_id="session-0",
        replay_mode="historical_control",
    )
    hybrid = merge_verified_clean_feature_labels(
        attack_labels,
        adjudications,
        base_session_id="session-0",
        replay_mode="hybrid",
    )
    synthetic = merge_verified_clean_feature_labels(
        attack_labels,
        adjudications,
        base_session_id="session-0",
        replay_mode="synthetic",
    )

    assert [window.provenance_id for window in control.labels] == ["control-clean"]
    assert [window.provenance_id for window in hybrid.labels if window.label == 0] == [
        "hybrid-clean"
    ]
    assert all(window.label == 1 for window in synthetic.labels)
    assert assign_label(control, tick=1, prediction_timestamp_ns=200).label == 0
    assert assign_label(control, tick=1, prediction_timestamp_ns=299).label == 0
    assert assign_label(control, tick=1, prediction_timestamp_ns=300).label is None
    assert assign_label(control, tick=1, prediction_timestamp_ns=650).label is None
    assert control.default_label is None


def test_governed_negative_merge_rejects_session_wide_default_labels() -> None:
    with pytest.raises(ValueError, match="session-wide default"):
        merge_verified_clean_feature_labels(
            LabelSpec(default_label=0, default_label_source="manual"),
            [],
            base_session_id="session-0",
            replay_mode="historical_control",
        )


def test_hybrid_clean_transfer_must_bind_same_verified_control_window() -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    control = CleanWindowAdjudication(
        window_id="control-clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("control-a"), _review("control-b")],
        label_source="independently_verified_clean",
    )
    transferred = CleanWindowAdjudication(
        window_id="hybrid-clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("hybrid-a"), _review("hybrid-b")],
        label_source="independently_verified_clean",
        transferred_from_control_window_id="control-clean",
        exact_equivalence_validation=_artifact("equivalence.json"),
    )

    validate_adjudications([control, transferred], manifest=manifest, protocol=protocol)

    missing_source = transferred.model_copy(
        update={"transferred_from_control_window_id": "missing"}
    )
    with pytest.raises(ValueError, match="does not match a verified control"):
        validate_adjudications([control, missing_source], manifest=manifest, protocol=protocol)


def test_hybrid_clean_transfer_requires_semantic_causal_equivalence_evidence(
    tmp_path: Path,
) -> None:
    protocol = _small_protocol()
    session = _session()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[session], protocol=protocol)
    control = CleanWindowAdjudication(
        window_id="control-clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("control-a"), _review("control-b")],
        label_source="independently_verified_clean",
    )
    for reviewer in ("control-a", "control-b", "hybrid-a", "hybrid-b"):
        (tmp_path / f"{reviewer}-evidence.json").write_bytes(b"x")
    payload = {
        "schema_version": "governed_clean_window_equivalence_v1",
        "verdict": "pass",
        "base_session_id": "session-0",
        "dataset_id": session.dataset_id,
        "source_control_window_id": "control-clean",
        "transferred_window_id": "hybrid-clean",
        "window_start_timestamp_ns": 200,
        "window_end_timestamp_ns": 300,
        "control_events_sha256": session.canonical_control_events.sha256,
        "campaign_id": session.campaigns[0].campaign_id,
        "hybrid_events_sha256": session.campaigns[0].canonical_events.sha256,
        "outside_causal_neighbourhood_equivalent": True,
        "exact_book_match_rate": 1.0,
        "causal_start_timestamp_ns": 400,
        "causal_end_timestamp_ns": 500,
    }
    evidence_bytes = (json.dumps(payload, sort_keys=True) + "\n").encode()
    (tmp_path / "equivalence.json").write_bytes(evidence_bytes)
    transferred = CleanWindowAdjudication(
        window_id="hybrid-clean",
        base_session_id="session-0",
        start_timestamp_ns=200,
        end_timestamp_ns=300,
        status="verified_clean",
        reviewer_decisions=[_review("hybrid-a"), _review("hybrid-b")],
        label_source="independently_verified_clean",
        transferred_from_control_window_id="control-clean",
        exact_equivalence_validation=_artifact(
            "equivalence.json",
            payload=evidence_bytes,
        ),
    )

    validate_adjudications(
        [control, transferred],
        manifest=manifest,
        protocol=protocol,
        artifact_root=tmp_path,
    )

    invalid_payload = {**payload, "exact_book_match_rate": 0.99}
    invalid_bytes = (json.dumps(invalid_payload, sort_keys=True) + "\n").encode()
    (tmp_path / "equivalence.json").write_bytes(invalid_bytes)
    invalid = transferred.model_copy(
        update={
            "exact_equivalence_validation": _artifact(
                "equivalence.json",
                payload=invalid_bytes,
            )
        }
    )
    with pytest.raises(ValueError, match="passing campaign"):
        validate_adjudications(
            [control, invalid],
            manifest=manifest,
            protocol=protocol,
            artifact_root=tmp_path,
        )


def test_corpus_bundle_is_atomic_and_preserves_nullable_history(tmp_path: Path) -> None:
    protocol = _small_protocol()
    manifest = build_corpus_manifest(corpus_id="corpus", sessions=[_session()], protocol=protocol)
    validation = validate_corpus(manifest, protocol)

    write_corpus_bundle(
        tmp_path,
        manifest=manifest,
        validation=validation,
        adjudications=[],
    )

    assert json.loads((tmp_path / "corpus-manifest.json").read_text())["corpus_id"] == "corpus"
    assert (tmp_path / "label-adjudications.jsonl").read_text() == ""
    with pytest.raises(ValueError, match="already exists"):
        write_corpus_bundle(
            tmp_path,
            manifest=manifest,
            validation=validation,
            adjudications=[],
        )
