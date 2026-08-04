from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


BOOK_TRACE_METRICS = ("spread", "depth_top_n", "imbalance", "level_count")
EVENT_FLOW_TRACE_METRICS = ("message_count", "add_count", "cancel_count", "execute_count")
TRACE_METRICS = (*BOOK_TRACE_METRICS, *EVENT_FLOW_TRACE_METRICS)


def validate_normalized_lobster(dataset_dir: Path) -> dict[str, Any]:
    """Validate the immutable normalized LOBSTER pair and its provenance."""
    import pyarrow.parquet as pq

    root = dataset_dir.resolve()
    manifest_path = root / "manifest.json"
    events_path = root / "events.parquet"
    books_path = root / "book_snapshots.parquet"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = pq.read_table(events_path).to_pylist()
    books = pq.read_table(books_path).to_pylist()
    checks: dict[str, dict[str, Any]] = {}

    event_keys = [(int(row["source_sequence"]), int(row["timestamp_ns_since_midnight"])) for row in events]
    book_keys = [(int(row["source_sequence"]), int(row["timestamp_ns_since_midnight"])) for row in books]
    _check(
        checks,
        "message_orderbook_synchronization",
        event_keys == book_keys and len(events) == len(books),
        event_rows=len(events),
        orderbook_rows=len(books),
    )
    sequences = [sequence for sequence, _ in event_keys]
    timestamps = [timestamp for _, timestamp in event_keys]
    _check(
        checks,
        "sequence_integrity",
        bool(sequences) and len(sequences) == len(set(sequences)) and sequences == sorted(sequences),
        first_sequence=sequences[0] if sequences else None,
        last_sequence=sequences[-1] if sequences else None,
    )
    _check(
        checks,
        "timestamp_integrity",
        bool(timestamps) and timestamps == sorted(timestamps),
        first_timestamp_ns=timestamps[0] if timestamps else None,
        last_timestamp_ns=timestamps[-1] if timestamps else None,
    )
    start_ns = int(manifest["start_time_ms"]) * 1_000_000
    end_ns = int(manifest["end_time_ms"]) * 1_000_000
    _check(
        checks,
        "trading_session_boundaries",
        bool(timestamps) and all(start_ns <= value < end_ns for value in timestamps),
        start_ns=start_ns,
        end_ns_exclusive=end_ns,
    )

    invalid_books: list[int] = []
    crossed_books: list[int] = []
    for index, row in enumerate(books):
        asks = row.get("asks") or []
        bids = row.get("bids") or []
        ask_prices = [int(level["price_x10000"]) for level in asks]
        bid_prices = [int(level["price_x10000"]) for level in bids]
        quantities = [int(level["quantity"]) for level in [*asks, *bids]]
        if (
            ask_prices != sorted(ask_prices)
            or bid_prices != sorted(bid_prices, reverse=True)
            or len(ask_prices) != len(set(ask_prices))
            or len(bid_prices) != len(set(bid_prices))
            or any(quantity <= 0 for quantity in quantities)
        ):
            invalid_books.append(index + 1)
        if ask_prices and bid_prices and bid_prices[0] >= ask_prices[0]:
            crossed_books.append(index + 1)
    _check(
        checks,
        "valid_uncrossed_books",
        not invalid_books and not crossed_books,
        invalid_rows=invalid_books[:20],
        locked_or_crossed_rows=crossed_books[:20],
    )

    output_hashes = {
        item["name"]: item["sha256"] for item in manifest.get("output_files", []) if "name" in item and "sha256" in item
    }
    actual_hashes = {
        "events.parquet": _sha256(events_path),
        "book_snapshots.parquet": _sha256(books_path),
    }
    _check(
        checks,
        "dataset_hashes",
        all(output_hashes.get(name) == digest for name, digest in actual_hashes.items()),
        expected=output_hashes,
        actual=actual_hashes,
    )
    source_files = manifest.get("source_files", [])
    provenance_ok = (
        manifest.get("source_type") == "lobster"
        and bool(manifest.get("dataset_id"))
        and bool(manifest.get("symbol"))
        and bool(manifest.get("trade_date"))
        and len(source_files) == 2
        and all(_valid_sha256(item.get("sha256")) for item in source_files)
    )
    _check(
        checks,
        "provenance",
        provenance_ok,
        dataset_id=manifest.get("dataset_id"),
        source_files=source_files,
    )
    _check(
        checks,
        "manifest_row_count",
        manifest.get("row_count") == len(events) == len(books),
        manifest_rows=manifest.get("row_count"),
        observed_rows=len(events),
    )
    return {
        "schema_version": "normalized_lobster_validation_v1",
        "dataset_id": manifest.get("dataset_id"),
        "verdict": _verdict(checks),
        "checks": checks,
    }


