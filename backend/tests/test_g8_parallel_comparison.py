"""Inert process-pool checks only; no model or protected record parsing."""
import json
import multiprocessing
import os
from pathlib import Path
import runpy
import time

import pytest

WORKER = Path(__file__).resolve().parents[2] / "scripts/g8_comparison_semantics_probe.py"


def inert_check(task):
    directory, index = task
    (Path(directory) / str(index)).write_text(str(os.getpid()))
    time.sleep(.05)
    return True


def rejected_check(task):
    raise ValueError("inert rejection")


def test_three_children_check_every_task_once_and_report_parent_counts(tmp_path, capsys):
    module = runpy.run_path(str(WORKER))
    module["validate_replays"]([(str(tmp_path), i) for i in range(12)], check=inert_check)
    assert {p.name for p in tmp_path.iterdir()} == {str(i) for i in range(12)}
    assert 1 < len({p.read_text() for p in tmp_path.iterdir()}) <= 3
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["canonical_replays_exhausted"] for r in records] == list(range(1, 13))
    assert not multiprocessing.active_children()


def test_child_failure_cannot_count_as_completion_and_terminates_pool(capsys):
    module = runpy.run_path(str(WORKER))
    with pytest.raises(ValueError, match="inert rejection"):
        module["validate_replays"]([1, 2, 3], check=rejected_check)
    assert module["PROGRESS"]["canonical_replays_exhausted"] == 0
    assert not capsys.readouterr().out
    assert not multiprocessing.active_children()
