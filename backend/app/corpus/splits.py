from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.corpus.governance import GovernedCorpusManifest, GovernedSession, SHA256_PATTERN
from app.corpus.models import GovernedBenchmarkProtocol


SPLIT_SCHEMA_VERSION = "governed_split_manifest_v1"
FoldName = Literal["train", "validation", "test"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionSplitAssignment(_StrictModel):
    base_session_id: str = Field(min_length=1)
    split_group: str = Field(min_length=1)
    source_session_hash: str = Field(pattern=SHA256_PATTERN)
    fold: FoldName
    session_date: date
    instrument: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    campaign_ids: list[str]


class FoldSummary(_StrictModel):
    fold: FoldName
    first_date: date
    last_date: date
    session_count: int = Field(ge=1)
    campaign_count: int = Field(ge=0)
    instruments: list[str] = Field(min_length=1)
    base_session_ids: list[str] = Field(min_length=1)


class EmbargoGroup(_StrictModel):
    between: Literal["train_validation", "validation_test"]
    session_dates: list[date] = Field(min_length=1)
    base_session_ids: list[str] = Field(min_length=1)


class GovernedSplitManifest(_StrictModel):
    schema_version: Literal["governed_split_manifest_v1"] = SPLIT_SCHEMA_VERSION
    split_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    corpus_hash: str = Field(pattern=SHA256_PATTERN)
    protocol_id: str = Field(min_length=1)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    generated_at: datetime
    strategy: Literal["chronological_session_grouped_purged"]
    split_group_fields: list[str] = Field(min_length=1)
    purge_ns: int = Field(ge=0)
    embargo_date_groups: int = Field(ge=0)
    assignments: list[SessionSplitAssignment] = Field(min_length=3)
    embargo: list[EmbargoGroup]
    folds: list[FoldSummary] = Field(min_length=3, max_length=3)
    test_frozen: Literal[True] = True
    assignment_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fold_inventory(self) -> "GovernedSplitManifest":
        fold_names = [fold.fold for fold in self.folds]
        if set(fold_names) != {"train", "validation", "test"} or len(fold_names) != 3:
            raise ValueError("split manifest requires exactly one train, validation, and test summary")
        assigned = [item.base_session_id for item in self.assignments]
        if len(assigned) != len(set(assigned)):
            raise ValueError("base sessions must have exactly one split assignment")
        if self.assignment_hash != _assignment_hash(self):
            raise ValueError("split assignment hash does not match manifest content")
        return self


def generate_split_manifest(
    *,
    split_id: str,
    corpus: GovernedCorpusManifest,
    protocol: GovernedBenchmarkProtocol,
    generated_at: datetime | None = None,
) -> GovernedSplitManifest:
    if corpus.protocol_id != protocol.protocol_id or corpus.protocol_hash != protocol.protocol_hash():
        raise ValueError("corpus protocol binding does not match split protocol")
    sessions_by_date: dict[date, list[GovernedSession]] = defaultdict(list)
    for session in corpus.sessions:
        sessions_by_date[session.session_date].append(session)
    dates = sorted(sessions_by_date)
    embargo_count = protocol.splits.embargo_sessions
    allocatable = len(dates) - 2 * embargo_count
    if allocatable < 3:
        raise ValueError("chronological split requires three evaluable date groups plus both embargo boundaries")
    train_count, validation_count, test_count = _fractional_counts(
        allocatable,
        (
            protocol.splits.train_fraction,
            protocol.splits.validation_fraction,
            protocol.splits.test_fraction,
        ),
    )
    train_end = train_count
    first_embargo_end = train_end + embargo_count
    validation_end = first_embargo_end + validation_count
    second_embargo_end = validation_end + embargo_count
    fold_dates: dict[FoldName, list[date]] = {
        "train": dates[:train_end],
        "validation": dates[first_embargo_end:validation_end],
        "test": dates[second_embargo_end : second_embargo_end + test_count],
    }
    embargo_dates = {
        "train_validation": dates[train_end:first_embargo_end],
        "validation_test": dates[validation_end:second_embargo_end],
    }
    assignments: list[SessionSplitAssignment] = []
    for fold in ("train", "validation", "test"):
        for session_date in fold_dates[fold]:
            for session in sorted(sessions_by_date[session_date], key=_session_sort_key):
                assignments.append(_assignment(session, fold))
    embargo: list[EmbargoGroup] = []
    for boundary, boundary_dates in embargo_dates.items():
        if not boundary_dates:
            continue
        embargo.append(
            EmbargoGroup(
                between=boundary,
                session_dates=boundary_dates,
                base_session_ids=sorted(
                    session.base_session_id
                    for session_date in boundary_dates
                    for session in sessions_by_date[session_date]
                ),
            )
        )
    folds = [
        _fold_summary(fold, fold_dates[fold], assignments)
        for fold in ("train", "validation", "test")
    ]
    partial = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "split_id": split_id,
        "corpus_id": corpus.corpus_id,
        "corpus_hash": corpus.corpus_hash(),
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.protocol_hash(),
        "generated_at": generated_at or datetime.now(timezone.utc),
        "strategy": protocol.splits.strategy,
        "split_group_fields": list(protocol.splits.group_fields),
        "purge_ns": protocol.splits.purge_ns,
        "embargo_date_groups": embargo_count,
        "assignments": assignments,
        "embargo": embargo,
        "folds": folds,
        "test_frozen": True,
        "assignment_hash": "0" * 64,
    }
    provisional = GovernedSplitManifest.model_construct(**partial)
    partial["assignment_hash"] = _assignment_hash(provisional)
    manifest = GovernedSplitManifest.model_validate(partial)
    validate_split_manifest(manifest, corpus=corpus, protocol=protocol)
    return manifest


