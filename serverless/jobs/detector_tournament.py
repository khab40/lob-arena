import argparse
import csv
import json
import sys
import struct
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


def _add_backend_to_path() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "backend",
        Path.cwd() / "backend",
        Path.cwd(),
    ]
    for candidate in candidates:
        if (candidate / "app").exists():
            sys.path.insert(0, str(candidate))
            return


_add_backend_to_path()

from app.arena.engine import SimulationEngine  # noqa: E402
from app.evaluation.ground_truth import (  # noqa: E402
    binary_classification_metrics,
    evaluate_detection,
    evidence_attribution,
)
from app.evaluation.run_planning import (  # noqa: E402
    DEFAULT_DIFFICULTY_MIX,
    derive_run_seed,
    engine_profile,
    exact_balanced_plan,
    exact_weighted_plan,
    parse_difficulty_mix,
)
from app.nebius.job_logging import JobLogger  # noqa: E402
from app.scenarios.catalog import BENCHMARK_SCENARIOS  # noqa: E402


DEFAULT_SCENARIOS = list(BENCHMARK_SCENARIOS)
DEFAULT_DETECTORS = ["spoofing_like", "layering_like", "quote_stuffing", "liquidity_shock"]
JOB_LOG = JobLogger("detector-tournament")


@dataclass
class RunResult:
    run_id: str
    scenario: str
    detector: str
    difficulty: str
    seed: int
    ground_truth_label: str
    predicted: bool
    truth: bool
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    latency_ms: float | None
    max_confidence: float
    temporal_overlap: float | None
    event_precision: float | None
    event_recall: float | None
    detection_timing: str
    participant_precision: float | None
    participant_recall: float | None
    order_precision: float | None
    order_recall: float | None
    phase_detection: dict[str, bool]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a synthetic detector tournament benchmark.")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--scenarios", default=",".join(DEFAULT_SCENARIOS))
    parser.add_argument("--detectors", default=",".join(DEFAULT_DETECTORS))
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--difficulty-mix", default=json.dumps(DEFAULT_DIFFICULTY_MIX))
    parser.add_argument("--output", type=Path, default=Path("outputs/benchmark"))
    args = parser.parse_args()

    scenarios = [_normalize_scenario(item) for item in _split_csv(args.scenarios)]
    detectors = [_normalize_detector(item) for item in _split_csv(args.detectors)]
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = max(1, args.runs)
    difficulty_mix = parse_difficulty_mix(args.difficulty_mix)
    scenario_plan = exact_balanced_plan(runs, scenarios, seed=args.random_seed)
    difficulty_plan = exact_weighted_plan(runs, difficulty_mix, seed=args.random_seed + 1)
    JOB_LOG.info(
        "tournament.planned",
        "Build a deterministic scenario plan and compare every selected detector against governed labels.",
        runs=runs,
        scenario_count=len(scenarios),
        detector_count=len(detectors),
        random_seed=args.random_seed,
    )
    run_results: list[RunResult] = []
    with JOB_LOG.phase(
        "tournament.execute",
        "Run each market simulation and compute detector outcomes, timing, and evidence attribution.",
        runs=runs,
        detector_count=len(detectors),
    ):
        for run_index, (scenario, difficulty) in enumerate(zip(scenario_plan, difficulty_plan)):
            run_results.extend(
                _run_one_simulation(
                    run_index,
                    scenario,
                    detectors,
                    random_seed=args.random_seed,
                    difficulty=difficulty,
                )
            )

    JOB_LOG.info(
        "artifacts.started",
        "Aggregate detector metrics and write the results, report, and chart artifacts.",
        result_count=len(run_results),
    )
    metrics = _compute_metrics(run_results, detectors)
    _write_metrics_csv(output_dir / "metrics.csv", metrics)
    _write_results_json(output_dir / "results.json", runs, scenarios, detectors, metrics, run_results)
    _write_report(output_dir / "benchmark_report.md", runs, scenarios, detectors, metrics)
    _write_charts(output_dir / "charts", metrics)
    JOB_LOG.info(
        "tournament.completed",
        "The detector tournament completed and its comparison artifacts are ready.",
        runs=runs,
        result_count=len(run_results),
        metric_count=len(metrics),
    )

    print(
        json.dumps(
            {
                "runs": runs,
                "random_seed": args.random_seed,
                "difficulty_mix": difficulty_mix,
                "scenarios": scenarios,
                "detectors": detectors,
                "output": str(output_dir),
            },
            indent=2,
        )
    )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_scenario(value: str) -> str:
    scenario = value.strip().lower()
    if scenario not in DEFAULT_SCENARIOS:
        raise ValueError(f"unsupported scenario: {value}")
    return scenario


