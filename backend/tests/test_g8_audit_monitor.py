"""Inert monitor decisions: provider transport failures are not startup failures."""
import json
from pathlib import Path
import runpy

DECIDE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/g8_audit_monitor.py"))["decision"]
START = json.dumps({"schema_version": "g8_audit_supervisor_v1", "stage": "launcher_started"})


def test_network_error_after_verified_startup_does_not_cancel():
    seen, reason, _ = DECIDE(elapsed=10, launcher_seen=False, log_output=START)
    assert seen and reason is None
    for output in (None, "", "provider transport unavailable"):
        seen, reason, progress = DECIDE(elapsed=1500, launcher_seen=seen, log_output=output)
        assert seen and reason is None and progress is None


def test_missing_startup_and_supervisor_deadlines_still_cancel():
    assert DECIDE(elapsed=301, launcher_seen=False, log_output=None)[1] == "startup_deadline"
    assert DECIDE(elapsed=3061, launcher_seen=True, log_output=None)[1] == "supervisor_deadline"
    assert DECIDE(elapsed=300, launcher_seen=False, log_output=None)[1] is None


def test_other_log_schemas_do_not_prove_launcher_startup():
    output = json.dumps({"schema_version": "other", "stage": "launcher_started"})
    assert DECIDE(elapsed=301, launcher_seen=False, log_output=output)[:2] == (False, "startup_deadline")


def test_bounded_progress_does_not_replace_startup_proof():
    output = json.dumps({"schema_version": "g8_comparison_progress_v1", "canonical_replays_exhausted": 19})
    seen, reason, progress = DECIDE(elapsed=500, launcher_seen=True, log_output=output)
    assert seen and reason is None and progress["canonical_replays_exhausted"] == 19
