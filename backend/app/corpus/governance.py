from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.corpus.models import GovernedBenchmarkProtocol
from app.features.models import LABEL_SCHEMA_VERSION, LabelSpec, LabelWindow


SHA256_PATTERN = r"^[0-9a-f]{64}$"
CORPUS_SCHEMA_VERSION = "governed_corpus_v1"
ADJUDICATION_SCHEMA_VERSION = "clean_window_adjudication_v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactReference(_StrictModel):
    name: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    schema_version: str = Field(min_length=1)


class CampaignManifest(_StrictModel):
    campaign_id: str = Field(min_length=1)
    attack_family: str = Field(min_length=1)
    master_seed: int = Field(ge=0)
    derived_seed: int = Field(ge=0)
    injection_timestamp_ns: int = Field(ge=0)
    canonical_events: ArtifactReference
    ground_truth: ArtifactReference
    validation: ArtifactReference


class GovernedSession(_StrictModel):
    base_session_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    session_date: date
    timezone: str = Field(min_length=1)
    start_timestamp_ns: int = Field(ge=0)
    end_timestamp_ns: int = Field(gt=0)
    complete_session: bool
    source_manifest: ArtifactReference
    canonical_control_events: ArtifactReference
    control_validation: ArtifactReference
    campaigns: list[CampaignManifest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_session(self) -> "GovernedSession":
        if self.start_timestamp_ns >= self.end_timestamp_ns:
            raise ValueError("session start must be before session end")
        campaign_ids = [campaign.campaign_id for campaign in self.campaigns]
        if len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("campaign IDs must be unique within a session")
        for campaign in self.campaigns:
            if not self.start_timestamp_ns <= campaign.injection_timestamp_ns < self.end_timestamp_ns:
                raise ValueError("campaign injection timestamp must be inside the complete session")
        return self


class CorpusCoverage(_StrictModel):
    complete_sessions: int
    instruments: list[str]
    distinct_dates: list[date]
    attack_families: list[str]
    seeds_by_attack_family: dict[str, list[int]]


class GovernedCorpusManifest(_StrictModel):
    schema_version: Literal["governed_corpus_v1"] = CORPUS_SCHEMA_VERSION
    corpus_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    generated_at: datetime
    sessions: list[GovernedSession] = Field(min_length=1)
    coverage: CorpusCoverage

    @model_validator(mode="after")
    def validate_unique_sessions(self) -> "GovernedCorpusManifest":
        base_ids = [session.base_session_id for session in self.sessions]
        identities = [
            (session.venue, session.instrument, session.session_date, session.session_id)
            for session in self.sessions
        ]
        if len(base_ids) != len(set(base_ids)):
            raise ValueError("base session IDs must be unique")
        if len(identities) != len(set(identities)):
            raise ValueError("venue/instrument/date/session identities must be unique")
        return self

    def canonical_json(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("generated_at", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def corpus_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class ReviewDecision(_StrictModel):
    reviewer_id: str = Field(min_length=1)
    decision: Literal["clean", "not_clean", "ambiguous"]
    reviewed_at: datetime
    method: str = Field(min_length=1)
    model_outputs_hidden: Literal[True] = True
    evidence: list[ArtifactReference] = Field(min_length=1)


class AdjudicatorDecision(_StrictModel):
    adjudicator_id: str = Field(min_length=1)
    decision: Literal["clean", "not_clean", "ambiguous"]
    decided_at: datetime
    rationale: str = Field(min_length=1)


class CleanWindowAdjudication(_StrictModel):
    schema_version: Literal["clean_window_adjudication_v1"] = ADJUDICATION_SCHEMA_VERSION
    window_id: str = Field(min_length=1)
    base_session_id: str = Field(min_length=1)
    start_timestamp_ns: int = Field(ge=0)
    end_timestamp_ns: int = Field(gt=0)
    status: Literal[
        "unreviewed",
        "candidate_clean",
        "verified_clean",
        "ambiguous",
        "excluded",
        "synthetic_attack",
    ]
    reviewer_decisions: list[ReviewDecision] = Field(default_factory=list)
    adjudicator_decision: AdjudicatorDecision | None = None
    exclusion_reason: str | None = None
    label_source: str | None = None
    transferred_from_control_window_id: str | None = None
    exact_equivalence_validation: ArtifactReference | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "CleanWindowAdjudication":
        if self.start_timestamp_ns >= self.end_timestamp_ns:
            raise ValueError("adjudication window start must be before end")
        reviewer_ids = [decision.reviewer_id for decision in self.reviewer_decisions]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("adjudication reviewers must be independent unique identities")
        if self.status == "excluded" and not self.exclusion_reason:
            raise ValueError("excluded windows require a reason")
        if self.status == "synthetic_attack" and self.label_source != "synthetic_scenario":
            raise ValueError("synthetic attack labels require synthetic_scenario provenance")
        transfer_fields = (
            self.transferred_from_control_window_id,
            self.exact_equivalence_validation,
        )
        if any(value is not None for value in transfer_fields) and not all(
            value is not None for value in transfer_fields
        ):
            raise ValueError("hybrid clean-label transfer requires source window and equivalence validation")
        return self


class CorpusValidationReport(_StrictModel):
    schema_version: Literal["governed_corpus_validation_v1"] = "governed_corpus_validation_v1"
    corpus_id: str
    corpus_hash: str = Field(pattern=SHA256_PATTERN)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    artifact_verification_mode: Literal["local", "metadata_only"]
    verdict: Literal["pass", "fail"]
    checks: dict[str, dict[str, object]]


def build_corpus_manifest(
    *,
    corpus_id: str,
    sessions: list[GovernedSession],
    protocol: GovernedBenchmarkProtocol,
    generated_at: datetime | None = None,
) -> GovernedCorpusManifest:
    coverage = _coverage(sessions)
    return GovernedCorpusManifest(
        corpus_id=corpus_id,
        protocol_id=protocol.protocol_id,
        protocol_hash=protocol.protocol_hash(),
        generated_at=generated_at or datetime.now(timezone.utc),
        sessions=sessions,
        coverage=coverage,
    )


def validate_corpus(
    manifest: GovernedCorpusManifest,
    protocol: GovernedBenchmarkProtocol,
    *,
    artifact_root: Path | None = None,
) -> CorpusValidationReport:
    checks: dict[str, dict[str, object]] = {}

    def check(name: str, passed: bool, **details: object) -> None:
        checks[name] = {"passed": passed, **details}

    declared_coverage = manifest.coverage
    coverage = _coverage(manifest.sessions)
    minimums = protocol.corpus
    check(
        "coverage_consistency",
        declared_coverage == coverage,
        declared=declared_coverage.model_dump(mode="json"),
        recomputed=coverage.model_dump(mode="json"),
    )
    check(
        "protocol_binding",
        manifest.protocol_id == protocol.protocol_id and manifest.protocol_hash == protocol.protocol_hash(),
        expected_protocol_id=protocol.protocol_id,
        expected_protocol_hash=protocol.protocol_hash(),
    )
    check(
        "complete_session_coverage",
        coverage.complete_sessions >= minimums.complete_sessions,
        observed=coverage.complete_sessions,
        required=minimums.complete_sessions,
    )
    check(
        "instrument_coverage",
        len(coverage.instruments) >= minimums.instruments,
        observed=coverage.instruments,
        required=minimums.instruments,
    )
    check(
        "date_coverage",
        len(coverage.distinct_dates) >= minimums.distinct_dates,
        observed=[value.isoformat() for value in coverage.distinct_dates],
        required=minimums.distinct_dates,
    )
    missing_families = sorted(set(minimums.required_attack_families) - set(coverage.attack_families))
    check(
        "attack_family_coverage",
        not minimums.require_all_attack_families or not missing_families,
        observed=coverage.attack_families,
        required=list(minimums.required_attack_families),
        missing=missing_families,
    )
    insufficient_seeds = {
        family: len(coverage.seeds_by_attack_family.get(family, []))
        for family in minimums.required_attack_families
        if len(coverage.seeds_by_attack_family.get(family, [])) < minimums.seeds_per_attack_family
    }
    check(
        "attack_seed_coverage",
        not insufficient_seeds,
        observed=coverage.seeds_by_attack_family,
        minimum_per_family=minimums.seeds_per_attack_family,
        insufficient=insufficient_seeds,
    )
    incomplete = sorted(session.base_session_id for session in manifest.sessions if not session.complete_session)
    check("complete_session_boundaries", not incomplete, incomplete_sessions=incomplete)
    artifact_results = _verify_manifest_artifacts(manifest, artifact_root)
    check(
        "artifact_integrity",
        all(item["verified"] for item in artifact_results),
        artifacts=artifact_results,
        verification_mode="local" if artifact_root is not None else "metadata_only",
    )
    validation_reports = _verify_validation_report_semantics(manifest, artifact_root)
    check(
        "validation_report_semantics",
        all(item["verified"] for item in validation_reports),
        reports=validation_reports,
        verification_mode="local" if artifact_root is not None else "metadata_only",
    )
    verdict = "pass" if all(bool(item["passed"]) for item in checks.values()) else "fail"
    return CorpusValidationReport(
        corpus_id=manifest.corpus_id,
        corpus_hash=manifest.corpus_hash(),
        protocol_hash=protocol.protocol_hash(),
        artifact_verification_mode="local" if artifact_root is not None else "metadata_only",
        verdict=verdict,
        checks=checks,
    )


def validate_adjudications(
    adjudications: list[CleanWindowAdjudication],
    *,
    manifest: GovernedCorpusManifest,
    protocol: GovernedBenchmarkProtocol,
    artifact_root: Path | None = None,
) -> None:
    sessions = {session.base_session_id: session for session in manifest.sessions}
    window_ids: set[str] = set()
    windows_by_id: dict[str, CleanWindowAdjudication] = {}
    supervised: dict[tuple[str, str], list[tuple[int, int, str]]] = defaultdict(list)
    for window in adjudications:
        if window.window_id in window_ids:
            raise ValueError(f"duplicate adjudication window ID: {window.window_id}")
        window_ids.add(window.window_id)
        windows_by_id[window.window_id] = window
        session = sessions.get(window.base_session_id)
        if session is None:
            raise ValueError(f"adjudication references unknown base session: {window.base_session_id}")
        if not (
            session.start_timestamp_ns <= window.start_timestamp_ns
            and window.end_timestamp_ns <= session.end_timestamp_ns
        ):
            raise ValueError(f"adjudication window is outside session boundaries: {window.window_id}")
        if window.status == "verified_clean":
            _validate_verified_clean(window, protocol)
        if window.status in {"verified_clean", "synthetic_attack"}:
            replay_domain = (
                "hybrid"
                if window.status == "synthetic_attack"
                or window.transferred_from_control_window_id is not None
                else "control"
            )
            supervised[(window.base_session_id, replay_domain)].append(
                (window.start_timestamp_ns, window.end_timestamp_ns, window.window_id)
            )
    for window in adjudications:
        source_id = window.transferred_from_control_window_id
        if source_id is None:
            continue
        source = windows_by_id.get(source_id)
        if (
            source is None
            or source.status != "verified_clean"
            or source.transferred_from_control_window_id is not None
            or source.base_session_id != window.base_session_id
            or source.start_timestamp_ns != window.start_timestamp_ns
            or source.end_timestamp_ns != window.end_timestamp_ns
        ):
            raise ValueError(
                f"hybrid clean-label transfer does not match a verified control window: {window.window_id}"
            )
    for (session_id, replay_domain), windows in supervised.items():
        ordered = sorted(windows)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1]:
                raise ValueError(
                    "supervised adjudication windows overlap in "
                    f"{session_id}/{replay_domain}: {previous[2]} and {current[2]}"
                )
    if artifact_root is not None:
        references = [
            reference
            for window in adjudications
            for reference in (
                *[
                    evidence
                    for decision in window.reviewer_decisions
                    for evidence in decision.evidence
                ],
                *(
                    [window.exact_equivalence_validation]
                    if window.exact_equivalence_validation is not None
                    else []
                ),
            )
        ]
        failures = [
            result
            for result in _verify_references(references, artifact_root)
            if not result["verified"]
        ]
        if failures:
            raise ValueError(f"adjudication evidence failed artifact verification: {failures}")
        for window in adjudications:
            if window.transferred_from_control_window_id is None:
                continue
            source = windows_by_id[window.transferred_from_control_window_id]
            session = sessions[window.base_session_id]
            _validate_equivalence_report(
                window,
                source=source,
                session=session,
                root=artifact_root,
            )


def write_corpus_bundle(
    output_dir: Path,
    *,
    manifest: GovernedCorpusManifest,
    validation: CorpusValidationReport,
    adjudications: list[CleanWindowAdjudication],
    overwrite: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "manifest": output_dir / "corpus-manifest.json",
        "validation": output_dir / "corpus-validation.json",
        "adjudications": output_dir / "label-adjudications.jsonl",
    }
    if not overwrite and any(path.exists() for path in targets.values()):
        raise ValueError("corpus output already exists; use a new directory or enable overwrite")
    token = uuid.uuid4().hex
    temporary = {name: path.with_name(f".{path.name}.{token}.tmp") for name, path in targets.items()}
    try:
        _write_json(temporary["manifest"], manifest.model_dump(mode="json"))
        _write_json(temporary["validation"], validation.model_dump(mode="json"))
        temporary["adjudications"].write_text(
            "".join(
                json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
                for item in adjudications
            ),
            encoding="utf-8",
        )
        for name, target in targets.items():
            os.replace(temporary[name], target)
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def load_sessions(path: Path) -> list[GovernedSession]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("session registry input must be a JSON array")
    return [GovernedSession.model_validate(item) for item in payload]


def load_adjudications(path: Path | None) -> list[CleanWindowAdjudication]:
    if path is None:
        return []
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [CleanWindowAdjudication.model_validate(item) for item in records]


def merge_verified_clean_feature_labels(
    base_labels: LabelSpec,
    adjudications: list[CleanWindowAdjudication],
    *,
    base_session_id: str,
    replay_mode: Literal["historical_control", "synthetic", "hybrid"],
) -> LabelSpec:
    """Add only independently verified, replay-appropriate negative windows.

    The caller must first run ``validate_adjudications`` against the bound
    corpus and protocol. Historical controls use original review windows;
    hybrid runs use only windows transferred with exact-equivalence evidence.
    Synthetic runs cannot inherit historical negative labels.
    """
    if base_labels.default_label is not None:
        raise ValueError("governed feature labels cannot use a session-wide default label")
    session_windows = [
        window
        for window in adjudications
        if window.base_session_id == base_session_id and window.status == "verified_clean"
    ]
    if replay_mode == "historical_control":
        eligible = [
            window
            for window in session_windows
            if window.transferred_from_control_window_id is None
        ]
    elif replay_mode == "hybrid":
        eligible = [
            window
            for window in session_windows
            if window.transferred_from_control_window_id is not None
        ]
    else:
        eligible = []
    for window in eligible:
        if window.label_source != "independently_verified_clean":
            raise ValueError(
                f"verified clean feature window has invalid provenance: {window.window_id}"
            )
    negative_windows = [
        LabelWindow(
            label=0,
            attack_family=None,
            label_source="independently_verified_clean",
            provenance_id=window.window_id,
            start_timestamp_ns=window.start_timestamp_ns,
            end_timestamp_ns=window.end_timestamp_ns,
            end_inclusive=False,
        )
        for window in sorted(
            eligible,
            key=lambda item: (
                item.start_timestamp_ns,
                item.end_timestamp_ns,
                item.window_id,
            ),
        )
    ]
    return LabelSpec(
        schema_version=LABEL_SCHEMA_VERSION,
        labels=[*base_labels.labels, *negative_windows],
        default_label=None,
        default_attack_family=None,
        default_label_source=None,
    )


def _validate_verified_clean(
    window: CleanWindowAdjudication,
    protocol: GovernedBenchmarkProtocol,
) -> None:
    decisions = window.reviewer_decisions
    if len(decisions) < protocol.clean_labels.independent_reviewers:
        raise ValueError(f"verified clean window lacks independent reviewers: {window.window_id}")
    observed = {decision.decision for decision in decisions}
    if observed == {"clean"}:
        pass
    elif (
        protocol.clean_labels.conflicts_require_adjudicator
        and window.adjudicator_decision is not None
        and window.adjudicator_decision.decision == "clean"
    ):
        reviewer_ids = {decision.reviewer_id for decision in decisions}
        if window.adjudicator_decision.adjudicator_id in reviewer_ids:
            raise ValueError("adjudicator must be independent from reviewers")
    else:
        raise ValueError(f"verified clean window has unresolved reviewer disagreement: {window.window_id}")
    if window.label_source != "independently_verified_clean":
        raise ValueError("verified clean windows require independently_verified_clean provenance")
    if window.transferred_from_control_window_id and not (
        protocol.clean_labels.transferable_to_hybrid_only_after_exact_equivalence
        and window.exact_equivalence_validation is not None
    ):
        raise ValueError("hybrid clean transfer lacks exact equivalence evidence")


def _coverage(sessions: list[GovernedSession]) -> CorpusCoverage:
    seeds: dict[str, set[int]] = defaultdict(set)
    for session in sessions:
        for campaign in session.campaigns:
            seeds[campaign.attack_family].add(campaign.derived_seed)
    return CorpusCoverage(
        complete_sessions=sum(session.complete_session for session in sessions),
        instruments=sorted({session.instrument for session in sessions}),
        distinct_dates=sorted({session.session_date for session in sessions}),
        attack_families=sorted(seeds),
        seeds_by_attack_family={family: sorted(values) for family, values in sorted(seeds.items())},
    )


def _verify_manifest_artifacts(
    manifest: GovernedCorpusManifest,
    root: Path | None,
) -> list[dict[str, object]]:
    references: list[ArtifactReference] = []
    for session in manifest.sessions:
        references.extend(
            [session.source_manifest, session.canonical_control_events, session.control_validation]
        )
        for campaign in session.campaigns:
            references.extend(
                [campaign.canonical_events, campaign.ground_truth, campaign.validation]
            )
    return _verify_references(references, root)


def _verify_validation_report_semantics(
    manifest: GovernedCorpusManifest,
    root: Path | None,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for session in manifest.sessions:
        references = [
            ("control", None, session.control_validation),
            *[
                ("campaign", campaign.campaign_id, campaign.validation)
                for campaign in session.campaigns
            ],
        ]
        for kind, campaign_id, reference in references:
            result: dict[str, object] = {
                "base_session_id": session.base_session_id,
                "kind": kind,
                "campaign_id": campaign_id,
                "artifact": reference.name,
            }
            if root is None:
                result.update({"verified": True, "verification": "metadata_only"})
                reports.append(result)
                continue
            try:
                path = _resolve_reference(reference, root)
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                payload = None
            required_identity = {
                "base_session_id": session.base_session_id,
                "dataset_id": session.dataset_id,
                "campaign_id": campaign_id,
                "session_start_timestamp_ns": session.start_timestamp_ns,
                "session_end_timestamp_ns": session.end_timestamp_ns,
                "complete_session": True,
            }
            identity_matches = isinstance(payload, dict) and all(
                payload.get(field) == expected
                for field, expected in required_identity.items()
            )
            result.update(
                {
                    "verified": bool(
                        isinstance(payload, dict)
                        and payload.get("verdict") == "pass"
                        and identity_matches
                    ),
                    "verification": "parsed_pass_verdict_and_identity",
                }
            )
            reports.append(result)
    return reports


def _validate_equivalence_report(
    window: CleanWindowAdjudication,
    *,
    source: CleanWindowAdjudication,
    session: GovernedSession,
    root: Path,
) -> None:
    reference = window.exact_equivalence_validation
    if reference is None:
        raise ValueError("hybrid clean transfer lacks exact equivalence evidence")
    path = _resolve_reference(reference, root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exception:
        raise ValueError("hybrid clean equivalence evidence is not valid JSON") from exception
    required_identity = {
        "schema_version": "governed_clean_window_equivalence_v1",
        "verdict": "pass",
        "base_session_id": session.base_session_id,
        "dataset_id": session.dataset_id,
        "source_control_window_id": source.window_id,
        "transferred_window_id": window.window_id,
        "window_start_timestamp_ns": window.start_timestamp_ns,
        "window_end_timestamp_ns": window.end_timestamp_ns,
        "control_events_sha256": session.canonical_control_events.sha256,
    }
    if not isinstance(payload, dict) or any(
        payload.get(name) != expected
        for name, expected in required_identity.items()
    ):
        raise ValueError("hybrid clean equivalence evidence identity or verdict is invalid")
    campaign_id = payload.get("campaign_id")
    campaigns = {item.campaign_id: item for item in session.campaigns}
    campaign = campaigns.get(campaign_id)
    if (
        campaign is None
        or payload.get("hybrid_events_sha256") != campaign.canonical_events.sha256
        or payload.get("outside_causal_neighbourhood_equivalent") is not True
        or payload.get("exact_book_match_rate") != 1.0
    ):
        raise ValueError("hybrid clean equivalence evidence is not bound to a passing campaign")
    causal_start = payload.get("causal_start_timestamp_ns")
    causal_end = payload.get("causal_end_timestamp_ns")
    if (
        not isinstance(causal_start, int)
        or not isinstance(causal_end, int)
        or causal_start > causal_end
        or not (
            window.end_timestamp_ns <= causal_start
            or window.start_timestamp_ns > causal_end
        )
    ):
        raise ValueError("hybrid clean window intersects the attack causal neighbourhood")


def _verify_references(
    references: list[ArtifactReference],
    root: Path | None,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    duplicate_names = Counter((reference.uri, reference.sha256) for reference in references)
    for reference in references:
        result: dict[str, object] = {
            "name": reference.name,
            "uri": reference.uri,
            "sha256": reference.sha256,
            "reference_count": duplicate_names[(reference.uri, reference.sha256)],
        }
        if root is None:
            result["verified"] = True
            result["verification"] = "digest_metadata_valid"
        else:
            path = (root / reference.uri).resolve()
            inside_root = path == root.resolve() or root.resolve() in path.parents
            exists = inside_root and path.is_file()
            actual_size = path.stat().st_size if exists else None
            actual_hash = _sha256(path) if exists else None
            result.update(
                {
                    "verified": (
                        exists
                        and actual_size == reference.size_bytes
                        and actual_hash == reference.sha256
                    ),
                    "verification": "local_file",
                    "actual_size_bytes": actual_size,
                    "actual_sha256": actual_hash,
                }
            )
        results.append(result)
    return results


def _resolve_reference(reference: ArtifactReference, root: Path) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / reference.uri).resolve()
    if path != resolved_root and resolved_root not in path.parents:
        raise ValueError(f"artifact escapes configured root: {reference.name}")
    if not path.is_file():
        raise ValueError(f"artifact is missing: {reference.name}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
