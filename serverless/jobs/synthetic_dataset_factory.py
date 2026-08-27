import argparse
import json
import sys
from pathlib import Path
from typing import Any


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
from app.nebius.job_logging import JobLogger  # noqa: E402


SCENARIOS = ["spoofing-like", "layering-like", "quote-stuffing", "liquidity-evaporation"]
JOB_LOG = JobLogger("synthetic-dataset")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate labeled synthetic arena dataset artifacts.")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("outputs/synthetic-dataset"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    events_path = args.output / "events.jsonl"
    incidents_path = args.output / "incidents.jsonl"
    labels_path = args.output / "labels.jsonl"
    snapshot_rows: list[dict[str, Any]] = []
    JOB_LOG.info(
        "dataset.started",
        "Generate deterministic labeled synthetic market-abuse samples and order-book snapshots.",
        sample_count=args.samples,
        scenario_count=len(SCENARIOS),
    )

    with (
        events_path.open("w", encoding="utf-8") as events_file,
        incidents_path.open("w", encoding="utf-8") as incidents_file,
        labels_path.open("w", encoding="utf-8") as labels_file,
    ):
        for sample_index in range(args.samples):
            scenario = SCENARIOS[sample_index % len(SCENARIOS)]
            sample = _generate_sample(sample_index, scenario)
            for event in sample["events"]:
                events_file.write(json.dumps(event) + "\n")
            for incident in sample["incidents"]:
                incidents_file.write(json.dumps(incident) + "\n")
            labels_file.write(json.dumps(sample["label"]) + "\n")
            snapshot_rows.extend(sample["snapshots"])

    JOB_LOG.info(
        "samples.completed",
        "All synthetic scenarios completed; write snapshot and manifest artifacts next.",
        sample_count=args.samples,
        snapshot_count=len(snapshot_rows),
    )
    snapshot_artifact = _write_snapshots(args.output, snapshot_rows)
    manifest = {
        "samples": args.samples,
        "events": str(events_path),
        "incidents": str(incidents_path),
        "labels": str(labels_path),
        "snapshots": str(snapshot_artifact),
        "format_note": "snapshots use parquet when pandas/pyarrow are available, otherwise JSONL.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    JOB_LOG.info(
        "dataset.completed",
        "The labeled synthetic dataset and manifest are ready for downstream evaluation.",
        sample_count=args.samples,
        snapshot_format=snapshot_artifact.suffix.lstrip("."),
    )
    print(json.dumps(manifest, indent=2))


def _generate_sample(sample_index: int, scenario: str) -> dict[str, Any]:
    engine = SimulationEngine(seed=sample_index + 101)
    engine.launch_scenario(scenario)
    events: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    incidents_by_id: dict[str, dict[str, Any]] = {}
    start_tick = None
    end_tick = None

    for _ in range(12):
        state = engine.step()
        if state["active_scenario"] and start_tick is None:
            start_tick = int(state["active_scenario"]["start_tick"])
        end_tick = int(state["tick"])
        for event in state["events"][:6]:
            event = dict(event)
            event["sample_id"] = f"sample-{sample_index:05d}"
            events.append(event)
        snapshots.append(_snapshot_row(sample_index, scenario, state))
        for incident in state.get("incidents", []):
            incident = dict(incident)
            incident["sample_id"] = f"sample-{sample_index:05d}"
            incidents_by_id[incident["id"]] = incident

    return {
        "events": events,
        "snapshots": snapshots,
        "incidents": list(incidents_by_id.values()),
        "label": {
            "sample_id": f"sample-{sample_index:05d}",
            "scenario": scenario,
            "scenario_family": scenario.replace("-", "_"),
            "start_tick": start_tick,
            "end_tick": end_tick,
            "has_incident": bool(incidents_by_id),
        },
    }


def _snapshot_row(sample_index: int, scenario: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": f"sample-{sample_index:05d}",
        "scenario": scenario,
        "tick": state["tick"],
        "best_bid": state["best_bid"],
        "best_ask": state["best_ask"],
        "mid": state["mid"],
        "spread": state["spread"],
        "top_bids": state["book"]["bids"][:5],
        "top_asks": state["book"]["asks"][:5],
        "features": state.get("features", {}),
        "detectors": state["detectors"]["scores"],
    }


def _write_snapshots(output_dir: Path, rows: list[dict[str, Any]]) -> Path:
    try:
        import pandas as pd  # type: ignore

        path = output_dir / "snapshots.parquet"
        pd.DataFrame(rows).to_parquet(path)
        return path
    except (ImportError, ModuleNotFoundError, ValueError, RuntimeError):
        path = output_dir / "snapshots.parquet.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        return path


if __name__ == "__main__":
    main()
