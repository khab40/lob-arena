"""Inert process lifecycle tests; never contact Nebius."""
import importlib.util
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "scripts/nebius_mlflow_watchdog.py"
SPEC = importlib.util.spec_from_file_location("watchdog", SOURCE)
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)
PROVIDER = watchdog.provider


def stopped():
    return {"verified_stopped": True, "attempts": [],
            "after": {"id": watchdog.VM_ID, "state": "STOPPED"}}


@pytest.fixture(autouse=True)
def forbid_live_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("live provider must never run in watchdog tests")
    monkeypatch.setattr(watchdog, "provider", forbidden)


def test_detached_watchdog_stops_after_parent_exits(tmp_path):
    code = ("import importlib.util,pathlib,time; "
            f"s=importlib.util.spec_from_file_location('w',{str(SOURCE)!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            f"m.watch(pathlib.Path({str(tmp_path)!r}),time.monotonic()+.2,"
            "stop=lambda:{'verified_stopped':True,'inert':True,"
            "'after':{'id':m.VM_ID,'state':'STOPPED'}})")
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
                          stop=stopped) == 0
    assert json.loads((tmp_path / "watchdog-result.json").read_text())["reason"] == "requested"


def test_stop_requires_readback_and_bounds_retries():
    calls = []
    def provider(action, timeout=45):
        calls.append((action, timeout))
        return {"id": watchdog.VM_ID, "state": "STOPPED" if len(calls) == 4 else "STOPPING"}
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
            watchdog.save(directory / "watchdog-result.json", stopped())
            return 0
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
        PROVIDER("get", timeout=1)
    assert killed == [(456, watchdog.signal.SIGKILL)]
    assert child.calls == 2


def test_receipt_publication_is_complete_private_and_create_once(tmp_path, monkeypatch):
    target, value = tmp_path / "receipt.json", {"data": "inert" * 1000}
    partial, resume, published, finish = (threading.Event() for _ in range(4))
    original_dump, original_link, original_sync = json.dump, watchdog.os.link, watchdog.os.fsync
    order = []
    def dump(value, stream, **kwargs):
        stream.write("{")
        stream.flush()
        partial.set()
        assert resume.wait(5)
        stream.seek(0)
        stream.truncate()
        original_dump(value, stream, **kwargs)
    def link(source, destination):
        order.append("link")
        original_link(source, destination)
        published.set()
        assert finish.wait(5)
    def sync(descriptor):
        order.append("sync")
        original_sync(descriptor)
    monkeypatch.setattr(watchdog.json, "dump", dump)
    monkeypatch.setattr(watchdog.os, "link", link)
    monkeypatch.setattr(watchdog.os, "fsync", sync)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(watchdog.save, target, value)
        try:
            assert partial.wait(5) and not target.exists()
            resume.set()
            assert published.wait(5)
            assert json.loads(target.read_text()) == value
            assert target.stat().st_mode & 0o777 == 0o600
        finally:
            resume.set()
            finish.set()
        future.result(timeout=5)
    assert order == ["sync", "link", "sync"]
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        watchdog.save(target, {"replacement": True})
    assert target.read_bytes() == before


def test_process_interruption_never_publishes_partial_receipt(tmp_path):
    target = tmp_path / "receipt.json"
    code = ("import importlib.util,os,pathlib; "
            f"s=importlib.util.spec_from_file_location('w',{str(SOURCE)!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "m.json.dump=lambda value,stream,**kw:(stream.write('{'),stream.flush(),os._exit(7)); "
            f"m.save(pathlib.Path({str(target)!r}),{{'inert':True}})")
    assert subprocess.run([sys.executable, "-c", code], timeout=5).returncode == 7
    assert not target.exists()
    watchdog.save(target, {"inert": True})
    assert json.loads(target.read_text()) == {"inert": True}


@pytest.mark.parametrize("failure", ["mkstemp", "dump", "file-sync", "link", "directory-sync"])
def test_atomic_publication_failures_leave_absent_or_complete_receipt(tmp_path, monkeypatch, failure):
    target, value, count = tmp_path / "receipt.json", stopped(), 0
    def broken(*args, **kwargs):
        raise OSError("inert private error sentinel")
    if failure in {"file-sync", "directory-sync"}:
        original = watchdog.os.fsync
        def sync(descriptor):
            nonlocal count
            count += 1
            if count == (1 if failure == "file-sync" else 2):
                broken()
            original(descriptor)
        monkeypatch.setattr(watchdog.os, "fsync", sync)
    else:
        module = {"mkstemp": watchdog.tempfile, "dump": watchdog.json, "link": watchdog.os}[failure]
        monkeypatch.setattr(module, failure, broken)
    with pytest.raises(OSError):
        watchdog.save(target, value)
    if target.exists():
        assert json.loads(target.read_text()) == value
    assert list(tmp_path.iterdir()) == ([target] if target.exists() else [])


