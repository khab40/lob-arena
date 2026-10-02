"""Inert guest-boot timing and redaction checks; no SSH or cloud calls."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "scripts/mlflow_readiness_guest.py"
SPEC = importlib.util.spec_from_file_location("guest", SOURCE)
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


def probe(ready=False, **values):
    return json.dumps({"ssh_reachable": True, "sudo_status": "allowed", "docker_status": "available",
                       "app_status": "running" if ready else "restarting", "app_running": ready,
                       "db_status": "running", "db_running": True, **values}).encode()


class Clock:
    value = 0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


def test_delayed_guest_after_old_45_second_cutoff_is_observed():
    clock, records = Clock(), []
    def run(args, **kwargs):
        assert kwargs["input"] == guest.PROBE.encode() and kwargs["timeout"] <= 10
        clock.value += 9
        return SimpleNamespace(returncode=0, stdout=probe(clock.value > 45), stderr=b"private sentinel")
    result = guest.wait_for_guest(["inert"], expires=600, record=records.append,
                                  now=clock.now, sleep=clock.sleep, run=run)
    assert 45 < result["elapsed_seconds"] < 90 and result["ready"]
    assert any(row["app_status"] == "restarting" for row in records)
    assert "private sentinel" not in json.dumps(records)


@pytest.mark.parametrize("stderr,code", [(b"Permission denied (publickey). secret", "ssh_authentication_failed"),
                                        (b"Host key verification failed. secret", "ssh_host_key_failed")])
def test_authentication_and_host_key_failures_abort_first_poll(stderr, code):
    clock, records = Clock(), []
    def run(*args, **kwargs):
        return SimpleNamespace(returncode=255, stdout=b"", stderr=stderr)
    with pytest.raises(guest.ReadinessError) as error:
        guest.wait_for_guest([], expires=600, record=records.append, now=clock.now, sleep=clock.sleep, run=run)
    assert error.value.failure_code == code and len(records) == 1
    assert "secret" not in json.dumps(records)


@pytest.mark.parametrize("expires,code,elapsed", [(600, "guest_readiness_timeout", 90),
                                                (460, "guest_reserve_exhausted", 25)])
def test_missing_guest_preserves_global_reserve(expires, code, elapsed):
    clock, records = Clock(), []
    def run(*args, **kwargs):
        clock.value += kwargs["timeout"]
        raise subprocess.TimeoutExpired("private command", kwargs["timeout"], output=b"", stderr=b"secret")
    with pytest.raises(guest.ReadinessError) as error:
        guest.wait_for_guest([], expires=expires, record=records.append, now=clock.now, sleep=clock.sleep, run=run)
    assert error.value.failure_code == code and clock.value == elapsed
    assert records[-1]["event"] == "deadline" and expires-clock.value >= 435
    assert "secret" not in json.dumps(records)


def test_partial_timeout_keeps_safe_ssh_and_sudo_progress():
    clock, records = Clock(), []
    def run(*args, **kwargs):
        clock.value += 10
        raw = probe(sudo_status="allowed", docker_status="timed_out") + b'\n{"partial'
        raise subprocess.TimeoutExpired("private", 10, output=raw)
    with pytest.raises(guest.ReadinessError):
        guest.wait_for_guest([], expires=446, record=records.append, now=clock.now, sleep=clock.sleep, run=run)
    assert records[0]["ssh_reachable"] and records[0]["sudo_status"] == "allowed"
    assert records[0]["docker_status"] == "timed_out" and records[0]["poll_timed_out"]


def test_injected_probe_fields_are_never_retained():
    clock, records = Clock(), []
    def run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=probe(password="sentinel"), stderr=b"")
    with pytest.raises(guest.ReadinessError, match="invalid_readiness_response"):
        guest.wait_for_guest([], expires=600, record=records.append, now=clock.now, sleep=clock.sleep, run=run)
    assert "sentinel" not in json.dumps(records)
