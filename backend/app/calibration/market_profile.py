"""Compile normalized ITCH windows into deterministic synthetic-market profiles."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import pyarrow.parquet as pq

PROFILE_SCHEMA_VERSION = "market_profile_v1"
REPORT_SCHEMA_VERSION = "market_profile_realism_report_v1"
SYNTHETIC_TICK_NS = 500_000_000
PRICE_TICK_X10000 = 10
QUANTITY_LOT_SCALE = 1_000

CORE_METRICS = (
    "arrival_intensity_events_per_second",
    "order_size",
    "spread_x10000",
    "top_depth",
    "absolute_imbalance",
    "mid_volatility_bps",
)


def extract_market_profile(dataset_dir: Path, *, profile_id: str | None = None) -> dict[str, Any]:
    """Extract empirical distributions and compile bounded Java simulation parameters."""
    manifest, events, books = _load_normalized_itch(dataset_dir)
    metrics = _measure(events, books)
    if metrics["mid_price_x10000"]["count"] == 0:
        raise ValueError("market profile requires at least one two-sided ITCH snapshot")
    resolved_id = profile_id or f"{manifest['dataset_id']}-market-v1"
    parameters = _compile_parameters(manifest, metrics)
    payload: dict[str, Any] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile_id": resolved_id,
        "source": {
            "dataset_id": manifest["dataset_id"],
            "source_type": manifest["source_type"],
            "format": manifest["format"],
            "venue": manifest["venue"],
            "symbol": manifest["symbol"],
            "trade_date": manifest["trade_date"],
            "start_time_ms": manifest["start_time_ms"],
            "end_time_ms": manifest["end_time_ms"],
            "row_count": manifest["row_count"],
            "source_stream_sha256": manifest.get("source_stream_sha256"),
            "parser_config_sha256": manifest.get("parser_config_sha256"),
            "output_sha256": {
                item["name"]: item["sha256"] for item in manifest.get("output_files", [])
            },
        },
        "distributions": metrics,
        "simulation_parameters": parameters,
    }
    payload["profile_sha256"] = _artifact_sha(payload)
    return payload


def build_realism_report(
    profile: dict[str, Any],
    held_out_dataset_dir: Path,
    *,
    simulation_runs: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate calibrated and hardcoded simulations against a disjoint ITCH window."""
    _validate_profile(profile)
    manifest, events, books = _load_normalized_itch(held_out_dataset_dir)
    if manifest["dataset_id"] == profile["source"]["dataset_id"]:
        raise ValueError("held-out dataset must be distinct from the calibration dataset")
    training_outputs = profile["source"].get("output_sha256", {})
    held_out_outputs = {
        item.get("name"): item.get("sha256") for item in manifest.get("output_files", [])
    }
    if training_outputs == held_out_outputs:
        raise ValueError("held-out dataset content must differ from the calibration dataset")
    training_source = profile["source"]
    if (
        manifest.get("source_stream_sha256") == training_source.get("source_stream_sha256")
        and manifest.get("symbol") == training_source.get("symbol")
        and manifest.get("trade_date") == training_source.get("trade_date")
        and not (
            int(manifest["end_time_ms"]) <= int(training_source["start_time_ms"])
            or int(training_source["end_time_ms"]) <= int(manifest["start_time_ms"])
        )
    ):
        raise ValueError("held-out ITCH window must not overlap the calibration window")
    held_out_metrics = _measure(events, books)
    observed = _metric_points(held_out_metrics)
    calibrated_run = _validate_simulation_run(
        simulation_runs, "calibrated", profile=profile, expected_source_type="synthetic_profile"
    )
    hardcoded_run = _validate_simulation_run(
        simulation_runs, "hardcoded", profile=profile, expected_source_type="synthetic"
    )
    calibrated_metrics = _simulation_distributions(calibrated_run["states"])
    hardcoded_metrics = _simulation_distributions(hardcoded_run["states"])
    calibrated = _metric_points(calibrated_metrics)
    hardcoded = _metric_points(hardcoded_metrics)
    calibrated_distances = _distribution_distances(held_out_metrics, calibrated_metrics)
    hardcoded_distances = _distribution_distances(held_out_metrics, hardcoded_metrics)
    calibrated_median = _round(median(calibrated_distances.values()))
    hardcoded_median = _round(median(hardcoded_distances.values()))
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "held_out_source": {
            "dataset_id": manifest["dataset_id"],
            "symbol": manifest["symbol"],
            "trade_date": manifest["trade_date"],
            "start_time_ms": manifest["start_time_ms"],
            "end_time_ms": manifest["end_time_ms"],
            "source_stream_sha256": manifest.get("source_stream_sha256"),
            "parser_config_sha256": manifest.get("parser_config_sha256"),
            "output_sha256": held_out_outputs,
            "row_count": manifest["row_count"],
        },
        "preregistered_core_metrics": list(CORE_METRICS),
        "observed": observed,
        "observed_quantiles": {
            metric: {
                quantile: held_out_metrics[metric][quantile]
                for quantile in ("p25", "median", "p75")
            }
            for metric in CORE_METRICS
        },
        "calibrated_simulation": calibrated,
        "hardcoded_regression_control": hardcoded,
        "simulation_quantiles": {
            "calibrated": calibrated_metrics,
            "hardcoded": hardcoded_metrics,
        },
        "simulation_runs": {
            "producer": simulation_runs["producer"],
            "master_seed": simulation_runs["master_seed"],
            "calibrated_trace_sha256": calibrated_run["trace_sha256"],
            "hardcoded_trace_sha256": hardcoded_run["trace_sha256"],
            "calibrated_attack_trace_sha256": calibrated_run["attack_trace_sha256"],
        },
        "normalized_distribution_distances": {
            "calibrated": calibrated_distances,
            "hardcoded": hardcoded_distances,
        },
        "median_realism_distance": {
            "calibrated": calibrated_median,
            "hardcoded": hardcoded_median,
            "improvement": _round(hardcoded_median - calibrated_median),
        },
        "completion_gate_passed": calibrated_median < hardcoded_median,
        "attack_response": _attack_response_from_run(calibrated_run),
        "determinism": {
            "seed": simulation_runs["master_seed"],
            "profile_sha_bound": True,
            "single_writer_required": True,
            "calibrated_repeat_match": True,
            "hardcoded_repeat_match": True,
            "calibrated_attack_repeat_match": True,
        },
    }
    report["report_sha256"] = _artifact_sha(report)
    return report


