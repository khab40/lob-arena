from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.corpus.governance import CleanWindowAdjudication
from app.evaluation.canonical_bundle import (
    CanonicalEvaluationInput,
    load_canonical_evaluation_input,
)
from app.evaluation.ground_truth import binary_classification_metrics


@dataclass(frozen=True)
class AttackWindow:
    campaign_id: str
    attack_family: str
    start_timestamp_ns: int
    end_timestamp_ns: int
    first_benefit_timestamp_ns: int | None = None

    def __post_init__(self) -> None:
        if self.start_timestamp_ns > self.end_timestamp_ns:
            raise ValueError("attack window start must not exceed end")
        if (
            self.first_benefit_timestamp_ns is not None
            and self.first_benefit_timestamp_ns < self.start_timestamp_ns
        ):
            raise ValueError("realized benefit cannot precede attack start")


@dataclass(frozen=True)
class CleanWindow:
    window_id: str
    start_timestamp_ns: int
    end_timestamp_ns: int

    def __post_init__(self) -> None:
        if self.start_timestamp_ns >= self.end_timestamp_ns:
            raise ValueError("clean window start must be before end")


@dataclass(frozen=True)
class AlertObservation:
    alert_id: str
    detector: str
    timestamp_ns: int

    def __post_init__(self) -> None:
        if not self.alert_id or not self.detector or self.timestamp_ns < 0:
            raise ValueError("alerts require an identity, detector, and non-negative timestamp")


@dataclass(frozen=True)
class GovernedSessionUnit:
    base_session_id: str
    instrument: str
    canonical_event_count: int
    evaluable_event_count: int
    attacks: tuple[AttackWindow, ...]
    clean_windows: tuple[CleanWindow, ...]
    alerts: tuple[AlertObservation, ...]
    regimes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.canonical_event_count < 1:
            raise ValueError("session unit requires canonical events")
        if not 0 <= self.evaluable_event_count <= self.canonical_event_count:
            raise ValueError("evaluable event count must be within the canonical session")
        _validate_non_overlapping_windows(self.attacks, self.clean_windows)


@dataclass(frozen=True)
class SessionMetricComponents:
    base_session_id: str
    instrument: str
    regimes: dict[str, str]
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    evaluable_event_count: int
    raw_false_alert_count: int
    false_alert_cluster_count: int
    raw_evaluable_alert_count: int
    evaluable_alert_cluster_count: int
    benefit_eligible_attack_count: int
    detected_before_benefit_count: int
    detection_latencies_ns: tuple[int, ...]


