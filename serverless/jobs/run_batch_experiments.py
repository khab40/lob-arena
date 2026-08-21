import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _add_backend_to_path() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2],
        here.parents[2] / "backend",
        Path.cwd() / "backend",
        Path("/job/backend"),
    ]
    for candidate in candidates:
        if (candidate / "app").exists():
            sys.path.insert(0, str(candidate))
            return


_add_backend_to_path()

from app.arena.engine import SimulationEngine  # noqa: E402
from app.evaluation.ground_truth import evaluate_detection, evidence_attribution  # noqa: E402
from app.evaluation.run_planning import (  # noqa: E402
    DEFAULT_DIFFICULTY_MIX,
    derive_run_seed,
    engine_profile,
    exact_balanced_plan,
    exact_weighted_plan,
    parse_difficulty_mix,
)
from app.scenarios.catalog import BENCHMARK_SCENARIOS  # noqa: E402
from app.nebius.object_storage import sync_s3  # noqa: E402


SCENARIOS = list(BENCHMARK_SCENARIOS)
SCENARIO_TO_ENGINE = {scenario: scenario for scenario in SCENARIOS if scenario != "normal_market"}
SCENARIO_TO_ENGINE["normal_market"] = None


@dataclass
class BatchResult:
    run_id: str
    scenario: str
    difficulty: str
    seed: int
    events: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    labels: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    metrics: dict[str, Any]
    report: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parallel synthetic attack/detect batches.")
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-workers", type=int, default=0)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--difficulty-mix", default=json.dumps(DEFAULT_DIFFICULTY_MIX))
    parser.add_argument("--output", type=Path, default=Path("outputs/serverless-batch"))
    parser.add_argument("--s3-output-uri", default="")
    parser.add_argument("--s3-endpoint-url", default="")
    args = parser.parse_args()

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    if not scenarios:
        parser.error("at least one scenario is required")
    runs = max(1, args.runs)
    batch_size = max(1, min(args.batch_size, 500))
    max_workers = batch_size if args.max_workers <= 0 else max(1, min(args.max_workers, batch_size))
    difficulty_mix = parse_difficulty_mix(args.difficulty_mix)
    scenario_plan = exact_balanced_plan(runs, scenarios, seed=args.random_seed)
    difficulty_plan = exact_weighted_plan(runs, difficulty_mix, seed=args.random_seed + 1)

    results: list[BatchResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_one,
                index,
                scenario_plan[index],
                difficulty_plan[index],
                args.random_seed,
            )
            for index in range(runs)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.run_id)
    _write_jsonl(output / "order_book_events.jsonl", (row for result in results for row in result.events))
    _write_jsonl(output / "trades.jsonl", (row for result in results for row in result.trades))
    _write_jsonl(output / "attack_labels.jsonl", (row for result in results for row in result.labels))
    _write_jsonl(output / "blue_team_alerts.jsonl", (row for result in results for row in result.alerts))
    metrics = _aggregate_metrics(results)
    _write_metrics(output / "detector_metrics.csv", metrics)
    report = _build_report(results, metrics, max_workers)
    (output / "generated_report.md").write_text(report, encoding="utf-8")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "batch_size": batch_size,
        "max_workers": max_workers,
        "scenarios": scenarios,
        "scenario_counts": _counts(scenario_plan),
        "random_seed": args.random_seed,
        "seed_strategy": "sha256(base_seed, run_index)",
        "difficulty_mix": difficulty_mix,
        "difficulty_counts": _counts(difficulty_plan),
        "artifacts": {
            "order_book_event_logs": str(output / "order_book_events.jsonl"),
            "trades": str(output / "trades.jsonl"),
            "attack_labels": str(output / "attack_labels.jsonl"),
            "blue_team_alerts": str(output / "blue_team_alerts.jsonl"),
            "detector_metrics": str(output / "detector_metrics.csv"),
            "generated_report": str(output / "generated_report.md"),
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if args.s3_output_uri:
        _sync_to_s3(output, args.s3_output_uri, args.s3_endpoint_url)
    print(json.dumps(manifest, indent=2))


def _run_one(
    index: int,
    scenario: str,
    difficulty: str = "medium",
    random_seed: int = 42,
) -> BatchResult:
    run_id = f"batch-{index:06d}"
    run_seed = derive_run_seed(random_seed, index)
    engine = SimulationEngine(seed=run_seed, **engine_profile(difficulty, seed=run_seed))
    engine_scenario = SCENARIO_TO_ENGINE.get(scenario)
    if engine_scenario is not None:
        engine.launch_scenario(engine_scenario)

    events: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    labels: dict[str, dict[str, Any]] = {}
    alerts: dict[str, dict[str, Any]] = {}
    max_confidence = 0.0
    detected_pattern = "normal_market"
    first_alert_tick: int | None = None
    alert_ticks: list[int] = []
    predicted_participants: set[str] = set()
    predicted_orders: set[str] = set()
    predicted_events: set[str] = set()
    final_label: dict[str, Any] | None = None

    for _ in range(16):
        state = engine.step()
        for event in state["events"][:8]:
            row = dict(event)
            row["run_id"] = run_id
            row["tick"] = state["tick"]
            row["seed"] = run_seed
            row["difficulty"] = difficulty
            row["scenario"] = scenario
            events.append(row)
            if row.get("type") == "trade" or "trade" in str(row.get("message", "")).lower():
                trades.append(row)
        active = state.get("active_scenario")
        if active and active.get("label"):
            final_label = {
                "run_id": run_id,
                "difficulty": difficulty,
                "has_attack": True,
                **active["label"],
            }
            labels[str(active["label"]["label_id"])] = final_label
        for score in state["detectors"]["scores"]:
            confidence = float(score["confidence"])
            if confidence > max_confidence:
                max_confidence = confidence
                detected_pattern = str(score["name"])
            if confidence >= 0.75:
                alert_ticks.append(int(state["tick"]))
                participants, orders, linked_events = evidence_attribution(score.get("evidence") or [])
                predicted_participants.update(participants)
                predicted_orders.update(orders)
                predicted_events.update(linked_events)
                alert_id = f"{run_id}-{score['name']}"
                alerts[alert_id] = {
                    "alert_id": alert_id,
                    "run_id": run_id,
                    "tick": state["tick"],
                    "scenario": scenario,
                    "detector": score["name"],
                    "confidence": confidence,
                    "evidence": score.get("evidence") or [],
                    "participant_ids": sorted(participants),
                    "order_ids": sorted(orders),
                    "event_ids": sorted(linked_events),
                }
                first_alert_tick = first_alert_tick or int(state["tick"])

    evaluation = evaluate_detection(
        alert_ticks=alert_ticks,
        label=final_label if scenario != "normal_market" else None,
        predicted_participant_ids=predicted_participants,
        predicted_order_ids=predicted_orders,
        predicted_event_ids=predicted_events,
    )
    metrics = {
        "run_id": run_id,
        "scenario": scenario,
        "difficulty": difficulty,
        "seed": run_seed,
        "detected_pattern": detected_pattern,
        "max_confidence": round(max_confidence, 4),
        "alert_count": len(alerts),
        "first_alert_tick": first_alert_tick,
        "detected": bool(alerts),
        **evaluation,
    }
    return BatchResult(
        run_id=run_id,
        scenario=scenario,
        difficulty=difficulty,
        seed=run_seed,
        events=events,
        trades=trades,
        labels=list(labels.values())
        or [
            {
                "run_id": run_id,
                "scenario": scenario,
                "scenario_family": scenario,
                "difficulty": difficulty,
                "seed": run_seed,
                "has_attack": scenario != "normal_market",
            }
        ],
        alerts=list(alerts.values()),
        metrics=metrics,
        report=f"{run_id}: {scenario} -> {detected_pattern} at confidence {max_confidence:.2f}",
    )


def _aggregate_metrics(results: list[BatchResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_scenario: dict[str, list[BatchResult]] = {}
    for result in results:
        by_scenario.setdefault(result.scenario, []).append(result)

    for scenario, scenario_results in sorted(by_scenario.items()):
        attack = scenario != "normal_market"
        detections = sum(1 for result in scenario_results if result.metrics["detected"])
        false_positives = detections if not attack else 0
        true_negatives = len(scenario_results) - detections if not attack else 0
        precision = 1.0 if attack and detections else None
        recall = detections / len(scenario_results) if attack else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall
            else 0.0 if recall == 0 else None
        )
        specificity = true_negatives / (true_negatives + false_positives) if not attack else None
        false_positive_rate = false_positives / len(scenario_results) if not attack else None
        alert_ticks = [
            result.metrics["first_alert_tick"]
            for result in scenario_results
            if result.metrics["first_alert_tick"] is not None
        ]
        rows.append(
            {
                "scenario": scenario,
                "detector": "built-in detector suite",
                "model": "none (deterministic)",
                "runs": len(scenario_results),
                "alerts": detections,
                "precision": _rounded(precision),
                "recall": _rounded(recall),
                "f1": _rounded(f1),
                "specificity": _rounded(specificity),
                "false_positive_rate": _rounded(false_positive_rate),
                "avg_detection_latency_ms": round((sum(alert_ticks) / len(alert_ticks)) * 500, 2)
                if alert_ticks
                else "",
                "temporal_overlap": _average_metric(scenario_results, "temporal_overlap"),
                "event_precision": _average_metric(scenario_results, "event_precision"),
                "event_recall": _average_metric(scenario_results, "event_recall"),
                "participant_precision": _average_metric(scenario_results, "participant_precision"),
                "participant_recall": _average_metric(scenario_results, "participant_recall"),
                "order_precision": _average_metric(scenario_results, "order_precision"),
                "order_recall": _average_metric(scenario_results, "order_recall"),
                "early_detections": sum(row.metrics["detection_timing"] == "early" for row in scenario_results),
                "on_time_detections": sum(row.metrics["detection_timing"] == "on_time" for row in scenario_results),
                "late_detections": sum(row.metrics["detection_timing"] == "late" for row in scenario_results),
                "missed_detections": sum(row.metrics["detection_timing"] == "missed" for row in scenario_results),
                "phase_detection": json.dumps(_phase_rates(scenario_results), sort_keys=True),
            }
        )
    return rows


def _counts(values: list[str]) -> dict[str, int]:
    return {value: values.count(value) for value in sorted(set(values))}


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _display(value: object) -> object:
    return value if value is not None and value != "" else "n/a"


def _average_metric(results: list[BatchResult], name: str) -> float | None:
    values = [
        value
        for result in results
        if (value := result.metrics.get(name)) is not None
    ]
    return round(sum(values) / len(values), 4) if values else None


def _phase_rates(results: list[BatchResult]) -> dict[str, float]:
    phases = sorted(
        {
            phase
            for result in results
            for phase in result.metrics.get("phase_detection", {})
        }
    )
    return {
        phase: round(
            sum(bool(result.metrics.get("phase_detection", {}).get(phase)) for result in results)
            / len(results),
            4,
        )
        for phase in phases
    }


def _write_jsonl(path: Path, rows: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_drop_nulls(row)) + "\n")


def _drop_nulls(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


def _write_metrics(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "detector",
                "model",
                "runs",
                "alerts",
                "precision",
                "recall",
                "f1",
                "specificity",
                "false_positive_rate",
                "avg_detection_latency_ms",
                "temporal_overlap",
                "event_precision",
                "event_recall",
                "participant_precision",
                "participant_recall",
                "order_precision",
                "order_recall",
                "early_detections",
                "on_time_detections",
                "late_detections",
                "missed_detections",
                "phase_detection",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _sync_to_s3(output: Path, s3_output_uri: str, endpoint_url: str) -> None:
    sync_s3(str(output), s3_output_uri.rstrip("/"), endpoint_url=endpoint_url or None)


def _build_report(results: list[BatchResult], metrics: list[dict[str, Any]], max_workers: int) -> str:
    lines = [
        "# Smart Attack/Detect Batch Report",
        "",
        "Educational synthetic simulation only. Not for real market surveillance, trading, or compliance use.",
        "",
        f"- Simulations: {len(results)}",
        f"- Parallel workers: {max_workers}",
        "- Output files: 6",
        "",
        "| Scenario | Runs | Alerts | Precision | Recall | F1 | Avg latency ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics:
        lines.append(
            f"| {row['scenario']} | {row['runs']} | {row['alerts']} | {_display(row['precision'])} | "
            f"{_display(row['recall'])} | {_display(row['f1'])} | "
            f"{_display(row['avg_detection_latency_ms'])} |"
        )
    lines.extend(["", "## Sample Reports", ""])
    for result in results[:12]:
        lines.append(f"- {result.report}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