def build_hybrid_validation(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate replay invariants and causal locality from paired control/hybrid traces."""
    control = raw["control"]
    hybrid = raw["hybrid"]
    checks: dict[str, dict[str, Any]] = {}

    control_integrity = control.get("source_integrity") or {}
    hybrid_integrity = hybrid.get("source_integrity") or {}
    source_row_count = control.get("source_row_count")
    control_output_hashes = control_integrity.get("output_sha256") or {}
    source_hash = raw.get("events_sha256")
    snapshot_hash = control.get("historical_snapshot_stream_hash")
    same_source = (
        isinstance(source_row_count, int)
        and source_row_count > 0
        and control.get("source_rows_replayed") == hybrid.get("source_rows_replayed")
        and control.get("source_rows_replayed") == source_row_count
        and source_row_count == hybrid.get("source_row_count")
        and control.get("historical_source_sequences") == source_row_count
        and hybrid.get("historical_source_sequences") == source_row_count
        and control.get("events_sha256") == hybrid.get("events_sha256") == source_hash
        and _valid_sha256(source_hash)
        and snapshot_hash == hybrid.get("historical_snapshot_stream_hash")
        and _valid_sha256(snapshot_hash)
        and control_integrity.get("validated") is True
        and hybrid_integrity.get("validated") is True
        and control_integrity.get("format")
        in {"lobster_parquet_v1", "itch_parquet_v1", "canonical_csv_v1"}
        and control_integrity.get("format") == hybrid_integrity.get("format")
        and control_integrity.get("row_count") == source_row_count
        and hybrid_integrity.get("row_count") == source_row_count
        and control_integrity.get("paired_rows") == source_row_count
        and hybrid_integrity.get("paired_rows") == source_row_count
        and bool(control_output_hashes)
        and all(_valid_sha256(value) for value in control_output_hashes.values())
        and control_output_hashes == hybrid_integrity.get("output_sha256")
        and all(
            control_integrity.get(field) == hybrid_integrity.get(field)
            for field in (
                "source_type",
                "venue",
                "parser_version",
                "source_stream_sha256",
                "parser_config_sha256",
                "filters",
                "message_counts",
                "truncation_limits",
            )
        )
    )
    if control_integrity.get("format") == "itch_parquet_v1":
        same_source = bool(
            same_source
            and control_integrity.get("source_type") == "nasdaq_itch"
            and control_integrity.get("venue") == "XNAS"
            and _valid_sha256(control_integrity.get("source_stream_sha256"))
            and _valid_sha256(control_integrity.get("parser_config_sha256"))
            and isinstance(control_integrity.get("message_counts"), dict)
        )
    _check(
        checks,
        "historical_source_immutability",
        same_source,
        source_rows=control.get("source_rows_replayed"),
        source_sha256=raw.get("events_sha256"),
        snapshot_stream_hash=control.get("historical_snapshot_stream_hash"),
        verified_source_integrity=control_integrity,
    )

    control_trace = _trace_by_tick(control.get("validation_trace", []))
    hybrid_trace = _trace_by_tick(hybrid.get("validation_trace", []))
    paired_ticks = sorted(set(control_trace) & set(hybrid_trace))
    _check(
        checks,
        "trace_alignment",
        bool(paired_ticks) and set(control_trace) == set(hybrid_trace),
        control_ticks=sorted(control_trace),
        hybrid_ticks=sorted(hybrid_trace),
    )

    label = hybrid.get("ground_truth") or {}
    scheduled = raw.get("scheduled_injection") is True
    control_schedule = control.get("injection_schedule")
    hybrid_schedule = hybrid.get("injection_schedule")
    schedule_valid = not scheduled or bool(
        isinstance(control_schedule, dict)
        and isinstance(hybrid_schedule, dict)
        and control_schedule == hybrid_schedule
        and hybrid_schedule.get("triggered") is True
        and _valid_sha256(hybrid_schedule.get("schedule_sha256"))
        and hybrid_schedule.get("actual_source_sequence") == label.get("trigger_source_sequence")
        and hybrid_schedule.get("actual_timestamp_ns") == label.get("trigger_timestamp_ns")
        and label.get("start_exchange_timestamp_ns") == label.get("trigger_timestamp_ns")
        and _valid_sha256(label.get("schedule_sha256"))
        and label.get("schedule_sha256") == hybrid_schedule.get("schedule_sha256")
        and label.get("parameters") == hybrid_schedule.get("parameters")
    )
    _check(
        checks,
        "deterministic_injection_schedule",
        schedule_valid,
        scheduled=scheduled,
        control_schedule=control_schedule,
        hybrid_schedule=hybrid_schedule,
    )
    start_tick = int(label.get("start_tick", 0))
    end_tick = int(label.get("end_tick", -1))
    before = [tick for tick in paired_ticks if tick < start_tick]
    during = [tick for tick in paired_ticks if start_tick <= tick <= end_tick]
    after = [tick for tick in paired_ticks if tick > end_tick]
    outside = [*before, *after]

    phases = {
        "before": _compare_phase(before, control_trace, hybrid_trace),
        "during": _compare_phase(during, control_trace, hybrid_trace),
        "after": _compare_phase(after, control_trace, hybrid_trace),
        "outside_causal_neighbourhood": _compare_phase(outside, control_trace, hybrid_trace),
    }
    outside_result = phases["outside_causal_neighbourhood"]
    _check(
        checks,
        "outside_causal_neighbourhood_equivalence",
        bool(outside)
        and bool(outside_result["statistically_equivalent"])
        and outside_result["exact_book_match_rate"] == 1.0,
        causal_neighbourhood={"start_tick": start_tick, "end_tick": end_tick},
        before_ticks=before,
        after_ticks=after,
        result=outside_result,
    )
    during_result = phases["during"]
    event_flow_divergence = any(
        not during_result["metrics"].get(metric, {}).get("equivalent", True) for metric in EVENT_FLOW_TRACE_METRICS
    )
    book_divergence = during_result["exact_book_match_rate"] < 1.0 if during else False
    _check(
        checks,
        "intended_market_impact",
        bool(during) and (book_divergence or event_flow_divergence),
        during_ticks=during,
        book_divergence=book_divergence,
        event_flow_divergence=event_flow_divergence,
        result=during_result,
    )

    synthetic_events = hybrid.get("synthetic_events", [])
    lifecycle = _synthetic_lifecycle(synthetic_events, set(label.get("order_ids", [])))
    _check(
        checks,
        "injected_order_lifecycle",
        lifecycle["valid"],
        **lifecycle,
    )
    event_ticks = [
        int(event["tick"]) for event in synthetic_events if event.get("scenario_id") == label.get("scenario_id")
    ]
    _check(
        checks,
        "attack_localisation",
        bool(event_ticks) and all(start_tick <= tick <= end_tick for tick in event_ticks),
        labelled_window={"start_tick": start_tick, "end_tick": end_tick},
        observed_event_ticks=sorted(set(event_ticks)),
    )
    _check(
        checks,
        "ground_truth_isolation",
        control.get("ground_truth") is None
        and not control.get("synthetic_events")
        and label.get("source") == "synthetic_scenario"
        and all(str(value).startswith("SYN:") for value in label.get("order_ids", []))
        and all(
            event.get("source") == "simulation"
            and event.get("scenario_id") == label.get("scenario_id")
            for event in synthetic_events
        ),
        control_ground_truth=control.get("ground_truth"),
        hybrid_label_source=label.get("source"),
    )
    determinism = raw.get("determinism", {})
    determinism_passed = bool(determinism) and all(
        determinism.get(name) is True
        for name in (
            "control_stream_match",
            "hybrid_stream_match",
            "control_trace_match",
            "hybrid_trace_match",
            "historical_snapshot_match",
        )
    )
    _check(checks, "deterministic_replay", determinism_passed, **determinism)

    return {
        "schema_version": "hybrid_dataset_validation_v1",
        "dataset_id": raw.get("dataset_id"),
        "master_seed": raw.get("master_seed"),
        "verdict": _verdict(checks),
        "causal_neighbourhood": {
            "definition": "synthetic ground-truth attack window, inclusive",
            "start_tick": start_tick,
            "end_tick": end_tick,
            "phases": phases,
        },
        "checks": checks,
    }


def _synthetic_lifecycle(
    events: Iterable[dict[str, Any]],
    labelled_order_ids: set[str],
) -> dict[str, Any]:
    active: dict[str, float] = {}
    added: set[str] = set()
    cancelled: set[str] = set()
    executed_quantity: dict[str, float] = defaultdict(float)
    errors: list[str] = []
    for event in sorted(events, key=lambda item: int(item.get("sequence", 0))):
        event_type = event.get("event_type")
        order_id = event.get("order_id")
        if event_type == "execute":
            quantity = float(event.get("quantity", 0))
            if quantity <= 0:
                errors.append("execution quantity must be positive")
            for key, remaining_key in (
                ("aggressor_order_id", "aggressor_remaining_quantity"),
                ("resting_order_id", "resting_remaining_quantity"),
            ):
                candidate = str(event.get(key, ""))
                if candidate in labelled_order_ids:
                    if candidate not in active:
                        errors.append(f"execution before add or after terminal event: {candidate}")
                        continue
                    if quantity > active[candidate]:
                        errors.append(f"execution over-consumes synthetic order: {candidate}")
                        continue
                    executed_quantity[candidate] += quantity
                    remaining = float(event.get(remaining_key, active[candidate] - quantity))
                    if remaining < 0 or remaining > active[candidate] - quantity:
                        errors.append(f"invalid execution remainder: {candidate}")
                    elif remaining == 0:
                        active.pop(candidate)
                    else:
                        active[candidate] = remaining
            continue
        if not isinstance(order_id, str) or not order_id.startswith("SYN:"):
            errors.append("synthetic mutation has an invalid order namespace")
            continue
        quantity = float(event.get("quantity", 0))
        if event_type == "add":
            if order_id in active:
                errors.append(f"duplicate active add: {order_id}")
            if quantity <= 0:
                errors.append(f"non-positive add: {order_id}")
            active[order_id] = quantity
            added.add(order_id)
        elif event_type == "modify":
            if order_id not in active:
                errors.append(f"modify before add: {order_id}")
            if quantity <= 0:
                errors.append(f"non-positive modify: {order_id}")
            active[order_id] = quantity
        elif event_type == "cancel":
            if order_id not in active:
                errors.append(f"cancel before add or duplicate cancel: {order_id}")
            else:
                active.pop(order_id)
            cancelled.add(order_id)
        else:
            errors.append(f"unsupported synthetic event type: {event_type}")
    missing = sorted(labelled_order_ids - added)
    unexpected = sorted(added - labelled_order_ids)
    if missing:
        errors.append(f"labelled orders not added: {missing}")
    if unexpected:
        errors.append(f"unlabelled synthetic orders added: {unexpected}")
    terminal = {
        order_id: (
            "cancelled"
            if order_id in cancelled
            else "executed"
            if executed_quantity.get(order_id, 0) > 0 and order_id not in active
            else "active"
        )
        for order_id in sorted(added)
    }
    return {
        "valid": not errors,
        "errors": errors,
        "added_order_count": len(added),
        "cancelled_order_count": len(cancelled),
        "execution_quantity_by_order": dict(sorted(executed_quantity.items())),
        "terminal_state_by_order": terminal,
    }


def _compare_phase(
    ticks: list[int],
    control: dict[int, dict[str, Any]],
    hybrid: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if not ticks:
        return {
            "tick_count": 0,
            "exact_book_match_rate": None,
            "statistically_equivalent": None,
            "metrics": {},
        }
    exact_matches = sum(control[tick].get("book_hash") == hybrid[tick].get("book_hash") for tick in ticks)
    metrics = {
        metric: _paired_equivalence(
            [float(control[tick].get(metric, 0.0)) for tick in ticks],
            [float(hybrid[tick].get(metric, 0.0)) for tick in ticks],
            absolute_margin=0.01 if metric == "imbalance" else 0.0,
            relative_margin=0.01,
        )
        for metric in TRACE_METRICS
    }
    return {
        "tick_count": len(ticks),
        "exact_book_match_rate": exact_matches / len(ticks),
        "statistically_equivalent": all(item["equivalent"] for item in metrics.values()),
        "metrics": metrics,
    }


def _paired_equivalence(
    control: list[float],
    hybrid: list[float],
    *,
    absolute_margin: float,
    relative_margin: float,
) -> dict[str, Any]:
    differences = [right - left for left, right in zip(control, hybrid, strict=True)]
    mean_difference = sum(differences) / len(differences)
    scale = max(abs(sum(control) / len(control)), max(map(abs, control), default=0.0), 1.0)
    margin = max(absolute_margin, relative_margin * scale)
    if len(differences) == 1:
        half_width = 0.0
    else:
        variance = sum((value - mean_difference) ** 2 for value in differences) / (len(differences) - 1)
        half_width = _critical_95(len(differences) - 1) * math.sqrt(variance / len(differences))
    lower = mean_difference - half_width
    upper = mean_difference + half_width
    max_absolute_difference = max(map(abs, differences), default=0.0)
    return {
        "method": "paired_mean_95pct_equivalence_interval",
        "equivalent": lower >= -margin and upper <= margin and max_absolute_difference <= margin * 5,
        "margin": margin,
        "mean_difference": mean_difference,
        "confidence_interval_95": [lower, upper],
        "max_absolute_difference": max_absolute_difference,
    }


def _critical_95(degrees_of_freedom: int) -> float:
    values = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        11: 2.201,
        12: 2.179,
        13: 2.160,
        14: 2.145,
        15: 2.131,
        16: 2.120,
        17: 2.110,
        18: 2.101,
        19: 2.093,
        20: 2.086,
        25: 2.060,
        30: 2.042,
    }
    for threshold in sorted(values):
        if degrees_of_freedom <= threshold:
            return values[threshold]
    return 1.96


def _trace_by_tick(rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row["tick"]): row for row in rows}


def _check(checks: dict[str, dict[str, Any]], name: str, passed: bool, **details: Any) -> None:
    checks[name] = {"status": "pass" if passed else "fail", **details}


def _verdict(checks: dict[str, dict[str, Any]]) -> str:
    return "pass" if checks and all(item["status"] == "pass" for item in checks.values()) else "fail"


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