def _normalize_detector(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _run_one_simulation(
    run_index: int,
    scenario: str,
    detectors: list[str],
    *,
    random_seed: int = 42,
    difficulty: str = "medium",
) -> list[RunResult]:
    run_seed = derive_run_seed(random_seed, run_index)
    engine = SimulationEngine(seed=run_seed, **engine_profile(difficulty, seed=run_seed))
    if scenario != "normal_market":
        engine.launch_scenario(scenario)
    first_alert_tick: dict[str, int] = {}
    alert_ticks: dict[str, list[int]] = defaultdict(list)
    max_confidence: dict[str, float] = defaultdict(float)
    incident_detectors: set[str] = set()
    detector_participants: dict[str, set[str]] = defaultdict(set)
    detector_orders: dict[str, set[str]] = defaultdict(set)
    detector_events: dict[str, set[str]] = defaultdict(set)
    label: dict[str, object] | None = None

    for _ in range(14):
        state = engine.step()
        for score in state["detectors"]["scores"]:
            detector_name = score["name"]
            confidence = float(score["confidence"])
            max_confidence[detector_name] = max(max_confidence[detector_name], confidence)
            if confidence >= 0.75 and detector_name not in first_alert_tick:
                first_alert_tick[detector_name] = int(state["tick"])
            if confidence >= 0.75:
                alert_ticks[detector_name].append(int(state["tick"]))
                participants, orders, events = evidence_attribution(score.get("evidence") or [])
                detector_participants[detector_name].update(participants)
                detector_orders[detector_name].update(orders)
                detector_events[detector_name].update(events)
        for incident in state.get("incidents", []):
            incident_detectors.add(str(incident["type"]))
        active = state.get("active_scenario")
        if isinstance(active, dict) and isinstance(active.get("label"), dict):
            label = active["label"]

    results: list[RunResult] = []
    for detector in detectors:
        truth = scenario != "normal_market"
        predicted = detector in incident_detectors or max_confidence[detector] >= 0.75
        true_positive = int(truth and predicted)
        false_positive = int(not truth and predicted)
        false_negative = int(truth and not predicted)
        true_negative = int(not truth and not predicted)
        latency_ms = None
        if detector in first_alert_tick:
            latency_ms = max(0, first_alert_tick[detector] - 1) * engine.tick_interval_seconds * 1000
        evaluation = evaluate_detection(
            alert_ticks=alert_ticks[detector],
            label=label if truth else None,
            predicted_participant_ids=detector_participants[detector],
            predicted_order_ids=detector_orders[detector],
            predicted_event_ids=detector_events[detector],
        )
        results.append(
            RunResult(
                run_id=f"run-{run_index:05d}",
                scenario=scenario,
                detector=detector,
                difficulty=difficulty,
                seed=run_seed,
                ground_truth_label=scenario if truth else "normal_market",
                predicted=predicted,
                truth=truth,
                true_positive=true_positive,
                false_positive=false_positive,
                false_negative=false_negative,
                true_negative=true_negative,
                latency_ms=latency_ms,
                max_confidence=round(max_confidence[detector], 4),
                **evaluation,
            )
        )
    return results


def _compute_metrics(run_results: list[RunResult], detectors: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    groups: dict[tuple[str, str], list[RunResult]] = defaultdict(list)
    for result in run_results:
        groups[(result.scenario, result.detector)].append(result)

    for (scenario, detector), results in sorted(groups.items()):
        if detector not in detectors:
            continue
        tp = sum(item.true_positive for item in results)
        fp = sum(item.false_positive for item in results)
        fn = sum(item.false_negative for item in results)
        tn = sum(item.true_negative for item in results)
        classification = binary_classification_metrics(tp=tp, fp=fp, fn=fn, tn=tn)
        latencies = [item.latency_ms for item in results if item.latency_ms is not None and item.truth]
        rows.append(
            {
                "scenario": scenario,
                "detector": detector,
                "precision": classification["precision"],
                "recall": classification["recall"],
                "f1": classification["f1"],
                "specificity": classification["specificity"],
                "false_positive_rate": classification["false_positive_rate"],
                "avg_detection_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "true_negative": tn,
                "runs": len(results),
                "temporal_overlap": _average_metric(results, "temporal_overlap"),
                "event_precision": _average_metric(results, "event_precision"),
                "event_recall": _average_metric(results, "event_recall"),
                "participant_precision": _average_metric(results, "participant_precision"),
                "participant_recall": _average_metric(results, "participant_recall"),
                "order_precision": _average_metric(results, "order_precision"),
                "order_recall": _average_metric(results, "order_recall"),
                "early_detections": sum(item.detection_timing == "early" for item in results),
                "on_time_detections": sum(item.detection_timing == "on_time" for item in results),
                "late_detections": sum(item.detection_timing == "late" for item in results),
                "missed_detections": sum(item.detection_timing == "missed" for item in results),
                "phase_detection": json.dumps(_phase_rates(results), sort_keys=True),
            }
        )
    return rows


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _average_metric(results: list[RunResult], name: str) -> float | None:
    values = [value for result in results if (value := getattr(result, name)) is not None]
    return round(sum(values) / len(values), 4) if values else None


def _phase_rates(results: list[RunResult]) -> dict[str, float]:
    phases = sorted({phase for result in results for phase in result.phase_detection})
    return {
        phase: round(
            sum(result.phase_detection.get(phase, False) for result in results) / len(results),
            4,
        )
        for phase in phases
    }


def _display(value: object) -> object:
    return value if value is not None and value != "" else "n/a"


def _write_metrics_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "scenario",
        "detector",
        "precision",
        "recall",
        "f1",
        "specificity",
        "false_positive_rate",
        "avg_detection_latency_ms",
        "true_positive",
        "false_positive",
        "false_negative",
        "true_negative",
        "runs",
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
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_results_json(
    path: Path,
    runs: int,
    scenarios: list[str],
    detectors: list[str],
    metrics: list[dict[str, object]],
    run_results: list[RunResult],
) -> None:
    path.write_text(
        json.dumps(
            {
                "runs": runs,
                "scenarios": scenarios,
                "detectors": detectors,
                "metrics": metrics,
                "run_results": [result.__dict__ for result in run_results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_report(
    path: Path,
    runs: int,
    scenarios: list[str],
    detectors: list[str],
    metrics: list[dict[str, object]],
) -> None:
    lines = [
        "# Detector Tournament Benchmark",
        "",
        "Educational synthetic benchmark. These results do not represent real market surveillance performance.",
        "",
        f"- Total scenario runs: {runs}",
        f"- Scenarios: {', '.join(scenarios)}",
        f"- Detectors: {', '.join(detectors)}",
        "",
        "| Scenario | Detector | Precision | Recall | F1 | Specificity | Event recall | Avg Latency ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in metrics:
        latency = row["avg_detection_latency_ms"]
        lines.append(
            f"| {row['scenario']} | {row['detector']} | {_display(row['precision'])} | "
            f"{_display(row['recall'])} | "
            f"{_display(row['f1'])} | {_display(row['specificity'])} | {_display(row['event_recall'])} | "
            f"{latency if latency is not None else 'n/a'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_charts(output_dir: Path, metrics: list[dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_rows = metrics
    _write_bar_chart(
        output_dir / "f1_by_scenario.png",
        [(f"{row['scenario']}:{row['detector']}", float(row["f1"] or 0.0)) for row in expected_rows],
        "F1 by Scenario",
        value_max=1.0,
    )
    _write_bar_chart(
        output_dir / "confidence_distribution.png",
        [(f"{row['scenario']}:{row['detector']}", float(row["precision"] or 0.0)) for row in expected_rows],
        "Precision by Scenario",
        value_max=1.0,
    )
    _write_bar_chart(
        output_dir / "detection_latency.png",
        [
            (str(row["scenario"]), float(row["avg_detection_latency_ms"] or 0.0))
            for row in expected_rows
        ],
        "Detection Latency",
        value_max=None,
    )


def _write_bar_chart(
    path: Path,
    values: list[tuple[str, float]],
    title: str,
    *,
    value_max: float | None,
) -> None:
    width = 920
    height = 420
    image = bytearray([7, 13, 20] * width * height)

    def pixel(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            image[offset : offset + 3] = bytes(color)

    def rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        for y in range(max(0, y0), min(height, y1)):
            for x in range(max(0, x0), min(width, x1)):
                pixel(x, y, color)

    rect(0, 0, width, height, (7, 13, 20))
    for y in range(70, 340, 54):
        rect(80, y, width - 40, y + 1, (27, 52, 77))

    if not values:
        _write_png(path, width, height, bytes(image))
        return

    max_value = value_max or max(value for _, value in values) or 1.0
    bar_width = max(24, min(96, int((width - 140) / max(len(values), 1) * 0.62)))
    gap = int((width - 140 - bar_width * len(values)) / max(len(values), 1))
    x = 90
    for index, (_, value) in enumerate(values):
        bar_height = int(250 * (value / max_value)) if max_value else 0
        color = [(34, 211, 238), (34, 171, 148), (245, 184, 65), (242, 54, 69)][index % 4]
        rect(x, 340 - bar_height, x + bar_width, 340, color)
        rect(x, 340 - bar_height, x + bar_width, 340 - bar_height + 3, (216, 243, 255))
        x += bar_width + max(18, gap)

    # Tiny title stripe. Text labels stay in CSV/report; this PNG is a lightweight visual artifact.
    rect(80, 35, min(width - 40, 80 + len(title) * 9), 41, (34, 211, 238))
    _write_png(path, width, height, bytes(image))


def _write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw_rows = []
    stride = width * 3
    for y in range(height):
        raw_rows.append(b"\x00" + rgb[y * stride : (y + 1) * stride])
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(b"".join(raw_rows), 9)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)


if __name__ == "__main__":
    main()