def validate_split_manifest(
    manifest: GovernedSplitManifest,
    *,
    corpus: GovernedCorpusManifest,
    protocol: GovernedBenchmarkProtocol,
) -> None:
    if manifest.assignment_hash != _assignment_hash(manifest):
        raise ValueError("split assignment hash does not match manifest contents")
    if manifest.corpus_id != corpus.corpus_id or manifest.corpus_hash != corpus.corpus_hash():
        raise ValueError("split manifest corpus binding is invalid")
    if manifest.protocol_id != protocol.protocol_id or manifest.protocol_hash != protocol.protocol_hash():
        raise ValueError("split manifest protocol binding is invalid")
    if (
        manifest.strategy != protocol.splits.strategy
        or manifest.split_group_fields != list(protocol.splits.group_fields)
        or manifest.purge_ns != protocol.splits.purge_ns
        or manifest.embargo_date_groups != protocol.splits.embargo_sessions
    ):
        raise ValueError("split manifest policy fields do not match the governed protocol")
    corpus_ids = {session.base_session_id for session in corpus.sessions}
    assigned_ids = {item.base_session_id for item in manifest.assignments}
    embargo_ids = {
        base_session_id
        for group in manifest.embargo
        for base_session_id in group.base_session_ids
    }
    if assigned_ids & embargo_ids:
        raise ValueError("embargo sessions must not have train, validation, or test assignments")
    if assigned_ids | embargo_ids != corpus_ids:
        raise ValueError("every corpus session must be assigned to a fold or explicit embargo")
    sessions = {session.base_session_id: session for session in corpus.sessions}
    dates_by_fold = {
        fold: [sessions[item.base_session_id].session_date for item in manifest.assignments if item.fold == fold]
        for fold in ("train", "validation", "test")
    }
    if not (
        max(dates_by_fold["train"]) < min(dates_by_fold["validation"])
        and max(dates_by_fold["validation"]) < min(dates_by_fold["test"])
    ):
        raise ValueError("split folds must be strictly chronological")
    source_folds: dict[str, set[str]] = defaultdict(set)
    for item in manifest.assignments:
        source_folds[sessions[item.base_session_id].canonical_control_events.sha256].add(item.fold)
    leaked_sources = {
        digest: sorted(folds)
        for digest, folds in source_folds.items()
        if len(folds) > 1
    }
    if leaked_sources:
        raise ValueError(f"duplicate source sessions cross folds: {leaked_sources}")
    for item in manifest.assignments:
        session = sessions[item.base_session_id]
        expected_campaigns = sorted(campaign.campaign_id for campaign in session.campaigns)
        if item.campaign_ids != expected_campaigns:
            raise ValueError(f"session campaign inventory is incomplete: {item.base_session_id}")
        if item.split_group != _split_group(session):
            raise ValueError(f"session split group is invalid: {item.base_session_id}")
        if (
            item.source_session_hash != session.canonical_control_events.sha256
            or item.session_date != session.session_date
            or item.instrument != session.instrument
            or item.venue != session.venue
        ):
            raise ValueError(f"session split assignment metadata is invalid: {item.base_session_id}")
    _validate_expected_partition(manifest, corpus=corpus, protocol=protocol)
    expected_summaries = {
        fold: _fold_summary(
            fold,
            sorted(
                {
                    sessions[item.base_session_id].session_date
                    for item in manifest.assignments
                    if item.fold == fold
                }
            ),
            manifest.assignments,
        )
        for fold in ("train", "validation", "test")
    }
    if any(
        summary != expected_summaries[summary.fold]
        for summary in manifest.folds
    ):
        raise ValueError("split fold summaries do not match assignments")


