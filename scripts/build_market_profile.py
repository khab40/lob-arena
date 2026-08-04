#!/usr/bin/env python3
"""Build market_profile_v1 and an optional held-out realism report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.calibration.market_profile import (  # noqa: E402
    build_realism_report,
    extract_market_profile,
    write_json_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--profile-id")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--held-out-dataset-dir", type=Path)
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    if bool(args.held_out_dataset_dir) != bool(args.report_output):
        parser.error("--held-out-dataset-dir and --report-output must be supplied together")
    return args


def main() -> int:
    args = parse_args()
    profile = extract_market_profile(args.dataset_dir, profile_id=args.profile_id)
    write_json_artifact(profile, args.output)
    result: dict[str, object] = {
        "profile": str(args.output),
        "profile_sha256": profile["profile_sha256"],
    }
    if args.held_out_dataset_dir:
        report = build_realism_report(profile, args.held_out_dataset_dir)
        write_json_artifact(report, args.report_output)
        result.update(
            report=str(args.report_output),
            report_sha256=report["report_sha256"],
            completion_gate_passed=report["completion_gate_passed"],
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