@pytest.fixture
def bounded_session(tmp_path, monkeypatch):
    directory, calls = tmp_path / "session", []
    class Child:
        pid, result, wait_error, exit_code = 123, json.dumps(stopped()).encode(), None, 0
        def wait(self, timeout):
            assert timeout == 190
            if self.wait_error:
                raise self.wait_error
            if self.result is not None:
                (directory / "watchdog-result.json").write_bytes(self.result)
            return self.exit_code
    child = Child()
    def provider(action, timeout=45):
        calls.append((action, timeout))
        return {"id": watchdog.VM_ID, "state": "STOPPED" if action == "get" else "RUNNING",
                "resources": {"platform": "cpu-e2", "preset": "2vcpu-8gb"}}
    monkeypatch.setattr(watchdog, "provider", provider)
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(watchdog, "await_ready", lambda *args: None)
    return directory, calls, child


@pytest.mark.parametrize("value", [None, b"", b"{", b"\xff", b"[]", b"null",
    b'{"verified_stopped":"true"}', b'{"verified_stopped":1}', b'{"verified_stopped":true}',
    json.dumps({"verified_stopped": True, "after": {"id": "other-vm", "state": "STOPPED"}}).encode(),
    json.dumps({"verified_stopped": True, "after": {"id": watchdog.VM_ID, "state": "STOPPING"}}).encode()])
def test_invalid_result_always_reaches_emergency_readback(bounded_session, value):
    directory, calls, child = bounded_session
    child.result = value
    with watchdog.bounded_vm(directory):
        pass
    assert calls[-2:] == [("stop", 45), ("get", 15)]
    assert watchdog.verified_stop(json.loads((directory / "emergency-stop.json").read_text()))


@pytest.mark.parametrize("failure", ["unreadable", "touch", "wait", "wait-timeout", "timeout-receipt",
                                        "emergency-receipt", "nonzero-exit", "interrupted"])
def test_cleanup_bookkeeping_failure_cannot_skip_stop(bounded_session, monkeypatch, failure):
    directory, calls, child = bounded_session
    original_read, original_touch, original_save = Path.read_text, Path.touch, watchdog.save
    def broken():
        raise OSError("inert private error sentinel")
    if failure == "unreadable":
        def read(path, *args, **kwargs):
            return broken() if path.name == "watchdog-result.json" else original_read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", read)
    if failure == "touch":
        monkeypatch.setattr(Path, "touch", lambda path, **kwargs: broken() if path.name == "stop-requested"
                            else original_touch(path, **kwargs))
    if failure in {"wait", "wait-timeout", "timeout-receipt", "interrupted"}:
        child.wait_error = KeyboardInterrupt() if failure == "interrupted" else (
            subprocess.TimeoutExpired("inert", 190) if "timeout" in failure else OSError("inert private error sentinel"))
    if failure in {"timeout-receipt", "emergency-receipt"}:
        child.result = None
        target = "watchdog-wait-timeout.json" if failure == "timeout-receipt" else "emergency-stop.json"
        monkeypatch.setattr(watchdog, "save", lambda path, value: broken() if path.name == target
                            else original_save(path, value))
    if failure == "nonzero-exit":
        child.exit_code = 1
    if failure == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            with watchdog.bounded_vm(directory):
                pass
    else:
        with watchdog.bounded_vm(directory):
            pass
    assert calls[-2:] == [("stop", 45), ("get", 15)]
    errors = json.loads((directory / "watchdog-cleanup-errors.json").read_text())
    assert errors["errors"] and "sentinel" not in json.dumps(errors)
    assert watchdog.verified_stop(errors["emergency"])


def test_unverified_stop_raises_intervention_even_when_receipt_writes_fail(bounded_session, monkeypatch):
    directory, calls, child = bounded_session
    child.result = None
    original_save = watchdog.save
    def save(path, value):
        if path.name in {"emergency-stop.json", "watchdog-cleanup-errors.json"}:
            raise OSError("inert private error sentinel")
        original_save(path, value)
    def provider(action, timeout=45):
        calls.append((action, timeout))
        return {"id": watchdog.VM_ID, "state": "STOPPING"}
    with pytest.raises(RuntimeError, match="VM stop unverified; immediate operator intervention required"):
        with watchdog.bounded_vm(directory):
            monkeypatch.setattr(watchdog, "provider", provider)
            monkeypatch.setattr(watchdog, "save", save)
    assert calls[-6:] == [("stop", 45), ("get", 15)] * 3


