import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.corpus.governance import (
    ArtifactReference,
    CampaignManifest,
    GovernedSession,
    build_corpus_manifest,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.corpus.splits import (
    GovernedSplitManifest,
    generate_split_manifest,
    load_split_manifest,
    validate_split_manifest,
    write_split_manifest,
)


def _artifact(name: str, digest_source: str | None = None) -> ArtifactReference:
    digest = hashlib.sha256((digest_source or name).encode()).hexdigest()
    return ArtifactReference(
        name=name,
        uri=name,
        sha256=digest,
        size_bytes=1,
        schema_version="fixture_v1",
    )


def _session(index: int, *, source_digest: str | None = None) -> GovernedSession:
    family = ("spoofing_like_wall", "layering_like", "quote_stuffing")[index % 3]
    campaign = CampaignManifest(
        campaign_id=f"campaign-{index}",
        attack_family=family,
        master_seed=10,
        derived_seed=index + 1,
        injection_timestamp_ns=150,
        canonical_events=_artifact(f"campaign-{index}-events"),
        ground_truth=_artifact(f"campaign-{index}-labels"),
        validation=_artifact(f"campaign-{index}-validation"),
    )
    return GovernedSession(
        base_session_id=f"base-{index}",
        dataset_id=f"dataset-{index}",
        instrument=f"SYM{index % 3}",
        venue="LOBSTER",
        session_id=f"regular-{index}",
        session_date=date(2026, 1, 1) + timedelta(days=index),
        timezone="America/New_York",
        start_timestamp_ns=100,
        end_timestamp_ns=1_000,
        complete_session=True,
        source_manifest=_artifact(f"source-{index}"),
        canonical_control_events=_artifact(f"control-{index}", source_digest),
        control_validation=_artifact(f"validation-{index}"),
        campaigns=[campaign],
    )


def _protocol() -> GovernedBenchmarkProtocol:
    return GovernedBenchmarkProtocol(
        protocol_id="split-test-v1",
        corpus={
            "complete_sessions": 1,
            "instruments": 1,
            "distinct_dates": 1,
            "seeds_per_attack_family": 1,
            "require_all_attack_families": False,
            "required_attack_families": ["spoofing_like_wall"],
        },
        splits={
            "embargo_sessions": 1,
            "train_fraction": 0.6,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
        },
    )


def test_split_is_chronological_grouped_purged_and_frozen() -> None:
    protocol = _protocol()
    corpus = build_corpus_manifest(
        corpus_id="corpus",
        sessions=[_session(index) for index in range(10)],
        protocol=protocol,
        generated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    manifest = generate_split_manifest(
        split_id="split-v1",
        corpus=corpus,
        protocol=protocol,
        generated_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )

    by_fold = {
        fold: [item for item in manifest.assignments if item.fold == fold]
        for fold in ("train", "validation", "test")
    }
    assert max(item.session_date for item in by_fold["train"]) < min(
        item.session_date for item in by_fold["validation"]
    )
    assert max(item.session_date for item in by_fold["validation"]) < min(
        item.session_date for item in by_fold["test"]
    )
    assert manifest.purge_ns == 10_000_000_000
    assert manifest.test_frozen
    assert len(manifest.embargo) == 2
    assert all(item.campaign_ids for item in manifest.assignments)


def test_split_assignment_is_reproducible_and_timestamp_independent() -> None:
    protocol = _protocol()
    corpus = build_corpus_manifest(corpus_id="corpus", sessions=[_session(i) for i in range(10)], protocol=protocol)

    first = generate_split_manifest(
        split_id="split-v1",
        corpus=corpus,
        protocol=protocol,
        generated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    second = generate_split_manifest(
        split_id="split-v1",
        corpus=corpus,
        protocol=protocol,
        generated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert first.assignment_hash == second.assignment_hash
    assert first.assignments == second.assignments


def test_all_seed_and_campaign_variants_remain_with_base_session() -> None:
    protocol = _protocol()
    session = _session(0)
    session.campaigns.append(
        session.campaigns[0].model_copy(
            update={"campaign_id": "second-seed", "derived_seed": 999}
        )
    )
    corpus = build_corpus_manifest(
        corpus_id="corpus",
        sessions=[session, *[_session(i) for i in range(1, 10)]],
        protocol=protocol,
    )

    manifest = generate_split_manifest(split_id="split", corpus=corpus, protocol=protocol)
    assignment = next(item for item in manifest.assignments if item.base_session_id == "base-0")

    assert assignment.campaign_ids == ["campaign-0", "second-seed"]


def test_duplicate_source_hash_cannot_cross_folds() -> None:
    protocol = _protocol()
    sessions = [_session(i) for i in range(10)]
    corpus = build_corpus_manifest(corpus_id="corpus", sessions=sessions, protocol=protocol)
    manifest = generate_split_manifest(split_id="split", corpus=corpus, protocol=protocol)
    train = next(item for item in manifest.assignments if item.fold == "train")
    test = next(item for item in manifest.assignments if item.fold == "test")
    tampered_assignments = [
        item.model_copy(
            update={"source_session_hash": train.source_session_hash}
        )
        if item.base_session_id == test.base_session_id
        else item
        for item in manifest.assignments
    ]
    tampered = manifest.model_copy(
        update={
            "assignments": tampered_assignments,
            "assignment_hash": "0" * 64,
        }
    )

    with pytest.raises(ValueError, match="assignment hash"):
        validate_split_manifest(tampered, corpus=corpus, protocol=protocol)


def test_split_requires_enough_dates_for_folds_and_embargo() -> None:
    protocol = _protocol()
    corpus = build_corpus_manifest(
        corpus_id="small",
        sessions=[_session(i) for i in range(4)],
        protocol=protocol,
    )

    with pytest.raises(ValueError, match="three evaluable date groups"):
        generate_split_manifest(split_id="invalid", corpus=corpus, protocol=protocol)


def test_split_manifest_hash_is_fail_closed_and_round_trips(tmp_path) -> None:
    protocol = _protocol()
    corpus = build_corpus_manifest(corpus_id="corpus", sessions=[_session(i) for i in range(10)], protocol=protocol)
    manifest = generate_split_manifest(split_id="split", corpus=corpus, protocol=protocol)
    path = tmp_path / "split-manifest.json"

    write_split_manifest(path, manifest)

    assert load_split_manifest(path) == manifest
    payload = manifest.model_dump()
    payload["assignment_hash"] = "f" * 64
    with pytest.raises(ValidationError, match="does not match"):
        GovernedSplitManifest.model_validate(payload)
