"""Monitor one existing audit Job; transient log errors cannot erase startup proof."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def decision(*, elapsed, launcher_seen, log_output):
    records = []
    if log_output is not None:
        for line in log_output.splitlines():
            try:
                records.append(json.loads(line[line.index("{"):]))
            except (ValueError, json.JSONDecodeError):
                pass
    seen = launcher_seen or any(
        r.get("schema_version") == "g8_audit_supervisor_v1" and r.get("stage") == "launcher_started"
        for r in records if isinstance(r, dict))
    reason = "supervisor_deadline" if elapsed > 3060 else (
        "startup_deadline" if elapsed > 300 and not seen else None)
    progress = [r for r in records if isinstance(r, dict) and r.get("schema_version") == "g8_comparison_progress_v1"]
    return seen, reason, progress[-1] if progress else None


def provider(args):
    try:
        response = subprocess.run(["rtk", "proxy", "nebius", *args,
            "--format", "json", "--retries", "1", "--no-browser"],
            capture_output=True, text=True, timeout=30)
        return response.stdout if response.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return None


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def monitor(directory, job_id):
    if not job_id.startswith("aijob-") or directory.is_symlink():
        raise ValueError("explicit Job identity and canonical evidence directory required")
    seen, started, index = False, time.monotonic(), 0
    # Resume only the same evidence history; a log outage cannot reset the latch.
    for path in sorted(directory.glob("watch-*.json")):
        old = json.loads(path.read_text())
        if old["job_id"] != job_id:
            raise ValueError("monitor history belongs to another Job")
        seen = seen or old["launcher_seen"]
        index += 1
    while time.monotonic() - started < 4200:
        raw = provider(["ai", "job", "get", "--id", job_id])
        logs = provider(["ai", "job", "logs", job_id, "--since", "2h", "--tail", "500"])
        job = json.loads(raw) if raw else None
        if job and job["metadata"]["id"] != job_id:
            raise ValueError("provider returned another Job")
        timestamp = job["status"].get("started_at") if job else None
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds() if timestamp else 0
        seen, reason, progress = decision(elapsed=elapsed, launcher_seen=seen, log_output=logs)
        state = job["status"]["state"] if job else "READ_UNAVAILABLE"
        save(directory / f"watch-{index:03d}.json", {"job_id": job_id,
            "observed_at": datetime.now(timezone.utc).isoformat(), "job": job, "logs": logs,
            "launcher_seen": seen, "elapsed_seconds": elapsed, "cancellation_reason": reason})
        print(json.dumps({"state": state, "elapsed": round(elapsed),
                          "launcher_seen": seen, "progress": progress}), flush=True)
        if state in {"COMPLETED", "FAILED", "CANCELLED"} and not job["status"].get("instances"):
            if logs is None:
                time.sleep(15)
                index += 1
                continue  # Released compute; collect real logs, never an API error as success evidence.
            save(directory / "job-final.json", job)
            save(directory / "job-logs.json", logs)
            return
        if reason and state not in {"COMPLETED", "FAILED", "CANCELLED"}:
            result = provider(["ai", "job", "cancel", "--id", job_id])
            save(directory / f"cancellation-{index:03d}.json", {"reason": reason, "response": result})
        index += 1
        time.sleep(30)
    result = provider(["ai", "job", "cancel", "--id", job_id])
    save(directory / "monitor-deadline.json", {"response": result})
    raise TimeoutError("monitor deadline; cancellation requested, independent readback required")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    arguments = parser.parse_args()
    monitor(arguments.directory.resolve(), arguments.job_id)
