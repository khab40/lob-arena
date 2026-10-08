import json

import pytest

from test_transformer_holdout_watch import CLI


def policy_fixture():
    proposal = {"submission": CLI.SUBMISSION, "policy_versions": {"final": "11", "results": "12"},
        "access_seconds": 10800, "create_to_terminal_seconds": 7200}
    buckets = {name: {"metadata": {"resource_version": str(int(version) + 1),
        "updated_at": "1970-01-01T00:16:40Z"}} for name, version in proposal["policy_versions"].items()}
    return proposal, buckets


def test_access_deadline_uses_earliest_verified_grant():
    proposal, buckets = policy_fixture()
    buckets["results"]["metadata"]["updated_at"] = "1970-01-01T00:16:42Z"
    assert CLI.access_deadline(proposal, buckets, now=lambda: 1003) == 11800


@pytest.mark.parametrize("case", ["missing", "version", "future", "timezone", "expired", "mode"])
def test_access_observation_boundaries(case):
    proposal, buckets = policy_fixture()
    if case == "missing":
        del buckets["final"]
    elif case == "version":
        buckets["final"]["metadata"]["resource_version"] = "99"
    elif case == "future":
        buckets["final"]["metadata"]["updated_at"] = "1970-01-01T00:17:00Z"
    elif case == "timezone":
        buckets["final"]["metadata"]["updated_at"] = "1970-01-01T00:16:40"
    elif case == "mode":
        proposal["submission"] = {}
    with pytest.raises((ValueError, TimeoutError)):
        CLI.access_deadline(proposal, buckets, now=lambda: 5000 if case == "expired" else 1000)


def test_existing_attempt_rejected_before_provider_reads(tmp_path, monkeypatch):
    proposal = {}
    monkeypatch.setattr(CLI, "preflight", lambda *a: (proposal, None, None, None, None, None))
    (tmp_path / "operator-approval.json").write_text(json.dumps({"approved": True, "proposal_sha256": "a" * 64}))
    (tmp_path / "creation-attempt.json").write_text("prior interrupted intent")
    monkeypatch.setattr(CLI, "cli", lambda *a, **kw: pytest.fail("provider read"))
    with pytest.raises(ValueError, match="consumes this execution directory"):
        CLI.run(tmp_path, "a" * 64, submit=True)