def _validate_expected_partition(
    manifest: GovernedSplitManifest,
    *,
    corpus: GovernedCorpusManifest,
    protocol: GovernedBenchmarkProtocol,
) -> None:
    sessions_by_date: dict[date, list[GovernedSession]] = defaultdict(list)
    for session in corpus.sessions:
        sessions_by_date[session.session_date].append(session)
    dates = sorted(sessions_by_date)
    embargo_count = protocol.splits.embargo_sessions
    allocatable = len(dates) - 2 * embargo_count
    train_count, validation_count, test_count = _fractional_counts(
        allocatable,
        (
            protocol.splits.train_fraction,
            protocol.splits.validation_fraction,
            protocol.splits.test_fraction,
        ),
    )
    train_end = train_count
    first_embargo_end = train_end + embargo_count
    validation_end = first_embargo_end + validation_count
    second_embargo_end = validation_end + embargo_count
    expected_fold_dates = {
        "train": set(dates[:train_end]),
        "validation": set(dates[first_embargo_end:validation_end]),
        "test": set(dates[second_embargo_end : second_embargo_end + test_count]),
    }
    expected_assignment = {
        session.base_session_id: fold
        for fold, fold_dates in expected_fold_dates.items()
        for session_date in fold_dates
        for session in sessions_by_date[session_date]
    }
    observed_assignment = {
        item.base_session_id: item.fold
        for item in manifest.assignments
    }
    if observed_assignment != expected_assignment:
        raise ValueError("split assignments do not match the deterministic chronological partition")
    expected_embargo = {
        "train_validation": {
            session.base_session_id
            for session_date in dates[train_end:first_embargo_end]
            for session in sessions_by_date[session_date]
        },
        "validation_test": {
            session.base_session_id
            for session_date in dates[validation_end:second_embargo_end]
            for session in sessions_by_date[session_date]
        },
    }
    observed_embargo = {
        group.between: set(group.base_session_ids)
        for group in manifest.embargo
    }
    expected_embargo_dates = {
        "train_validation": set(dates[train_end:first_embargo_end]),
        "validation_test": set(dates[validation_end:second_embargo_end]),
    }
    expected_embargo_dates = {
        boundary: values
        for boundary, values in expected_embargo_dates.items()
        if values
    }
    observed_embargo_dates = {
        group.between: set(group.session_dates)
        for group in manifest.embargo
    }
    expected_embargo = {
        boundary: ids
        for boundary, ids in expected_embargo.items()
        if ids
    }
    if (
        observed_embargo != expected_embargo
        or observed_embargo_dates != expected_embargo_dates
    ):
        raise ValueError("split embargo inventory does not match the deterministic partition")


def write_split_manifest(path: Path, manifest: GovernedSplitManifest, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise ValueError("split manifest already exists; create a new version or enable overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_split_manifest(path: Path) -> GovernedSplitManifest:
    return GovernedSplitManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _fractional_counts(total: int, fractions: tuple[float, float, float]) -> tuple[int, int, int]:
    if total < 3:
        raise ValueError("at least three date groups are required")
    remaining = total - 3
    raw = [fraction * remaining for fraction in fractions]
    extra = [math.floor(value) for value in raw]
    leftover = remaining - sum(extra)
    order = sorted(range(3), key=lambda index: (raw[index] - extra[index], -index), reverse=True)
    for index in order[:leftover]:
        extra[index] += 1
    return tuple(value + 1 for value in extra)


def _assignment(session: GovernedSession, fold: FoldName) -> SessionSplitAssignment:
    return SessionSplitAssignment(
        base_session_id=session.base_session_id,
        split_group=_split_group(session),
        source_session_hash=session.canonical_control_events.sha256,
        fold=fold,
        session_date=session.session_date,
        instrument=session.instrument,
        venue=session.venue,
        campaign_ids=sorted(campaign.campaign_id for campaign in session.campaigns),
    )


def _split_group(session: GovernedSession) -> str:
    identity = "|".join(
        (
            session.venue,
            session.instrument,
            session.session_date.isoformat(),
            session.session_id,
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _fold_summary(
    fold: FoldName,
    dates: list[date],
    assignments: list[SessionSplitAssignment],
) -> FoldSummary:
    items = [item for item in assignments if item.fold == fold]
    return FoldSummary(
        fold=fold,
        first_date=min(dates),
        last_date=max(dates),
        session_count=len(items),
        campaign_count=sum(len(item.campaign_ids) for item in items),
        instruments=sorted({item.instrument for item in items}),
        base_session_ids=sorted(item.base_session_id for item in items),
    )


def _assignment_hash(manifest: GovernedSplitManifest) -> str:
    payload = {
        "schema_version": manifest.schema_version,
        "split_id": manifest.split_id,
        "corpus_id": manifest.corpus_id,
        "corpus_hash": manifest.corpus_hash,
        "protocol_id": manifest.protocol_id,
        "protocol_hash": manifest.protocol_hash,
        "strategy": manifest.strategy,
        "split_group_fields": manifest.split_group_fields,
        "purge_ns": manifest.purge_ns,
        "embargo_date_groups": manifest.embargo_date_groups,
        "assignments": [
            item.model_dump(mode="json")
            for item in sorted(manifest.assignments, key=lambda value: value.base_session_id)
        ],
        "embargo": [
            item.model_dump(mode="json")
            for item in sorted(manifest.embargo, key=lambda value: value.between)
        ],
        "test_frozen": manifest.test_frozen,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _session_sort_key(session: GovernedSession) -> tuple[str, str, str]:
    return session.venue, session.instrument, session.session_id
