import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.features.io import (  # noqa: E402
    fetch_events,
    load_config,
    load_events_jsonl,
    load_labels,
    load_run_metadata,
    write_feature_run,
)
from app.features.pipeline import FeaturePipeline  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate versioned causal LOB features from canonical exchange events."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--events", type=Path, help="Canonical exchange-event JSONL")
    source.add_argument(
        "--events-url",
        help="Paginated /api/arena/exchange-events endpoint for the current Java run",
    )
    parser.add_argument(
        "--metadata", type=Path, required=True, help="Feature run metadata JSON"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "features" / "lightgbm-v1.json",
        help="Versioned feature configuration JSON",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="Separate feature_labels_v1 or scenario ground truth JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    metadata = load_run_metadata(args.metadata)
    labels = load_labels(args.labels)
    events = (
        load_events_jsonl(args.events)
        if args.events is not None
        else fetch_events(args.events_url, timeout=args.timeout)
    )
    result = FeaturePipeline(config, metadata, labels).generate(events)
    manifest = write_feature_run(
        args.output,
        result=result,
        config=config,
        metadata=metadata,
        overwrite=args.overwrite,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if config.fail_on_invalid_rows and result.quality_report["invalid_row_count"]:
        print(
            "feature generation completed with invalid rows; inspect feature-quality.json",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