def evaluate_governed_session(
    unit: GovernedSessionUnit,
    *,
    alert_deduplication_window_ns: int,
    alert_matching_horizon_ns: int,
) -> SessionMetricComponents:
    if min(alert_deduplication_window_ns, alert_matching_horizon_ns) < 0:
        raise ValueError("alert matching and deduplication horizons must be non-negative")
    attack_alerts: dict[str, list[AlertObservation]] = {
        attack.campaign_id: [] for attack in unit.attacks
    }
    clean_alerts: dict[str, list[AlertObservation]] = {
        window.window_id: [] for window in unit.clean_windows
    }
    for alert in sorted(unit.alerts, key=lambda item: (item.timestamp_ns, item.detector, item.alert_id)):
        matching_attacks = [
            attack
            for attack in unit.attacks
            if attack.start_timestamp_ns
            <= alert.timestamp_ns
            <= attack.end_timestamp_ns + alert_matching_horizon_ns
        ]
        if matching_attacks:
            attack = min(
                matching_attacks,
                key=lambda item: (
                    abs(alert.timestamp_ns - item.start_timestamp_ns),
                    item.start_timestamp_ns,
                    item.campaign_id,
                ),
            )
            attack_alerts[attack.campaign_id].append(alert)
            continue
        matching_clean = [
            window
            for window in unit.clean_windows
            if window.start_timestamp_ns <= alert.timestamp_ns < window.end_timestamp_ns
        ]
        if matching_clean:
            window = min(matching_clean, key=lambda item: (item.start_timestamp_ns, item.window_id))
            clean_alerts[window.window_id].append(alert)

    detected_attacks = 0
    benefit_eligible = 0
    before_benefit = 0
    latencies: list[int] = []
    attack_clusters = 0
    raw_attack_alerts = 0
    for attack in unit.attacks:
        alerts = attack_alerts[attack.campaign_id]
        clusters = _cluster_alerts(alerts, alert_deduplication_window_ns)
        raw_attack_alerts += len(alerts)
        attack_clusters += len(clusters)
        if clusters:
            detected_attacks += 1
            first_alert_ns = clusters[0][0].timestamp_ns
            latencies.append(first_alert_ns - attack.start_timestamp_ns)
        if attack.first_benefit_timestamp_ns is not None:
            benefit_eligible += 1
            if clusters and clusters[0][0].timestamp_ns <= attack.first_benefit_timestamp_ns:
                before_benefit += 1

    false_positive_windows = 0
    false_alert_clusters = 0
    raw_false_alerts = 0
    for window in unit.clean_windows:
        alerts = clean_alerts[window.window_id]
        clusters = _cluster_alerts(alerts, alert_deduplication_window_ns)
        raw_false_alerts += len(alerts)
        false_alert_clusters += len(clusters)
        false_positive_windows += bool(clusters)

    return SessionMetricComponents(
        base_session_id=unit.base_session_id,
        instrument=unit.instrument,
        regimes=dict(sorted(unit.regimes.items())),
        true_positive=detected_attacks,
        false_positive=false_positive_windows,
        false_negative=len(unit.attacks) - detected_attacks,
        true_negative=len(unit.clean_windows) - false_positive_windows,
        evaluable_event_count=unit.evaluable_event_count,
        raw_false_alert_count=raw_false_alerts,
        false_alert_cluster_count=false_alert_clusters,
        raw_evaluable_alert_count=raw_attack_alerts + raw_false_alerts,
        evaluable_alert_cluster_count=attack_clusters + false_alert_clusters,
        benefit_eligible_attack_count=benefit_eligible,
        detected_before_benefit_count=before_benefit,
        detection_latencies_ns=tuple(latencies),
    )


def aggregate_governed_metrics(
    components: list[SessionMetricComponents],
) -> dict[str, Any]:
    if not components:
        raise ValueError("governed metric aggregation requires at least one session")
    totals = {
        name: sum(getattr(item, name) for item in components)
        for name in (
            "true_positive",
            "false_positive",
            "false_negative",
            "true_negative",
            "evaluable_event_count",
            "raw_false_alert_count",
            "false_alert_cluster_count",
            "raw_evaluable_alert_count",
            "evaluable_alert_cluster_count",
            "benefit_eligible_attack_count",
            "detected_before_benefit_count",
        )
    }
    classification = binary_classification_metrics(
        tp=totals["true_positive"],
        fp=totals["false_positive"],
        fn=totals["false_negative"],
        tn=totals["true_negative"],
    )
    latencies = sorted(
        latency
        for item in components
        for latency in item.detection_latencies_ns
    )
    event_denominator = totals["evaluable_event_count"]
    raw_alerts = totals["raw_evaluable_alert_count"]
    clusters = totals["evaluable_alert_cluster_count"]
    benefit_denominator = totals["benefit_eligible_attack_count"]
    return {
        "schema_version": "governed_operational_metrics_v1",
        **classification,
        "session_count": len(components),
        "evaluable_event_count": event_denominator,
        "attack_count": totals["true_positive"] + totals["false_negative"],
        "verified_clean_window_count": totals["false_positive"] + totals["true_negative"],
        "false_alert_cluster_count": totals["false_alert_cluster_count"],
        "raw_false_alert_count": totals["raw_false_alert_count"],
        "false_alerts_per_million_events": _rate_per_million(
            totals["false_alert_cluster_count"], event_denominator
        ),
        "raw_false_alerts_per_million_events": _rate_per_million(
            totals["raw_false_alert_count"], event_denominator
        ),
        "attack_level_recall": classification["recall"],
        "benefit_eligible_attack_count": benefit_denominator,
        "detected_before_benefit_count": totals["detected_before_benefit_count"],
        "detection_before_benefit_rate": (
            round(totals["detected_before_benefit_count"] / benefit_denominator, 6)
            if benefit_denominator
            else None
        ),
        "raw_evaluable_alert_count": raw_alerts,
        "evaluable_alert_cluster_count": clusters,
        "duplicate_alert_load": round(raw_alerts / clusters, 6) if clusters else None,
        "duplicate_alert_fraction": (
            round((raw_alerts - clusters) / raw_alerts, 6) if raw_alerts else None
        ),
        "detection_latency_ns": _latency_summary(latencies),
    }


