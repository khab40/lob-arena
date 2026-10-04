"""Fake child/clock supervision; never start an attester or cloud command."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("confirmation_supervisor", Path(__file__).resolve().parents[2]
                                            / "scripts/transformer_confirmation_supervisor.py")
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def event(name, stage):
    return {"event": name, "stage": stage, "evidence_status": "progress_not_independent_verification"}


READY = event("attester_ready", "provider_read")
WAIT = event("attester_waiting", "provider_read")
PUBLISH = event("context_publication_started", "context_publish")
PUBLISHED = event("context_published", "context_publish")
DELIVERED = {"job_id": "aijob-fixture", "context_delivered": True}


def harness(monkeypatch, tmp_path, records, *, exit_at=1, exit_code=0):
    clock, signals, observations = [1000.], [], []
    output = tmp_path / "supervision"
    binding = {"slot": "seed-7", "run_id": "confirmation-seed-7"}
    for name in ("proposal", "request", "operator"):
        path = tmp_path / name
        path.write_text("{}")
        binding.update({name + "_path": str(path), name + "_sha256": supervisor.sha(path)})
    queue = list(records)
    class Child:
        pid = 54321
        killed = False
        def poll(self):
            while queue and queue[0][0] <= clock[0] - 1000:
                _, record = queue.pop(0)
                self.stdout.write(record if isinstance(record, str) else json.dumps(record) + "\n")
                self.stdout.flush()
            return -15 if self.killed else (exit_code if clock[0] - 1000 >= exit_at else None)
        def wait(self, timeout=None):
            assert self.killed
            return -15
    child = Child()
    commands = []
    def spawn(command, **kwargs):
        commands.append(command)
        assert kwargs["start_new_session"] is True
        child.stdout = kwargs["stdout"]
        return child
    def pause(seconds):
        clock[0] += seconds
        observations.append(supervisor.inspect(output, binding["proposal_sha256"], binding["request_sha256"],
            now=lambda: clock[0], identity=lambda pid: "same-start"))
    def kill(pid, sig):
        signals.append((pid, sig))
        child.killed = True
    monkeypatch.setattr(supervisor.os, "killpg", kill)
    def run():
        return supervisor.supervise(["inert-child"], output, binding, 2, 10, spawn=spawn,
            now=lambda: clock[0], pause=pause, identity=lambda pid: "same-start")
    return SimpleNamespace(run=run, output=output, binding=binding, clock=clock, signals=signals,
                           observations=observations, commands=commands, child=child)


def test_ready_requires_absent_job_poll_then_delivers_once(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT), (.5, PUBLISH),
        (.75, PUBLISHED), (1, DELIVERED)])
    assert h.run() == 0
    assert [r["admission_ready"] for r in h.observations] == [False, True, False, False]
    status = json.loads((h.output / "status.json").read_bytes())
    assert status["state"] == "delivered" and status["job_id"] == "aijob-fixture"
    assert json.loads((h.output / "readiness.json").read_bytes())["binding"] == h.binding
    assert h.commands == [["inert-child"]] and not h.signals
    with pytest.raises(FileExistsError):
        h.run()
    assert len(h.commands) == 1


def test_ready_event_alone_never_admits_and_timeout_stops_owned_child(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY)], exit_at=30)
    assert h.run() == 1
    assert all(not r["admission_ready"] for r in h.observations)
    assert not (h.output / "readiness.json").exists()
    assert h.signals == [(h.child.pid, supervisor.signal.SIGTERM)]
    assert json.loads((h.output / "status.json").read_bytes())["error_type"] == "TimeoutError"


def test_failure_during_external_create_is_recorded_without_restart(monkeypatch, tmp_path):
    failed = {"status": "failed", "stage": "provider_validation", "error_type": "AttributeError",
              "cause_type": None, "frames": [{"file": "research_context.py", "function": "observed", "line": 20}],
              "cause_frames": []}
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT), (.5, failed)], exit_at=.5, exit_code=1)
    assert h.run() == 1
    assert any(r["admission_ready"] for r in h.observations)
    status = supervisor.inspect(h.output, h.binding["proposal_sha256"], h.binding["request_sha256"])
    assert status["state"] == "failed" and not status["admission_ready"]
    assert status["attester_failure"]["stage"] == "provider_validation"
    assert len(h.commands) == 1 and not h.signals


@pytest.mark.parametrize("fault", ["stale", "pid_reused", "wrong_request", "changed_operator", "expired_admission"])
def test_inspection_rejects_stale_or_changed_admission(monkeypatch, tmp_path, fault):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT), (.5, PUBLISHED), (1, DELIVERED)])
    assert h.run() == 0
    ready = json.loads((h.output / "readiness.json").read_bytes())
    supervisor.save(h.output / "status.json", ready)
    now = ready["updated_at"]
    request_sha = h.binding["request_sha256"]
    start = "same-start"
    def identity(pid):
        return start
    if fault == "stale":
        now += 4
    elif fault == "pid_reused":
        start = "another-start"
    elif fault == "wrong_request":
        request_sha = "a" * 64
    elif fault == "changed_operator":
        Path(h.binding["operator_path"]).write_text("changed")
    else:
        ready["admission_expires_at"] = now - 1
        supervisor.save(h.output / "status.json", ready)
        assert not supervisor.inspect(h.output, h.binding["proposal_sha256"], request_sha,
                                      now=lambda: now, identity=identity)["admission_ready"]
        return
    with pytest.raises(ValueError):
        supervisor.inspect(h.output, h.binding["proposal_sha256"], request_sha, now=lambda: now, identity=identity)
    assert not h.signals  # Inspection never signals any stored PID.


@pytest.mark.parametrize("records,code", [([(0, READY), (.25, WAIT)], 0), ([(0, READY)], 7),
    ([(0, READY), (.25, WAIT), (.5, DELIVERED)], 0), ([(0, "{broken\n")], 0)])
def test_incomplete_or_invalid_child_output_fails_closed(monkeypatch, tmp_path, records, code):
    h = harness(monkeypatch, tmp_path, records, exit_code=code)
    assert h.run() == 1
    assert json.loads((h.output / "status.json").read_bytes())["state"] == "failed"
    assert len(h.commands) == 1


def test_child_exit_in_ready_poll_never_admits(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT)], exit_at=.25, exit_code=1)
    assert h.run() == 1
    assert all(not record["admission_ready"] for record in h.observations)
    assert not (h.output / "readiness.json").exists()


def test_child_exit_during_cleanup_keeps_failure_receipt(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY)], exit_at=30)
    def exited_before_signal(pid, sig):
        h.child.killed = True
        raise ProcessLookupError()
    monkeypatch.setattr(supervisor.os, "killpg", exited_before_signal)
    assert h.run() == 1
    assert json.loads((h.output / "status.json").read_bytes())["error_type"] == "TimeoutError"
