#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.market_data.acquisition import execute_acquisition, execute_acquisition_s3
from app.market_data.public_sample import OBJECT_STORAGE_ENDPOINT, execute_c0_preflight, execute_c0_s3
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import verify_complete_result


JOB_LOG = JobLogger("market-data-acquisition")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded Nasdaq connectivity preflight or source acquisition."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    local = subparsers.add_parser("c0-local")
    local.add_argument("--request", type=Path, required=True)
    local.add_argument("--input-root", type=Path, required=True)
    local.add_argument("--result", type=Path, required=True)
    cloud = subparsers.add_parser("c0-s3")
    cloud.add_argument("--input-uri", required=True)
    cloud.add_argument("--work-root", type=Path, default=Path("/job/market-data-c0"))
    cloud.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    acquire_local = subparsers.add_parser("acquire-local")
    acquire_local.add_argument("--request", type=Path, required=True)
    acquire_local.add_argument("--result", type=Path, required=True)
    acquire_cloud = subparsers.add_parser("acquire-s3")
    acquire_cloud.add_argument("--input-uri", required=True)
    acquire_cloud.add_argument(
        "--work-root", type=Path, default=Path("/job/market-data-acquire")
    )
    acquire_cloud.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    verify = subparsers.add_parser("verify-local")
    verify.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    JOB_LOG.info(
        "entrypoint.started",
        "Dispatch a bounded C0 connectivity preflight or C1/C2 source acquisition.",
        command=args.command,
    )
    if args.command == "c0-local":
        result = execute_c0_preflight(
            args.request,
            input_root=args.input_root,
            result_root=args.result,
        )
    elif args.command == "c0-s3":
        result = execute_c0_s3(
            args.input_uri,
            work_root=args.work_root,
            endpoint_url=args.endpoint_url,
        )
    elif args.command == "acquire-local":
        result = execute_acquisition(args.request, result_root=args.result)
    elif args.command == "acquire-s3":
        result = execute_acquisition_s3(
            args.input_uri,
            work_root=args.work_root,
            endpoint_url=args.endpoint_url,
        )
    else:
        result = verify_complete_result(args.result).model_dump(mode="json")
    JOB_LOG.info(
        "entrypoint.completed",
        "The bounded C0/C1/C2 market-data operation completed successfully.",
        command=args.command,
    )
    print(json.dumps(result, sort_keys=True) if isinstance(result, dict) else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
