"""Supervise one attester; never create/cancel Jobs or restart the helper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process_identity(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                            capture_output=True, text=True, timeout=2, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def save(path, value):
    temporary = path.with_suffix(".next")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    temporary.replace(path)


def inspect(output, proposal_sha256, request_sha256, *, now=time.time, identity=process_identity):
    status = json.loads((output / "status.json").read_bytes())
    binding = status["binding"]
    if (binding["proposal_sha256"] != proposal_sha256 or binding["request_sha256"] != request_sha256
            or any(sha(binding[key + "_path"]) != binding[key + "_sha256"]
                   for key in ("proposal", "request", "operator"))):
        raise ValueError("supervisor binding differs")
    status["admission_ready"] = False
    if status["state"] not in ("delivered", "failed"):
        if not 0 <= now() - status["updated_at"] <= 3:
            raise ValueError("supervisor heartbeat expired")
        for name in ("supervisor", "attester"):
            if not status[name + "_start"] or identity(status[name + "_pid"]) != status[name + "_start"]:
                raise ValueError("supervised process identity is no longer live")
        status["admission_ready"] = (status["state"] == "ready" and not status["admission_closed"]
            and now() <= status["admission_expires_at"])
    return status


def supervise(command, output, binding, ready_seconds, seconds, *, spawn=subprocess.Popen,
              now=time.time, pause=time.sleep, identity=process_identity):
    output.mkdir(parents=True, exist_ok=False)  # A consumed attempt is never restarted.
    child, status = None, {"binding": binding, "state": "starting", "supervisor_pid": os.getpid(),
        "supervisor_start": identity(os.getpid()), "admission_ready": False, "admission_closed": False}
    started, ready_at, ready_event, buffer = now(), None, False, ""
    terminal, published = None, False
    try:
        with (output / "attester.jsonl").open("x") as log, (output / "attester.stderr").open("x") as errors:
            child = spawn(command, stdout=log, stderr=errors, start_new_session=True)
            status.update(attester_pid=child.pid, attester_start=identity(child.pid))
            with (output / "attester.jsonl").open() as reader:
                while True:
                    code = child.poll()
                    buffer += reader.read()
                    if reader.tell() > 1024 * 1024:
                        raise ValueError("attester output bound exceeded")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        record = json.loads(line)
                        event = record.get("event")
                        if event and record.get("evidence_status") != "progress_not_independent_verification":
                            raise ValueError("unverified attester progress format")
                        if event == "attester_ready":
                            if record.get("stage") != "provider_read":
                                raise ValueError("unexpected attester ready stage")
                            ready_event = True
                        elif event == "attester_waiting":
                            if record.get("stage") == "intent_read":
                                status["admission_closed"] = True
                            if ready_event and not status["admission_closed"] and record.get("stage") == "provider_read":
                                if ready_at is None:
                                    ready_at = now()
                                status.update(state="ready", admission_expires_at=ready_at + ready_seconds)
                            else:
                                status["state"] = "attesting"
                        elif event in ("provider_observed", "context_publication_started", "context_published"):
                            expected = "provider_validation" if event == "provider_observed" else "context_publish"
                            if record.get("stage") != expected:
                                raise ValueError("unexpected attester observation/publication stage")
                            published = published or event == "context_published"
                            status.update(state="attesting", admission_closed=True)
                        elif record.get("context_delivered") is True or record.get("status") == "failed":
                            if terminal is not None:
                                raise ValueError("duplicate attester terminal output")
                            terminal = record
                            if record.get("status") == "failed":
                                raise RuntimeError("attester failed")
                        else:
                            raise ValueError("unexpected attester output")
                    if code is not None:
                        if (code != 0 or buffer or not published or not terminal
                                or terminal.get("context_delivered") is not True
                                or not re.fullmatch(r"aijob-[a-z0-9]+", terminal.get("job_id", ""))):
                            raise RuntimeError("attester did not deliver context")
                        status.update(state="delivered", job_id=terminal["job_id"], exit_code=code)
                    elif now() - started >= seconds or ready_at is None and now() - started >= ready_seconds:
                        raise TimeoutError("attester supervision deadline expired")
                    status["updated_at"] = now()
                    save(output / "status.json", status)
                    if status["state"] == "ready" and not (output / "readiness.json").exists():
                        save(output / "readiness.json", status)
                    if code is not None:
                        return 0
                    pause(0.25)
    except Exception as error:
        status.update(state="failed", error_type=type(error).__name__, updated_at=now())
        if terminal and terminal.get("status") == "failed":
            status["attester_failure"] = {key: terminal.get(key) for key in
                ("stage", "error_type", "cause_type", "frames", "cause_frames")}
        save(output / "status.json", status)
        return 1
    finally:
        # Only the live child owned by this invocation; never act on a saved PID.
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
            except ProcessLookupError:
                child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "inspect"))
    for name in ("output", "proposal-sha256", "request-sha256"):
        parser.add_argument("--" + name, required=True)
    for name in ("proposal", "evidence", "slot", "operator", "operator-sha256", "operator-python"):
        parser.add_argument("--" + name)
    parser.add_argument("--ready-seconds", type=int, default=120)
    parser.add_argument("--custody")
    args = parser.parse_args()
    if args.action == "inspect":
        print(json.dumps(inspect(Path(args.output), args.proposal_sha256, args.request_sha256)))
        return 0
    if not all((args.proposal, args.evidence, args.slot, args.operator, args.operator_sha256, args.operator_python)):
        parser.error("run requires proposal, evidence, slot and pinned operator arguments")
    request_path = Path(args.evidence) / args.slot / "request.json"
    binding = {"proposal_path": str(Path(args.proposal).resolve()), "proposal_sha256": args.proposal_sha256,
        "request_path": str(request_path.resolve()), "request_sha256": args.request_sha256,
        "operator_path": str(Path(args.operator).resolve()), "operator_sha256": args.operator_sha256}
    if any(sha(binding[key + "_path"]) != binding[key + "_sha256"] for key in ("proposal", "request", "operator")):
        raise ValueError("reviewed supervisor input changed")
    request = json.loads(request_path.read_bytes())
    seconds = request["resources"]["timeout_seconds"]
    if request["slot"] != args.slot or seconds != 7200 or not 1 <= args.ready_seconds <= 120:
        raise ValueError("supervisor escaped confirmation bounds")
    binding.update(slot=args.slot, run_id=request["run_id"])
    command = [args.operator_python, "-u", args.operator, "attest", "--evidence", args.evidence, "--slot", args.slot]
    if args.custody:
        binding["custody_path"] = str(Path(args.custody).resolve())
        command.extend(["--custody", binding["custody_path"]])
    return supervise(command, Path(args.output), binding, args.ready_seconds, seconds)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), flush=True)
        sys.exit(1)