def write_json_artifact(payload: dict[str, Any], output: Path) -> None:
    """Atomically publish canonical, byte-deterministic JSON."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
    temporary.replace(output)


def _load_normalized_itch(dataset_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = dataset_dir / "manifest.json"
    events_path = dataset_dir / "events.parquet"
    books_path = dataset_dir / "book_snapshots.parquet"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_type") != "nasdaq_itch" or manifest.get("format") != "itch_parquet_v1":
        raise ValueError("market_profile_v1 requires normalized Nasdaq ITCH data")
    expected_outputs = {
        item.get("name"): item.get("sha256") for item in manifest.get("output_files", [])
    }
    for path in (events_path, books_path):
        expected = expected_outputs.get(path.name)
        if not isinstance(expected, str) or expected != _file_sha256(path):
            raise ValueError(f"normalized ITCH output hash mismatch: {path.name}")
    for field in ("source_stream_sha256", "parser_config_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"normalized ITCH manifest has invalid {field}")
    events = pq.read_table(events_path).to_pylist()
    books = pq.read_table(books_path).to_pylist()
    if not events or len(events) != len(books) or len(events) != manifest.get("row_count"):
        raise ValueError("events, snapshots, and manifest row counts must match and be non-zero")
    for event, book in zip(events, books, strict=True):
        if event["source_sequence"] != book["source_sequence"]:
            raise ValueError("event and snapshot source sequences are not aligned")
        if event["timestamp_ns_since_midnight"] != book["timestamp_ns_since_midnight"]:
            raise ValueError("event and snapshot timestamps are not aligned")
    if any(
        right["timestamp_ns_since_midnight"] < left["timestamp_ns_since_midnight"]
        for left, right in zip(events, events[1:], strict=False)
    ):
        raise ValueError("normalized ITCH timestamps are not monotonic")
    return manifest, events, books


def _measure(events: list[dict[str, Any]], books: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [int(event["timestamp_ns_since_midnight"]) for event in events]
    inter_event = [right - left for left, right in zip(timestamps, timestamps[1:], strict=False)]
    arrival_buckets = Counter(timestamp // 60_000_000_000 for timestamp in timestamps)
    arrival_rates = [count / 60 for _, count in sorted(arrival_buckets.items())]
    sizes = [int(event["size"]) for event in events if int(event["size"]) > 0]
    add_sizes = [int(event["size"]) for event in events if event["event_kind"] == "ADD"]
    distances: list[int] = []
    spreads: list[int] = []
    spread_timestamps: list[int] = []
    depths: list[int] = []
    imbalances: list[float] = []
    mids: list[float] = []
    for event, book in zip(events, books, strict=True):
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        bid_depth = sum(int(level["quantity"]) for level in bids)
        ask_depth = sum(int(level["quantity"]) for level in asks)
        depth = bid_depth + ask_depth
        depths.append(depth)
        imbalances.append(0 if depth == 0 else (bid_depth - ask_depth) / depth)
        if bids and asks:
            bid = int(bids[0]["price_x10000"])
            ask = int(asks[0]["price_x10000"])
            spreads.append(ask - bid)
            spread_timestamps.append(int(event["timestamp_ns_since_midnight"]))
            mids.append((ask + bid) / 2)
        if event["event_kind"] == "ADD":
            levels = bids if event.get("book_side") == "BUY" else asks
            prior_touch = _pre_add_touch(event, levels)
            if prior_touch is not None:
                distances.append(abs(int(event["price_x10000"]) - prior_touch))
    returns = [abs(right - left) / left * 10_000 for left, right in zip(mids, mids[1:], strict=False) if left]
    lifetimes = _order_lifetimes(events)
    refill_times, resilience_times = _recovery_times(
        timestamps, depths, spread_timestamps, spreads
    )
    kinds = Counter(str(event["event_kind"]) for event in events)
    reductions = kinds["PARTIAL_CANCEL"] + kinds["DELETE"] + kinds["VISIBLE_EXECUTION"]
    return {
        "arrival_intensity_events_per_second": _distribution(arrival_rates),
        "inter_event_time_ns": _distribution(inter_event),
        "order_size": _distribution(add_sizes or sizes),
        "distance_from_touch_x10000": _distribution(distances),
        "order_lifetime_ns": _distribution(lifetimes),
        "cancellation_ratio": _round((kinds["PARTIAL_CANCEL"] + kinds["DELETE"]) / max(1, reductions)),
        "execution_ratio": _round(kinds["VISIBLE_EXECUTION"] / max(1, reductions)),
        "spread_x10000": _distribution(spreads),
        "mid_price_x10000": _distribution(mids),
        "top_depth": _distribution(depths),
        "imbalance": _distribution(imbalances),
        "absolute_imbalance": _distribution(abs(value) for value in imbalances),
        "mid_volatility_bps": _distribution(returns),
        "refill_time_ns": _distribution(refill_times),
        "resilience_time_ns": _distribution(resilience_times),
        "event_kind_counts": dict(sorted(kinds.items())),
    }


def _pre_add_touch(event: dict[str, Any], post_event_levels: list[dict[str, Any]]) -> int | None:
    event_price = int(event["price_x10000"])
    event_size = int(event["size"])
    for level in post_event_levels:
        price = int(level["price_x10000"])
        quantity = int(level["quantity"])
        if price != event_price or quantity > event_size:
            return price
    return None


def _order_lifetimes(events: list[dict[str, Any]]) -> list[int]:
    active: dict[int, tuple[int, int]] = {}
    lifetimes: list[int] = []
    for event in events:
        reference = int(event["source_order_id"])
        timestamp = int(event["timestamp_ns_since_midnight"])
        size = int(event["size"])
        kind = event["event_kind"]
        if kind == "ADD":
            active[reference] = (timestamp, size)
        elif reference in active:
            started, remaining = active[reference]
            if kind == "REPLACE":
                lifetimes.append(timestamp - started)
                active.pop(reference)
                replacement = event.get("replacement_order_reference")
                if replacement is not None:
                    active[int(replacement)] = (timestamp, size)
            elif kind == "DELETE" or size >= remaining:
                lifetimes.append(timestamp - started)
                active.pop(reference)
            elif kind in {"PARTIAL_CANCEL", "VISIBLE_EXECUTION"}:
                active[reference] = (started, remaining - size)
    return lifetimes


def _recovery_times(
    timestamps: list[int],
    depths: list[int],
    spread_timestamps: list[int],
    spreads: list[int],
) -> tuple[list[int], list[int]]:
    refill: list[int] = []
    resilience: list[int] = []
    for index in range(1, len(depths)):
        previous = depths[index - 1]
        if previous > 0 and depths[index] < previous * 0.75:
            for recovered in range(index + 1, len(depths)):
                if depths[recovered] >= previous * 0.9:
                    refill.append(timestamps[recovered] - timestamps[index])
                    break
    if spreads:
        normal = median(spreads)
        for index, spread in enumerate(spreads):
            if normal > 0 and spread > normal * 1.5:
                for recovered in range(index + 1, len(spreads)):
                    if spreads[recovered] <= normal * 1.1:
                        resilience.append(spread_timestamps[recovered] - spread_timestamps[index])
                        break
    return refill, resilience


def _compile_parameters(manifest: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    depth = max(1, min(12, int(manifest.get("depth", 10))))
    reference_x10000 = max(
        PRICE_TICK_X10000 * 100,
        metrics["mid_price_x10000"]["median"],
    )
    spread_x10000 = max(2 * PRICE_TICK_X10000, round(metrics["spread_x10000"]["median"]))
    total_depth = max(2, round(metrics["top_depth"]["median"]))
    order_size = max(1, round(metrics["order_size"]["median"]))
    depth_increment_lots = max(1, round(order_size * QUANTITY_LOT_SCALE / max(2, depth)))
    target_side_lots = total_depth * QUANTITY_LOT_SCALE / 2
    increment_total = depth_increment_lots * depth * (depth - 1) / 2
    base_quantity_lots = max(1, round((target_side_lots - increment_total) / depth))
    volatility_x10000 = max(
        PRICE_TICK_X10000,
        round(reference_x10000 * metrics["mid_volatility_bps"]["median"] / 10_000),
    )
    refill_ns = metrics["refill_time_ns"]["median"] or SYNTHETIC_TICK_NS * 4
    arrival = metrics["arrival_intensity_events_per_second"]["median"]
    level_spacing_ticks = max(1, round(spread_x10000 / (2 * PRICE_TICK_X10000)))
    return {
        "symbol": manifest["symbol"],
        "venue": "SIM",
        "reference_price_ticks": max(1, round(reference_x10000 / PRICE_TICK_X10000)),
        "baseline_levels": depth,
        "level_spacing_ticks": level_spacing_ticks,
        "base_quantity_lots": base_quantity_lots,
        "depth_increment_lots": depth_increment_lots,
        "reference_update_interval_ticks": max(
            1, min(10_000, round(metrics["inter_event_time_ns"]["median"] / SYNTHETIC_TICK_NS))
        ),
        "reference_max_step_ticks": min(
            level_spacing_ticks,
            max(1, round(volatility_x10000 / PRICE_TICK_X10000)),
        ),
        "refill_ticks": max(1, min(10_000, round(refill_ns / SYNTHETIC_TICK_NS))),
        "normal_agent_count": max(1, min(64, round(arrival * 2))),
        "agent_order_size_lots": order_size * QUANTITY_LOT_SCALE,
        "arrival_events_per_tick": _round(arrival * SYNTHETIC_TICK_NS / 1_000_000_000),
        "target_absolute_imbalance": metrics["absolute_imbalance"]["median"],
    }
def _metric_points(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "arrival_intensity_events_per_second": metrics["arrival_intensity_events_per_second"]["median"],
        "order_size": metrics["order_size"]["median"],
        "spread_x10000": metrics["spread_x10000"]["median"],
        "top_depth": metrics["top_depth"]["median"],
        "absolute_imbalance": metrics["absolute_imbalance"]["median"],
        "mid_volatility_bps": metrics["mid_volatility_bps"]["median"],
    }


def _distribution_distances(
    observed_distributions: dict[str, Any], simulated_distributions: dict[str, Any]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for metric in CORE_METRICS:
        observed = observed_distributions[metric]
        simulated = simulated_distributions[metric]
        result[metric] = _round(
            sum(
                abs(float(simulated[name]) - float(observed[name]))
                / max(abs(float(observed[name])), 1.0)
                for name in ("p25", "median", "p75")
            )
            / 3
        )
    return result


def _validate_simulation_run(
    simulation_runs: dict[str, Any],
    name: str,
    *,
    profile: dict[str, Any],
    expected_source_type: str,
) -> dict[str, Any]:
    if simulation_runs.get("schema_version") != "market_profile_simulation_runs_v1":
        raise ValueError("realism report requires market_profile_simulation_runs_v1")
    if simulation_runs.get("producer") != "java_control_plane":
        raise ValueError("realism report requires Java control-plane simulation runs")
    if not isinstance(simulation_runs.get("master_seed"), int):
        raise ValueError("simulation runs require an integer master_seed")
    run = simulation_runs.get(name)
    if not isinstance(run, dict) or run.get("source_type") != expected_source_type:
        raise ValueError(f"simulation run {name} has the wrong source type")
    states = run.get("states")
    attack_states = run.get("attack_states")
    if not isinstance(states, list) or len(states) < 4:
        raise ValueError(f"simulation run {name} requires at least four states")
    if not isinstance(attack_states, list) or len(attack_states) < 3:
        raise ValueError(f"simulation run {name} requires attack states")
    expected_trace = hashlib.sha256(_canonical_json(states).encode()).hexdigest()
    expected_attack_trace = hashlib.sha256(_canonical_json(attack_states).encode()).hexdigest()
    if run.get("trace_sha256") != expected_trace or run.get("repeat_trace_sha256") != expected_trace:
        raise ValueError(f"simulation run {name} is not repeat deterministic")
    if (
        run.get("attack_trace_sha256") != expected_attack_trace
        or run.get("repeat_attack_trace_sha256") != expected_attack_trace
    ):
        raise ValueError(f"simulation attack run {name} is not repeat deterministic")
    if expected_source_type == "synthetic_profile":
        if run.get("profile_sha256") != profile["profile_sha256"]:
            raise ValueError("calibrated simulation is not bound to the selected profile")
        if any(
            state.get("market_data", {}).get("profile_sha256") != profile["profile_sha256"]
            for state in states + attack_states
        ):
            raise ValueError("calibrated simulation state lost its profile binding")
    return run


def _simulation_distributions(states: list[dict[str, Any]]) -> dict[str, Any]:
    arrivals: list[float] = []
    order_sizes: list[float] = []
    spreads: list[float] = []
    depths: list[float] = []
    imbalances: list[float] = []
    mids: list[float] = []
    for state in states:
        tick = int(state["tick"])
        book = state.get("book") or {}
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        bid_depth = sum(float(level["quantity"]) for level in bids)
        ask_depth = sum(float(level["quantity"]) for level in asks)
        depth = bid_depth + ask_depth
        depths.append(depth)
        imbalances.append(0.0 if depth == 0 else abs(bid_depth - ask_depth) / depth)
        if bids and asks:
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            spreads.append((best_ask - best_bid) * 10_000)
            mids.append((best_ask + best_bid) / 2)
        current_events = [
            event
            for event in state.get("exchange_events", [])
            if int(event.get("tick") or -1) == tick and event.get("event_type") != "snapshot"
        ]
        arrivals.append(len(current_events) * 2.0)
        order_sizes.extend(
            float(event["quantity"])
            for event in current_events
            if event.get("event_type") == "add" and float(event.get("quantity") or 0) > 0
        )
    returns = [
        abs(right - left) / left * 10_000
        for left, right in zip(mids, mids[1:], strict=False)
        if left
    ]
    return {
        "arrival_intensity_events_per_second": _distribution(arrivals),
        "order_size": _distribution(order_sizes),
        "spread_x10000": _distribution(spreads),
        "top_depth": _distribution(depths),
        "absolute_imbalance": _distribution(imbalances),
        "mid_volatility_bps": _distribution(returns),
    }


def _attack_response_from_run(run: dict[str, Any]) -> dict[str, Any]:
    states = run["attack_states"]
    windows = run.get("attack_windows")
    if windows != {"before": [0, 19], "during": [20, 29], "after": [30, 39]} or len(states) < 40:
        raise ValueError("simulation attack run has invalid before/during/after windows")

    def measurements(state: dict[str, Any]) -> tuple[float, float]:
        book = state.get("book") or {}
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        depth = sum(float(level["quantity"]) for level in bids + asks)
        spread = 0.0
        if bids and asks:
            spread = (float(asks[0]["price"]) - float(bids[0]["price"])) * 10_000
        return depth, spread

    measured = [measurements(state) for state in states]

    def window_median(field: int, start: int, end: int) -> int | float:
        return _round(median(row[field] for row in measured[start : end + 1]))

    return {
        "scenario": "liquidity_evaporation",
        "windows": windows,
        "depth_top_n": {
            "before": window_median(0, 0, 19),
            "during": window_median(0, 20, 29),
            "after": window_median(0, 30, 39),
        },
        "spread_x10000": {
            "before": window_median(1, 0, 19),
            "during": window_median(1, 20, 29),
            "after": window_median(1, 30, 39),
        },
        "simulation_trace_sha256": run["attack_trace_sha256"],
    }


def _distribution(values: Iterable[int | float]) -> dict[str, int | float]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"count": 0, "min": 0, "p25": 0, "median": 0, "p75": 0, "max": 0, "mean": 0}
    return {
        "count": len(ordered),
        "min": _round(ordered[0]),
        "p25": _round(_quantile(ordered, 0.25)),
        "median": _round(_quantile(ordered, 0.5)),
        "p75": _round(_quantile(ordered, 0.75)),
        "max": _round(ordered[-1]),
        "mean": _round(sum(ordered) / len(ordered)),
    }


def _quantile(values: list[float], probability: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("unsupported market profile schema")
    expected = profile.get("profile_sha256")
    if not isinstance(expected, str) or expected != _artifact_sha(profile):
        raise ValueError("market profile SHA-256 does not match its canonical content")


def _artifact_sha(payload: dict[str, Any]) -> str:
    content = {key: value for key, value in payload.items() if key not in {"profile_sha256", "report_sha256"}}
    return hashlib.sha256(_canonical_json(content).encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _round(value: int | float) -> int | float:
    rounded = round(float(value), 9)
    return int(rounded) if rounded.is_integer() else rounded
