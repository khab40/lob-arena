"""Inert process lifecycle tests; never contact Nebius."""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "scripts/nebius_mlflow_watchdog.py"
SPEC = importlib.util.spec_from_file_location("watchdog", SOURCE)
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


def test_detached_watchdog_stops_after_parent_exits(tmp_path):
    code = ("import importlib.util,pathlib,time; "
            f"s=importlib.util.spec_from_file_location('w',{str(SOURCE)!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            f"m.watch(pathlib.Path({str(tmp_path)!r}),time.monotonic()+.2,"
            "stop=lambda:{'verified_stopped':True,'inert':True})")
    parent = ("import subprocess,sys; "
              f"subprocess.Popen([sys.executable,'-c',{code!r}],start_new_session=True,"
              "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)")
    subprocess.run([sys.executable, "-c", parent], check=True, timeout=5)
    limit = time.monotonic() + 5
    target = tmp_path / "watchdog-result.json"
    while not target.exists() and time.monotonic() < limit:
        time.sleep(.05)
    result = json.loads(target.read_text())
    assert result["reason"] == "deadline"
    assert result["verified_stopped"] and result["inert"]


def test_stop_requested_exits_before_deadline(tmp_path):
    (tmp_path / "stop-requested").touch()
    assert watchdog.watch(tmp_path, time.monotonic() + 600,
                          stop=lambda: {"verified_stopped": True}) == 0
    assert json.loads((tmp_path / "watchdog-result.json").read_text())["reason"] == "requested"


def test_stop_requires_readback_and_bounds_retries():
    calls = []
    def provider(action, timeout=45):
        calls.append((action, timeout))
        return {"state": "STOPPED" if len(calls) == 4 else "STOPPING"}
    result = watchdog.stop_verified(provider)
    assert result["verified_stopped"]
    assert calls == [("stop", 45), ("get", 15), ("stop", 45), ("get", 15)]
    def broken(*args, **kwargs):
        raise RuntimeError("sensitive provider response must not be retained")
    result = watchdog.stop_verified(broken)
    assert not result["verified_stopped"] and len(result["attempts"]) == 3
    assert "sensitive" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["arm", "start", "body", "none"])
def test_cleanup_on_every_session_path(tmp_path, monkeypatch, failure):
    directory = tmp_path / "session"
    calls = []
    def provider(action, timeout=45):
        calls.append(action)
        if action == "start" and failure == "start":
            raise RuntimeError("start failed")
        return {"id": watchdog.VM_ID, "state": "STOPPED" if action == "get" else "RUNNING",
                "resources": {"platform": "cpu-e2", "preset": "2vcpu-8gb"}}
    class Child:
        pid = 123
        def wait(self, timeout):
            assert (directory / "stop-requested").exists()
            watchdog.save(directory / "watchdog-result.json", {"verified_stopped": True})
    def ready(*args):
        if failure == "arm":
            raise RuntimeError("handshake failed")
    monkeypatch.setattr(watchdog, "provider", provider)
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(watchdog, "await_ready", ready)
    def run():
        with watchdog.bounded_vm(directory):
            if failure == "body":
                raise RuntimeError("read failed")
    if failure == "none":
        run()
    else:
        with pytest.raises(RuntimeError):
            run()
    assert ("start" in calls) == (failure != "arm")
    assert json.loads((directory / "watchdog-result.json").read_text())["verified_stopped"]


def test_running_vm_is_never_adopted(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "provider", lambda *a: {"state": "RUNNING"})
    with pytest.raises(ValueError, match="stopped"):
        with watchdog.bounded_vm(tmp_path / "session"):
            pytest.fail("must not enter")


def test_dead_watchdog_prevents_start(tmp_path):
    class Child:
        def poll(self):
            return 1
    with pytest.raises(RuntimeError, match="exited"):
        watchdog.await_ready(tmp_path, Child(), time.monotonic() + 600)


def test_provider_timeout_kills_the_entire_cli_process_group(monkeypatch):
    class Child:
        pid = 456
        calls = 0
        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("inert", timeout)
            return "", ""
    child = Child()
    killed = []
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(watchdog.os, "killpg", lambda *args: killed.append(args))
    with pytest.raises(subprocess.TimeoutExpired):
        watchdog.provider("get", timeout=1)
    assert killed == [(456, watchdog.signal.SIGKILL)]
    assert child.calls == 2
