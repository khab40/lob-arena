import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("watch_holdout", ROOT / "scripts/watch_transformer_holdout.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def test_wrong_external_pin_stops_before_imports_credentials_or_cloud(tmp_path, monkeypatch):
    (tmp_path / "proposal.json").write_bytes(b"{}")
    def forbidden(*args, **kwargs):
        raise AssertionError("must fail before cloud or source import")
    monkeypatch.setattr(CLI, "sources", forbidden)
    monkeypatch.setattr(CLI.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="external proposal pin"):
        CLI.preflight(tmp_path, "0" * 64)


@pytest.mark.parametrize("mutation", [True, False])
def test_deterministic_provider_failure_has_no_retry(monkeypatch, mutation):
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["timeout"])
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"PermissionDenied")
    monkeypatch.setattr(CLI.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        CLI.cli("ai", "job", "get", mutation=mutation)
    assert calls == [30]


def test_retry_budget_uses_remaining_time(monkeypatch):
    clock, calls = [0.0], []
    def fail(*args, **kwargs):
        calls.append(kwargs["timeout"])
        clock[0] += kwargs["timeout"]
        raise CLI.subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(CLI.subprocess, "run", fail)
    with pytest.raises(TimeoutError):
        CLI.cli("ai", "job", "get", budget=100, now=lambda: clock[0])
    assert calls == [30, 60, 10] and clock[0] == 100


def test_local_cli_preflight_checks_actual_command_argv(monkeypatch):
    calls = []
    def check(args, **kwargs):
        calls.append(args)
        assert "--request-timeout" not in args and "--timeout" in args
        assert "--auth-timeout" in args and "--per-retry-timeout" in args
        assert args[-1] == "--help" and kwargs["timeout"] == 30
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(CLI.subprocess, "run", check)
    CLI.cli_preflight()
    assert len(calls) == 3


def test_transient_reads_increase_timeout_but_never_retry_mutations(monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["timeout"])
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"Unavailable")
    monkeypatch.setattr(CLI.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        CLI.cli("ai", "job", "get")
    assert calls == [30, 60, 90, 120]
    calls.clear()
    with pytest.raises(RuntimeError):
        CLI.cli("ai", "job", "cancel", mutation=True)
    assert calls == [30]
