"""Read-only observer started before submission; never create, restart or cancel."""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time

from app.ml.transformer.research_comparison_contract import is_comparison
from app.ml.transformer.research_context import observed
from app.ml.transformer.research_execution_spec import PROJECT, request_sha, validate
from transformer_confirmation_supervisor import process_identity, save, sha
from transformer_research_operator import cli

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "CANCELED"}
STATES = TERMINAL | {"PROVISIONING", "STARTING", "RUNNING"}


def inspect(output, expected_sha, *, now=time.time, identity=process_identity):
    status = json.loads((output / "status.json").read_bytes())
    if status["request_sha256"] != expected_sha or sha(status["request_path"]) != expected_sha:
        raise ValueError("observer request binding differs")
    status["admission_ready"] = False
    if status["state"] not in ("failed", *TERMINAL):
        if not 0 <= now() - status["observed_at"] <= 30:
            raise ValueError("observer provider observation expired")
        if not status["process_start"] or identity(status["pid"]) != status["process_start"]:
            raise ValueError("observer process identity is no longer live")
        status["admission_ready"] = status["state"] == "absent" and not status["admission_closed"]
    return status


def observe(request, path, output, *, read=cli, now=time.time, pause=time.sleep, identity=process_identity):
    validate(request)
    if not is_comparison(request):
        raise ValueError("observer requires the exact comparison request")
    output.mkdir(parents=True, exist_ok=False)
    started, job_id, starting_at = now(), None, None
    status = {"state": "starting", "request_path": str(path.resolve()),
        "request_sha256": request_sha(request), "pid": os.getpid(), "process_start": identity(os.getpid()),
        "admission_closed": False, "observed_at": started}
    try:
        while True:
            job = read("ai", "job", "get-by-name", "--parent-id", PROJECT, "--name", request["run_id"])
            checked = now()
            status["observed_at"] = checked
            if job is None:
                if job_id or checked - started > 120:
                    raise ValueError("Job disappeared or submission window expired")
                status["state"] = "absent"
            else:
                context = observed(job, request, allowed_states=STATES)
                if job_id and job_id != context["job_id"]:
                    raise ValueError("observer Job identity changed")
                job_id = context["job_id"]
                status.update(state=job["status"]["state"], job_id=job_id, admission_closed=True,
                    provider_status=job["status"], created_at=job["metadata"]["created_at"])
                if status["state"] == "STARTING":
                    if starting_at is None:
                        starting_at = checked
                else:
                    starting_at = None
                created = datetime.fromisoformat(job["metadata"]["created_at"]).astimezone(UTC).timestamp()
                if status["state"] not in TERMINAL and (checked - created > 7200
                        or starting_at is not None and checked - starting_at > 600):
                    raise TimeoutError("provider accounting or startup bound exceeded; operator must reconcile")
            with (output / "observations.jsonl").open("a") as stream:
                stream.write(json.dumps(status, sort_keys=True) + "\n")
            save(output / "status.json", status)
            print(json.dumps({k: status[k] for k in ("state", "observed_at", "admission_closed")}), flush=True)
            if status["state"] in TERMINAL:
                return 0
            pause(10)
    except Exception as error:
        status.update(state="failed", error_type=type(error).__name__, admission_closed=True)
        save(output / "status.json", status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "inspect"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    if args.action == "inspect":
        print(json.dumps(inspect(args.output, args.request_sha256)))
        return 0
    if args.request is None or sha(args.request) != args.request_sha256:
        raise ValueError("observer request file differs")
    return observe(json.loads(args.request.read_bytes()), args.request, args.output)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), flush=True)
        sys.exit(1)
