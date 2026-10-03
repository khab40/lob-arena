"""Verification of saved confirmation receipts, without model execution."""
from dataclasses import asdict

import pytest

from app.ml.transformer.research_policy import Trial, seed_stability


def receipts():
    return [{"status": "verified", "trial": asdict(trial), "trial_sha256": trial.sha256(),
             "selection_log_loss": .3, "selection_f1_at_half": .8}
            for trial in (Trial(64, .0003, seed) for seed in (42, 7, 2027))]


def test_confirmation_preserves_original_candidate_seed():
    result = seed_stability(receipts(), Trial(64, .0003))
    assert result["passed"] and result["candidate_seed"] == 42


def test_unstable_seed_blocks_freeze_without_search_expansion():
    rows = receipts()
    rows[2]["selection_log_loss"] = .36
    assert not seed_stability(rows, Trial(64, .0003))["passed"]


@pytest.mark.parametrize("case", ["missing", "duplicate", "wrong_config", "unverified", "nan"])
def test_invalid_confirmation_is_rejected(case):
    rows = receipts()
    if case == "missing":
        rows.pop()
    elif case == "duplicate":
        rows[1] = rows[0]
    elif case == "wrong_config":
        rows[1]["trial"]["width"] = 128
    elif case == "unverified":
        rows[1]["status"] = "completed_pending_independent_verification"
    else:
        rows[1]["selection_f1_at_half"] = float("nan")
    with pytest.raises(ValueError):
        seed_stability(rows, Trial(64, .0003))
