"""Independent operator-side stop guard for the existing G8 MLflow VM.

Arm before starting the VM. This is orchestration, never a model rehearsal.
The operator host must remain online; CLI/network failures are recorded and retried.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

VM = "computeinstance-e00xq8hqrzks2pf3gn"


def record(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def cli(action):
    result = subprocess.run(["nebius", "compute", "instance", action, "--id", VM, "--format", "json",
                             "--no-browser", "--timeout", "30s", "--auth-timeout", "30s", "--retries", "1"],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45)
    if result.returncode:
        return {"action": action, "returncode": result.returncode, "state": None}
    value = json.loads(result.stdout)
    if value.get("metadata", {}).get("id") != VM:
        raise ValueError("stop guard received a different VM")
    return {"action": action, "returncode": 0, "state": value.get("status", {}).get("state")}


def watch(directory):
    lease = json.loads((directory / "lease.json").read_text())
    deadline = datetime.fromisoformat(lease["deadline"])
    if lease["vm_id"] != VM or deadline.tzinfo is None:
        raise ValueError("exact VM and timezone-aware deadline required")
    # Absolute time catches suspension/clock jumps; monotonic time prevents a
    # clock correction from extending the original three-hour stop budget.
    remaining = min(10800, max(0, (deadline - datetime.now(UTC)).total_seconds()))
    end = time.monotonic() + remaining
    record(directory / "events.jsonl", {"event": "armed", "pid": os.getpid(), "deadline": deadline.isoformat()})
    while True:
        remaining = min(end - time.monotonic(), (deadline - datetime.now(UTC)).total_seconds())
        if remaining <= 0:
            break
        time.sleep(min(30, remaining))
    while True:
        try:
            observed = cli("get")
            if observed["state"] != "STOPPED":
                record(directory / "events.jsonl", cli("stop"))
                observed = cli("get")
            record(directory / "events.jsonl", {**observed, "observed_at": datetime.now(UTC).isoformat()})
            if observed["state"] == "STOPPED":
                return
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            record(directory / "events.jsonl", {"event": "retry", "error_type": type(error).__name__})
        time.sleep(30)


def arm(directory, deadline):
    now = datetime.now(UTC)
    if deadline.tzinfo is None or not now < deadline <= now + timedelta(hours=3):
        raise ValueError("stop deadline must be within three hours, preserving one-hour headroom")
    if directory.absolute() != directory.resolve():
        raise ValueError("canonical guard directory required")
    if cli("get")["state"] != "STOPPED":
        raise ValueError("arm the guard before starting the stopped VM")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    record(directory / "lease.json", {"vm_id": VM, "deadline": deadline.isoformat(), "armed_at": now.isoformat()})
    with (directory / "process.log").open("xb") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "watch", "--directory", str(directory)],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("stop guard exited before arming")
        events = directory / "events.jsonl"
        if events.is_file() and any(json.loads(line).get("event") == "armed" for line in events.read_text().splitlines()):
            return {"vm_id": VM, "guard_pid": process.pid, "deadline": deadline.isoformat(), "armed": True}
        time.sleep(0.1)
    raise RuntimeError("stop guard did not acknowledge; do not start the VM")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("arm", "watch"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--deadline", type=datetime.fromisoformat)
    args = parser.parse_args()
    if args.action == "arm":
        if args.deadline is None:
            parser.error("arm requires --deadline")
        print(json.dumps(arm(args.directory, args.deadline), sort_keys=True))
    else:
        watch(args.directory)
