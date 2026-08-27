#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.ml.lightgbm.cloud_runner import execute_wave1_request, verify_wave1_result
from app.ml.lightgbm.cloud_transport import DEFAULT_ENDPOINT_URL, execute_wave1_s3
from app.nebius.job_logging import JobLogger


JOB_LOG = JobLogger("lightgbm-wave1")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or verify a governed LightGBM Wave 1 request.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--input-root", type=Path, required=True)
    run_s3 = subparsers.add_parser("run-s3")
    run_s3.add_argument("--input-uri", required=True)
    run_s3.add_argument("--work-root", type=Path, default=Path("/job/wave1"))
    run_s3.add_argument("--request-relative-path", default="request.json")
    run_s3.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    JOB_LOG.info(
        "entrypoint.started",
        "Dispatch the requested governed LightGBM operation and report its lifecycle as structured events.",
        command=args.command,
    )
    if args.command == "run":
        result = execute_wave1_request(args.request, input_root=args.input_root)
    elif args.command == "run-s3":
        result = execute_wave1_s3(
            args.input_uri,
            work_root=args.work_root,
            endpoint_url=args.endpoint_url,
            request_relative_path=args.request_relative_path,
        )
    else:
        result = verify_wave1_result(args.result).model_dump_json(indent=2)
    JOB_LOG.info(
        "entrypoint.completed",
        "The requested governed LightGBM operation completed successfully.",
        command=args.command,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
