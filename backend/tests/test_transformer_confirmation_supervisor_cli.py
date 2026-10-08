"""Inert CLI binding checks; do not launch the supplied operator command."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("confirmation_supervisor_cli", Path(__file__).resolve().parents[2]
                                            / "scripts/transformer_confirmation_supervisor.py")
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def cli(monkeypatch, tmp_path, *, slot="seed-7", timeout=7200, ready=120, requested_slot="seed-7"):
    evidence = tmp_path / "evidence"
    request = evidence / requested_slot / "request.json"
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({"slot": slot, "run_id": "confirmation-seed-7",
                                   "resources": {"timeout_seconds": timeout}}))
    proposal, operator = tmp_path / "proposal.json", tmp_path / "operator.py"
    proposal.write_text("{}")
    operator.write_text("raise RuntimeError('must never execute')")
    paths = {"request": request, "proposal": proposal, "operator": operator}
    args = ["supervisor", "run", "--output", str(tmp_path / "supervision"),
            "--evidence", str(evidence), "--slot", requested_slot, "--proposal", str(proposal),
            "--operator", str(operator), "--operator-python", "/reviewed/python",
            "--ready-seconds", str(ready), "--custody", str(tmp_path / "unread-custody.json")]
    for name, path in paths.items():
        args.extend(["--" + name + "-sha256", supervisor.sha(path)])
    monkeypatch.setattr(supervisor.sys, "argv", args)
    calls = []
    def supervise(*values):
        calls.append(values)
        return 0
    monkeypatch.setattr(supervisor, "supervise", supervise)
    return paths, calls


def test_cli_binds_inputs_and_passes_unread_custody_path(monkeypatch, tmp_path):
    paths, calls = cli(monkeypatch, tmp_path)
    assert supervisor.main() == 0
    assert len(calls) == 1
    command, output, binding, ready, seconds = calls[0]
    assert command == ["/reviewed/python", "-u", str(paths["operator"]), "attest", "--evidence",
                       str(tmp_path / "evidence"), "--slot", "seed-7", "--custody",
                       str(tmp_path / "unread-custody.json")]
    assert output == tmp_path / "supervision" and (ready, seconds) == (120, 7200)
    assert binding["run_id"] == "confirmation-seed-7" and binding["slot"] == "seed-7"
    assert binding["custody_path"] == str(tmp_path / "unread-custody.json")
    assert not Path(binding["custody_path"]).exists()
    for name, path in paths.items():
        assert binding[name + "_path"] == str(path)
        assert binding[name + "_sha256"] == supervisor.sha(path)


@pytest.mark.parametrize("changed", ["request", "proposal", "operator"])
def test_cli_rejects_changed_reviewed_bytes_before_spawn(monkeypatch, tmp_path, changed):
    paths, calls = cli(monkeypatch, tmp_path)
    paths[changed].write_text("changed")
    with pytest.raises(ValueError):
        supervisor.main()
    assert not calls


@pytest.mark.parametrize("overrides", [{"slot": "seed-2027"}, {"timeout": 7201},
                                     {"ready": 121}, {"ready": 0}])
def test_cli_rejects_confirmation_bounds_before_spawn(monkeypatch, tmp_path, overrides):
    _, calls = cli(monkeypatch, tmp_path, **overrides)
    with pytest.raises(ValueError):
        supervisor.main()
    assert not calls


def test_comparison_supervision_uses_exact_one_hour(monkeypatch, tmp_path):
    _, calls = cli(monkeypatch, tmp_path, slot="inference", requested_slot="inference", timeout=3600)
    assert supervisor.main() == 0
    assert calls[0][-1] == 3600


@pytest.mark.parametrize("slot,seconds", [("inference", 7200), ("seed-7", 3600), ("other", 7200)])
def test_slot_cannot_change_its_timeout(monkeypatch, tmp_path, slot, seconds):
    _, calls = cli(monkeypatch, tmp_path, slot=slot, requested_slot=slot, timeout=seconds)
    with pytest.raises(ValueError):
        supervisor.main()
    assert not calls