def test_wrong_resource_preset_is_never_adopted(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "provider", lambda *args: {
        "state": "STOPPED", "resources": {"platform": "cpu-e2", "preset": "different"}})
    with pytest.raises(ValueError, match="stopped, unchanged"):
        with watchdog.bounded_vm(tmp_path / "session"):
            pytest.fail("must not enter")


@pytest.mark.parametrize("value", [b"", b"[]", b"{}", b'{"pid":999,"expires_monotonic":700}'])
def test_invalid_handshake_refuses_start(tmp_path, monkeypatch, value):
    class Child:
        pid = 123
        def poll(self):
            return None
    (tmp_path / "watchdog-ready.json").write_bytes(value)
    monkeypatch.setattr(watchdog.time, "monotonic", lambda: 100)
    with pytest.raises(ValueError, match="handshake"):
        watchdog.await_ready(tmp_path, Child(), 700)


def test_handshake_preserves_startup_window(tmp_path, monkeypatch):
    class Child:
        pid = 123
        def poll(self):
            return None
    monkeypatch.setattr(watchdog.time, "monotonic", lambda: 100)
    watchdog.save(tmp_path / "watchdog-ready.json", {"pid": 123, "expires_monotonic": 689})
    with pytest.raises(RuntimeError, match="startup window expired"):
        watchdog.await_ready(tmp_path, Child(), 689)


def test_failed_temporary_cleanup_preserves_publication_failure(tmp_path, monkeypatch):
    def publish(*args):
        raise RuntimeError("inert publication failure")
    def cleanup(*args):
        raise OSError("inert cleanup failure")
    monkeypatch.setattr(watchdog.os, "link", publish)
    monkeypatch.setattr(watchdog.os, "unlink", cleanup)
    with pytest.raises(RuntimeError, match="publication failure"):
        watchdog.save(tmp_path / "receipt.json", stopped())
    assert not (tmp_path / "receipt.json").exists()


def test_publication_cancellation_leaves_no_final_receipt(tmp_path, monkeypatch):
    def dump(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(watchdog.json, "dump", dump)
    with pytest.raises(KeyboardInterrupt):
        watchdog.save(tmp_path / "receipt.json", stopped())
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("observed", [None, [], {"id": "other-vm", "state": "STOPPED"},
                                       {"id": watchdog.VM_ID, "state": "STOPPING"}])
def test_stop_requires_pinned_well_shaped_independent_readback(observed):
    calls = []
    def provider(action, timeout=45):
        calls.append((action, timeout))
        return observed
    assert not watchdog.stop_verified(provider)["verified_stopped"]
    assert calls == [("stop", 45), ("get", 15)] * 3


def test_cleanup_retains_stop_evidence_without_replacing_primary_failure(bounded_session, monkeypatch):
    directory, calls, child = bounded_session
    child.result = None
    original = watchdog.save
    def save(path, value):
        if path.name == "emergency-stop.json":
            raise OSError("inert private error sentinel")
        original(path, value)
    monkeypatch.setattr(watchdog, "save", save)
    with pytest.raises(RuntimeError, match="inert primary failure"):
        with watchdog.bounded_vm(directory):
            raise RuntimeError("inert primary failure")
    assert calls[-2:] == [("stop", 45), ("get", 15)]
    receipt = json.loads((directory / "watchdog-cleanup-errors.json").read_text())
    assert watchdog.verified_stop(receipt["emergency"]) and "sentinel" not in json.dumps(receipt)


def test_verified_stop_reports_unavailable_evidence(bounded_session, monkeypatch):
    directory, calls, child = bounded_session
    child.result = None
    original = watchdog.save
    def save(path, value):
        if path.name in {"emergency-stop.json", "watchdog-cleanup-errors.json"}:
            raise OSError("inert private error sentinel")
        original(path, value)
    monkeypatch.setattr(watchdog, "save", save)
    with pytest.raises(RuntimeError, match="VM stopped; shutdown evidence could not be retained"):
        with watchdog.bounded_vm(directory):
            pass
    assert calls[-2:] == [("stop", 45), ("get", 15)]
