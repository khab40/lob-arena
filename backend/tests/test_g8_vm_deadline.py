"""Stop-guard tests with injected CLI/clock; no cloud calls or sleeping."""
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts import g8_vm_deadline as guard


def lease(directory, deadline):
    guard.record(directory / "lease.json", {"vm_id": guard.VM, "deadline": deadline.isoformat()})


def test_expired_deadline_stops_and_independently_verifies(tmp_path, monkeypatch):
    lease(tmp_path, datetime.now(UTC) - timedelta(seconds=1))
    calls = []
    states = iter(("RUNNING", "STOPPING", "STOPPED"))

    def cli(action):
        calls.append(action)
        return {"action": action, "returncode": 0, "state": next(states)}

    monkeypatch.setattr(guard, "cli", cli)
    guard.watch(tmp_path)
    assert calls == ["get", "stop", "get"]
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert events[-1]["state"] == "STOPPED"


def test_network_failure_retries_without_claiming_stop(tmp_path, monkeypatch):
    lease(tmp_path, datetime.now(UTC) - timedelta(seconds=1))
    attempts = []
    sleeps = []

    def cli(action):
        attempts.append(action)
        if len(attempts) == 1:
            raise OSError("synthetic network failure")
        return {"action": action, "returncode": 0, "state": "STOPPED"}

    monkeypatch.setattr(guard, "cli", cli)
    monkeypatch.setattr(guard.time, "sleep", sleeps.append)
    guard.watch(tmp_path)
    assert attempts == ["get", "get"] and sleeps == [30]
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert events[1] == {"event": "retry", "error_type": "OSError"}


def test_monotonic_budget_cannot_be_extended(tmp_path, monkeypatch):
    lease(tmp_path, datetime.now(UTC) + timedelta(seconds=10))
    clock = iter((0, 0, 11))
    calls = []
    monkeypatch.setattr(guard.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))

    def cli(action):
        calls.append((action, None))
        return {"action": action, "state": "STOPPED", "returncode": 0}

    monkeypatch.setattr(guard, "cli", cli)
    guard.watch(tmp_path)
    assert calls[0][0] == "sleep" and 0 < calls[0][1] <= 10
    assert calls[1] == ("get", None)


@pytest.mark.parametrize("hours", [-1, 0])
def test_expired_arm_rejected(tmp_path, hours):
    with pytest.raises(ValueError, match="in the future"):
        guard.arm(tmp_path / "new", datetime.now(UTC) + timedelta(hours=hours))


def test_arm_requires_stopped_vm_before_start(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "cli", lambda _: {"state": "RUNNING"})
    with pytest.raises(ValueError, match="before starting"):
        guard.arm(tmp_path / "new", datetime.now(UTC) + timedelta(hours=2))
    assert not (tmp_path / "new").exists()


def test_start_checks_live_guard_and_persists_single_start_intent(tmp_path, monkeypatch):
    deadline = datetime.now(UTC) + timedelta(hours=2, minutes=30)
    lease(tmp_path, deadline)
    guard.record(tmp_path / "events.jsonl", {"event": "armed", "pid": 123, "deadline": deadline.isoformat()})
    calls = []
    monkeypatch.setattr(guard.os, "kill", lambda pid, signal: calls.append((pid, signal)))

    def cli(action):
        calls.append(action)
        if action == "start":
            assert (tmp_path / "start-intent.json").is_file()
        return {"state": "STOPPED" if action == "get" else "RUNNING"}

    monkeypatch.setattr(guard, "cli", cli)
    assert guard.start(tmp_path)["state"] == "RUNNING"
    with pytest.raises(FileExistsError):
        guard.start(tmp_path)
    assert calls.count("start") == 1 and calls[0] == (123, 0)


def test_delayed_approval_cannot_start_after_guard_deadline(tmp_path, monkeypatch):
    deadline = datetime.now(UTC) - timedelta(seconds=1)
    lease(tmp_path, deadline)
    guard.record(tmp_path / "events.jsonl", {"event": "armed", "pid": 123, "deadline": deadline.isoformat()})
    monkeypatch.setattr(guard, "cli", lambda _: pytest.fail("expired guard must not call the provider"))
    with pytest.raises(ValueError, match="future deadline"):
        guard.start(tmp_path)


def test_operator_managed_start_needs_no_lease_and_never_retries(tmp_path, monkeypatch):
    directory = tmp_path / "start"
    calls = []

    def cli(action):
        calls.append(action)
        if action == "start":
            intent = json.loads((directory / "start-intent.json").read_text())
            assert intent["spend_monitoring"] == "operator_managed_alerts"
            assert "deadline" not in intent
            raise TimeoutError("ambiguous provider response")
        return {"state": "STOPPED"}

    monkeypatch.setattr(guard, "cli", cli)
    with pytest.raises(TimeoutError):
        guard.start(directory, operator_managed=True)
    with pytest.raises(FileExistsError):
        guard.start(directory, operator_managed=True)
    assert calls.count("start") == 1


def test_operator_managed_start_does_not_touch_running_vm(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "cli", lambda _: {"state": "RUNNING"})
    with pytest.raises(ValueError, match="stopped"):
        guard.start(tmp_path / "start", operator_managed=True)
    assert not (tmp_path / "start").exists()