def combine_session_components(
    components: list[SessionMetricComponents],
    *,
    base_session_id: str,
    instrument: str,
    regimes: dict[str, str],
) -> SessionMetricComponents:
    if not components:
        raise ValueError("session component combination requires at least one replay")
    if any(item.base_session_id != base_session_id for item in components):
        raise ValueError("combined replay components must share one base session")
    return SessionMetricComponents(
        base_session_id=base_session_id,
        instrument=instrument,
        regimes=dict(sorted(regimes.items())),
        true_positive=sum(item.true_positive for item in components),
        false_positive=sum(item.false_positive for item in components),
        false_negative=sum(item.false_negative for item in components),
        true_negative=sum(item.true_negative for item in components),
        evaluable_event_count=sum(item.evaluable_event_count for item in components),
        raw_false_alert_count=sum(item.raw_false_alert_count for item in components),
        false_alert_cluster_count=sum(item.false_alert_cluster_count for item in components),
        raw_evaluable_alert_count=sum(item.raw_evaluable_alert_count for item in components),
        evaluable_alert_cluster_count=sum(item.evaluable_alert_cluster_count for item in components),
        benefit_eligible_attack_count=sum(item.benefit_eligible_attack_count for item in components),
        detected_before_benefit_count=sum(item.detected_before_benefit_count for item in components),
        detection_latencies_ns=tuple(
            latency
            for item in components
            for latency in item.detection_latencies_ns
        ),
    )


def governed_unit_from_canonical_bundle(
    replay_manifest: Path,
    *,
    verified_clean_windows: list[CleanWindowAdjudication],
    artifact_root: Path | None = None,
    regimes: dict[str, str] | None = None,
) -> GovernedSessionUnit:
    replay = load_canonical_evaluation_input(replay_manifest, artifact_root=artifact_root)
    manifest = replay.manifest
    for window in verified_clean_windows:
        if window.base_session_id != manifest.base_session_id or window.status != "verified_clean":
            raise ValueError("canonical evaluation accepts only verified clean windows from its base session")
    timestamp_by_tick: dict[int, int] = {}
    event_timestamps: list[int] = []
    for event in replay.events:
        timestamp = event.exchange_timestamp_ns
        if timestamp is None:
            timestamp = event.received_timestamp_ns
        if timestamp is None:
            raise ValueError("canonical evaluation events require timestamps")
        event_timestamps.append(timestamp)
        if event.tick is not None:
            timestamp_by_tick.setdefault(event.tick, timestamp)
    truth_records = _read_ground_truth_records(
        replay_manifest,
        replay,
        artifact_root=artifact_root,
    )
    attacks = tuple(
        _attack_window(record, timestamp_by_tick, manifest.campaign_id)
        for record in truth_records
    )
    clean = tuple(
        CleanWindow(
            window_id=window.window_id,
            start_timestamp_ns=window.start_timestamp_ns,
            end_timestamp_ns=window.end_timestamp_ns,
        )
        for window in verified_clean_windows
    )
    alerts = tuple(
        _alert_observation(record, timestamp_by_tick)
        for record in replay.alerts
    )
    evaluable_count = sum(
        _timestamp_is_evaluable(timestamp, attacks, clean)
        for timestamp in event_timestamps
    )
    return GovernedSessionUnit(
        base_session_id=manifest.base_session_id,
        instrument=manifest.instrument,
        canonical_event_count=len(replay.events),
        evaluable_event_count=evaluable_count,
        attacks=attacks,
        clean_windows=clean,
        alerts=alerts,
        regimes=regimes or {},
    )


def _cluster_alerts(
    alerts: list[AlertObservation],
    window_ns: int,
) -> list[list[AlertObservation]]:
    clusters: list[list[AlertObservation]] = []
    for alert in sorted(alerts, key=lambda item: (item.detector, item.timestamp_ns, item.alert_id)):
        if (
            not clusters
            or clusters[-1][-1].detector != alert.detector
            or alert.timestamp_ns - clusters[-1][-1].timestamp_ns > window_ns
        ):
            clusters.append([alert])
        else:
            clusters[-1].append(alert)
    clusters.sort(key=lambda cluster: (cluster[0].timestamp_ns, cluster[0].detector))
    return clusters


