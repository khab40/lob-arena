"""Detached stop watchdog for the existing Wave 1 MLflow VM only."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

VM_ID = "computeinstance-e00xq8hqrzks2pf3gn"


def save(path, value):
    """Publish complete private JSON without replacing any existing receipt."""
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Same-directory atomic, exclusive publication.
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass  # Temporary-file cleanup must not replace a publication failure.


def verified_stop(value):
    if not isinstance(value, dict) or value.get("verified_stopped") is not True:
        return False
    observed = value.get("after")
    return isinstance(observed, dict) and observed.get("id") == VM_ID and observed.get("state") == "STOPPED"


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


def stop_verified(call=None):
    call = provider if call is None else call
    attempts = []
    for _ in range(3):
        try:
            response = call("stop")
            attempts.append({"stop_response": response})
            observed = call("get", timeout=15)
            if verified_stop({"verified_stopped": True, "after": observed}):
                return {"verified_stopped": True, "attempts": attempts, "after": observed}
        except Exception as exc:
            attempts.append({"error": type(exc).__name__})
    return {"verified_stopped": False, "attempts": attempts}


def watch(directory, expires, stop=None):
    stop = stop_verified if stop is None else stop
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
    return 0 if verified_stop(receipt) else 1


def await_ready(directory, child, expires):
    limit = time.monotonic() + 5
    while time.monotonic() < limit:
        if child.poll() is not None:
            raise RuntimeError("watchdog exited before startup")
        ready = directory / "watchdog-ready.json"
        if ready.exists():
            try:
                value = json.loads(ready.read_text())
            except (OSError, UnicodeError, ValueError):
                raise ValueError("invalid watchdog handshake") from None
            if not isinstance(value, dict):
                raise ValueError("invalid watchdog handshake")
            if value.get("pid") != child.pid or value.get("expires_monotonic") != expires:
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
        errors, interruptions = [], []

        def failed(stage, exc):
            errors.append({"stage": stage, "error": type(exc).__name__})
            if not isinstance(exc, Exception):
                interruptions.append(exc)

        def retain(name, value):
            try:
                save(directory / name, value)
                return True
            except BaseException as exc:
                failed(name, exc)
                return False

        try:
            (directory / "stop-requested").touch(exist_ok=True)
        except BaseException as exc:
            failed("stop-requested", exc)
        try:
            if child.wait(timeout=190) != 0:
                errors.append({"stage": "watchdog-wait", "error": "NonzeroExit"})
        except subprocess.TimeoutExpired as exc:
            failed("watchdog-wait", exc)
            retain("watchdog-wait-timeout.json", {"at_unix": time.time()})
        except BaseException as exc:
            failed("watchdog-wait", exc)
        try:
            result = json.loads((directory / "watchdog-result.json").read_text(encoding="utf-8"))
        except BaseException as exc:
            failed("watchdog-result", exc)
            result = None
        emergency = None
        if errors or not verified_stop(result):
            try:
                emergency = stop_verified()
            except BaseException as exc:
                failed("emergency-stop", exc)
                emergency = {"verified_stopped": False}
            retain("emergency-stop.json", emergency)
        retained = not errors or retain("watchdog-cleanup-errors.json", {"errors": errors, "emergency": emergency})
        if emergency is not None and not verified_stop(emergency):
            raise RuntimeError("VM stop unverified; immediate operator intervention required")
        if interruptions:
            raise interruptions[0]
        if not retained and sys.exc_info()[0] is None:
            raise RuntimeError("VM stopped; shutdown evidence could not be retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--expires", required=True, type=float)
    args = parser.parse_args()
    if not 0 < args.expires - time.monotonic() <= 600:
        raise ValueError("invalid watchdog deadline")
    raise SystemExit(watch(args.directory, args.expires))
