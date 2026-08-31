#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.market_data.preparation import execute_preparation, execute_preparation_s3
from app.market_data.public_sample import OBJECT_STORAGE_ENDPOINT
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import verify_complete_result


JOB_LOG = JobLogger("market-data-preparation")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded Nasdaq normalization, replay, and feature preparation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    local = subparsers.add_parser("prepare-local")
    local.add_argument("--request", type=Path, required=True)
    local.add_argument("--source-root", type=Path, required=True)
    local.add_argument("--result", type=Path, required=True)
    local.add_argument("--java-base-url", default="http://127.0.0.1:8080")
    cloud = subparsers.add_parser("prepare-s3")
    cloud.add_argument("--input-uri", required=True)
    cloud.add_argument("--work-root", type=Path, default=Path("/job/market-data-prepare"))
    cloud.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    cloud.add_argument("--java-jar", type=Path, default=Path("/job/java/control-plane.jar"))
    verify = subparsers.add_parser("verify-local")
    verify.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    JOB_LOG.info(
        "entrypoint.started",
        "Dispatch bounded C3/C4 normalization, Java replay, and feature preparation.",
        command=args.command,
    )
    if args.command == "prepare-local":
        result = execute_preparation(
            args.request,
            source_root=args.source_root,
            result_root=args.result,
            java_base_url=args.java_base_url,
        )
    elif args.command == "prepare-s3":
        result = execute_preparation_s3(
            args.input_uri,
            work_root=args.work_root,
            java_jar=args.java_jar,
            endpoint_url=args.endpoint_url,
        )
    else:
        result = verify_complete_result(args.result).model_dump(mode="json")
    JOB_LOG.info(
        "entrypoint.completed",
        "The bounded C3/C4 market-data preparation completed successfully.",
        command=args.command,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
