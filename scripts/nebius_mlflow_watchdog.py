"""Detached stop watchdog for the existing Wave 1 MLflow VM only."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

VM_ID = "computeinstance-e00xq8hqrzks2pf3gn"


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def provider(action, timeout=45):
    if action not in {"get", "start", "stop"}:
        raise ValueError("unsupported VM action")
    child = subprocess.Popen(
        ["rtk", "proxy", "nebius", "compute", "instance", action,
         "--id", VM_ID, "--format", "json", "--no-browser", "--retries", "1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        stdout, _ = child.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.communicate()
        raise
    if child.returncode:
        raise RuntimeError("provider command failed; output redacted")
    value = json.loads(stdout)
    if value["metadata"]["id"] != VM_ID:
        raise ValueError("unexpected VM identity")
    return {"id": VM_ID, "state": value["status"]["state"],
            "resources": value["spec"]["resources"],
            "observed_at_unix": time.time()}


def stop_verified(call=provider):
    attempts = []
    for _ in range(3):
        try:
            response = call("stop")
            attempts.append({"stop_response": response})
            observed = call("get", timeout=15)
            if observed["state"] == "STOPPED":
                return {"verified_stopped": True, "attempts": attempts, "after": observed}
        except Exception as exc:
            attempts.append({"error": type(exc).__name__})
    return {"verified_stopped": False, "attempts": attempts}


def watch(directory, expires, stop=stop_verified):
    save(directory / "watchdog-ready.json", {"pid": os.getpid(), "expires_monotonic": expires})
    reason = "deadline"
    while time.monotonic() < expires:
        if (directory / "stop-requested").exists():
            reason = "requested"
            break
        time.sleep(min(.2, max(0, expires - time.monotonic())))
    receipt = {"reason": reason, "stop_started_at_unix": time.time(), **stop()}
    receipt["completed_at_unix"] = time.time()
    save(directory / "watchdog-result.json", receipt)
    return 0 if receipt["verified_stopped"] else 1


def await_ready(directory, child, expires):
    limit = time.monotonic() + 5
    while time.monotonic() < limit:
        if child.poll() is not None:
            raise RuntimeError("watchdog exited before startup")
        ready = directory / "watchdog-ready.json"
        if ready.exists():
            try:
                value = json.loads(ready.read_text())
            except json.JSONDecodeError:
                continue  # The child is still flushing its tiny handshake.
            if value["pid"] != child.pid or value["expires_monotonic"] != expires:
                raise ValueError("watchdog handshake mismatch")
            if expires - time.monotonic() < 590:
                raise RuntimeError("watchdog startup window expired")
            return
        time.sleep(.05)
    raise TimeoutError("watchdog did not arm")


@contextmanager
def bounded_vm(directory):
    """Arm before start; independent stop begins by ten minutes, even if parent dies."""
    if directory.is_symlink() or directory.resolve() != directory.absolute():
        raise ValueError("noncanonical session directory")
    directory.mkdir(mode=0o700, exist_ok=False)
    before = provider("get")
    if before["state"] != "STOPPED" or before["resources"] != {"platform": "cpu-e2", "preset": "2vcpu-8gb"}:
        raise ValueError("requires the stopped, unchanged MLflow VM")
    save(directory / "vm-before.json", before)
    expires = time.monotonic() + 600
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--directory", str(directory),
         "--expires", str(expires)], start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Prevent idle sleep on the Mac; closing the laptop or losing networking still
    # requires operator intervention. This is not a provider-side billing limit.
    if sys.platform == "darwin":
        subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(child.pid)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        await_ready(directory, child, expires)
        save(directory / "vm-start-request.json", {"at_unix": time.time(), "watchdog_pid": child.pid})
        started = provider("start", timeout=60)
        save(directory / "vm-started.json", started)
        if started["state"] != "RUNNING":
            raise RuntimeError("VM did not reach RUNNING")
        yield expires
    finally:
        (directory / "stop-requested").touch(exist_ok=True)
        try:
            child.wait(timeout=190)
        except subprocess.TimeoutExpired:
            save(directory / "watchdog-wait-timeout.json", {"at_unix": time.time()})
        result = directory / "watchdog-result.json"
        if not result.exists() or not json.loads(result.read_text()).get("verified_stopped"):
            emergency = stop_verified()
            save(directory / "emergency-stop.json", emergency)
            if not emergency["verified_stopped"]:
                raise RuntimeError("VM stop unverified; immediate operator intervention required")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--expires", required=True, type=float)
    args = parser.parse_args()
    if not 0 < args.expires - time.monotonic() <= 600:
        raise ValueError("invalid watchdog deadline")
    raise SystemExit(watch(args.directory, args.expires))