def _validate_non_overlapping_windows(
    attacks: tuple[AttackWindow, ...],
    clean: tuple[CleanWindow, ...],
) -> None:
    windows = [
        (window.start_timestamp_ns, window.end_timestamp_ns, f"attack:{window.campaign_id}")
        for window in attacks
    ] + [
        (window.start_timestamp_ns, window.end_timestamp_ns, f"clean:{window.window_id}")
        for window in clean
    ]
    windows.sort()
    for previous, current in zip(windows, windows[1:], strict=False):
        if current[0] <= previous[1]:
            raise ValueError(f"governed evaluation windows overlap: {previous[2]} and {current[2]}")


def _read_ground_truth_records(
    manifest_path: Path,
    replay: CanonicalEvaluationInput,
    *,
    artifact_root: Path | None,
) -> list[dict[str, Any]]:
    reference = replay.manifest.ground_truth
    if reference is None:
        return []
    path = ((artifact_root or manifest_path.parent) / reference.uri).resolve()
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        truth = payload.get("ground_truth", payload)
        if truth is not None:
            records.append(truth)
    return records


def _attack_window(
    truth: dict[str, Any],
    timestamp_by_tick: dict[int, int],
    fallback_campaign_id: str | None,
) -> AttackWindow:
    start = truth.get("start_timestamp_ns")
    end = truth.get("end_timestamp_ns")
    if start is None or end is None:
        start_tick = truth.get("start_tick")
        end_tick = truth.get("end_tick")
        if start_tick not in timestamp_by_tick or end_tick not in timestamp_by_tick:
            raise ValueError("ground truth tick bounds cannot be mapped to canonical Java timestamps")
        start = timestamp_by_tick[start_tick]
        end = timestamp_by_tick[end_tick]
    benefit = truth.get("first_benefit_timestamp_ns")
    if benefit is None and truth.get("first_benefit_tick") is not None:
        benefit = timestamp_by_tick.get(truth["first_benefit_tick"])
        if benefit is None:
            raise ValueError("realized benefit tick cannot be mapped to canonical Java timestamps")
    campaign_id = truth.get("campaign_id") or fallback_campaign_id
    if not campaign_id:
        raise ValueError("canonical attack ground truth requires campaign identity")
    family = truth.get("scenario_family")
    if not isinstance(family, str) or not family:
        raise ValueError("canonical attack ground truth requires scenario family")
    return AttackWindow(
        campaign_id=str(campaign_id),
        attack_family=family,
        start_timestamp_ns=int(start),
        end_timestamp_ns=int(end),
        first_benefit_timestamp_ns=int(benefit) if benefit is not None else None,
    )


def _alert_observation(
    record: dict[str, Any],
    timestamp_by_tick: dict[int, int],
) -> AlertObservation:
    timestamp = record.get("timestamp_ns")
    if timestamp is None:
        tick = record.get("tick")
        timestamp = timestamp_by_tick.get(tick)
    if timestamp is None:
        raise ValueError("canonical alert requires timestamp_ns or a mappable tick")
    alert_id = record.get("alert_id") or record.get("incident_id")
    detector = record.get("detector") or record.get("detector_id")
    if not isinstance(alert_id, str) or not isinstance(detector, str):
        raise ValueError("canonical alert requires alert and detector identities")
    return AlertObservation(alert_id=alert_id, detector=detector, timestamp_ns=int(timestamp))


def _timestamp_is_evaluable(
    timestamp: int,
    attacks: tuple[AttackWindow, ...],
    clean: tuple[CleanWindow, ...],
) -> bool:
    return any(
        window.start_timestamp_ns <= timestamp <= window.end_timestamp_ns
        for window in attacks
    ) or any(
        window.start_timestamp_ns <= timestamp < window.end_timestamp_ns
        for window in clean
    )


def _rate_per_million(numerator: int, denominator: int) -> float | None:
    return round(numerator * 1_000_000 / denominator, 6) if denominator else None


def _latency_summary(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "p50": None, "p90": None, "max": None}
    return {
        "count": len(values),
        "min": values[0],
        "mean": sum(values) / len(values),
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "max": values[-1],
    }


def _percentile(values: list[int], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight
