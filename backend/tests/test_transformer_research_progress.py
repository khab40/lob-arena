"""Scalar-only progress fixtures; no model imports, cloud calls or execution."""
from dataclasses import asdict
import json

import pytest

from app.ml.transformer import research_progress as logging
from app.ml.transformer.research_policy import Trial, select_grid


def lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def progress(*, improved=True):
    return {"epoch": 2, "global_step": 6, "best_epoch": 2 if improved else 1,
            "best_loss": .2, "stale_epochs": 0 if improved else 1,
            "history": [{"epoch": 2, "weighted_train_loss": .3,
                         "selection_log_loss": .2 if improved else .4, "selection_f1_at_half": .8}]}


def result(epoch=7, stale=5, checkpoints=True):
    return {"progress": {"epoch": epoch, "stale_epochs": stale, "global_step": epoch * 3},
            "selected_epoch": 2, "selection_log_loss": .2, "selection_f1_at_half": .8,
            "parameter_count": 107905, "duration_seconds": 18.5,
            "peak_allocated_gpu_bytes": 1000, "peak_reserved_gpu_bytes": 2000,
            "published_checkpoints": [{"epoch": 2, "name": "epoch-02.pt", "sha256": "a" * 64}]
                if checkpoints else [], "bindings": {"secret": "must-not-be-logged"}}


@pytest.mark.parametrize("event,fields", [
    ("unknown", {}), ("phase_started", {"secret": "private"}),
    ("phase_started", {"phase": {"token": "private"}}),
    ("phase_started", {"phase": ["private"]}), ("phase_started", {"phase": object()}),
    ("phase_started", {"phase": "x" * 257}),
    ("epoch_completed", {"selection_log_loss": float("nan")}),
    ("epoch_completed", {"selection_log_loss": float("inf")}),
    ("epoch_completed", {"selection_log_loss": None}),
])
def test_nonallowlisted_or_unbounded_payloads_never_reach_stdout(event, fields, capsys):
    with pytest.raises(ValueError):
        logging.emit(event, **fields)
    assert not capsys.readouterr().out


def test_progress_is_flushed_and_broken_stream_does_not_abort_work(monkeypatch):
    calls = []
    def broken_print(value, **kwargs):
        calls.append((json.loads(value), kwargs))
        raise BrokenPipeError("private stream error")
    monkeypatch.setattr("builtins.print", broken_print)
    logging.emit("phase_started", phase="gpu", slot="search-64-0003")
    assert calls == [({"event": "phase_started", "phase": "gpu", "slot": "search-64-0003",
                      "evidence_status": "progress_not_independent_verification"}, {"flush": True})]


def test_deadline_during_stdout_is_not_swallowed(monkeypatch):
    def expired(*args, **kwargs):
        raise TimeoutError("workload deadline")
    monkeypatch.setattr("builtins.print", expired)
    with pytest.raises(TimeoutError, match="workload deadline"):
        logging.emit("phase_started", phase="gpu", slot="search-64-0003")


@pytest.mark.parametrize("improved", [True, False])
def test_epoch_logs_acknowledged_checkpoint_and_optimization_progress(monkeypatch, capsys, improved):
    persisted, clock = [], iter([10., 12.5])
    monkeypatch.setattr(logging.time, "monotonic", lambda: next(clock))
    report = logging.TrialProgress(Trial(64, .0003), 130, 20, 3,
                                   persist=lambda event, fields: persisted.append((event, fields)))
    report.start({"epoch": 1})
    report.epoch_started(2, 3)
    report.epoch_completed(progress(improved=improved), {"name": "epoch-02.pt", "sha256": "a" * 64},
                           .0001, .0002)
    started, epoch, completed = lines(capsys)
    assert started["resumed_from_epoch"] == 1 and started["optimizer"] == "AdamW"
    assert started["train_rows"] == 130 and started["batches_per_epoch"] == 3
    assert epoch["epoch"] == 2 and epoch["global_step"] == 3
    assert completed["epoch_seconds"] == 2.5 and completed["global_step"] == 6
    assert completed["learning_rate_first_step"] == .0001
    assert completed["learning_rate_last_step"] == .0002
    assert completed["weighted_train_loss"] == .3 and completed["selection_f1_at_half"] == .8
    assert completed["selection_log_loss"] == (.2 if improved else .4)
    assert completed["best_epoch"] == (2 if improved else 1)
    assert completed["best_selection_log_loss"] == .2 and completed["improved"] is improved
    assert completed["stale_epochs"] == (0 if improved else 1) and completed["patience"] == 5
    assert completed["checkpoint"] == "epoch-02.pt" and completed["checkpoint_sha256"] == "a" * 64
    assert persisted == [("epoch_completed", {k: v for k, v in completed.items()
                                              if k not in ("event", "evidence_status")})]


@pytest.mark.parametrize("epoch,stale,reason,checkpoints", [
    (7, 5, "patience", True), (30, 1, "max_epochs", True), (7, 5, "patience", False)])
def test_summary_identifies_choice_stop_reason_and_resume_fallback(capsys, epoch, stale, reason, checkpoints):
    logging.TrialProgress(Trial(64, .0003), 130, 20, 3).finish(result(epoch, stale, checkpoints))
    [summary] = lines(capsys)
    assert summary["selected_epoch"] == 2 and summary["stopped_epoch"] == epoch
    assert summary["stop_reason"] == reason and summary["global_step"] == epoch * 3
    assert summary["selection_log_loss"] == .2 and summary["selection_f1_at_half"] == .8
    assert summary["training_seconds"] == 18.5 and summary["parameter_count"] == 107905
    assert summary["peak_allocated_gpu_bytes"] == 1000 and summary["peak_reserved_gpu_bytes"] == 2000
    assert summary["checkpoint"] == ("epoch-02.pt" if checkpoints else "retained_resume_checkpoint")
    assert summary["checkpoint_sha256"] == ("a" * 64 if checkpoints else "see_resume_receipt")
    assert "F1_diagnostic_only" in summary["selection_rule"]
    assert "secret" not in json.dumps(summary) and "bindings" not in summary


def test_failed_durable_event_is_not_misreported_as_verified_completion(capsys):
    calls = []
    def unavailable(event, fields):
        calls.append(event)
        raise OSError("private publication details")
    report = logging.TrialProgress(Trial(64, .0003), 130, 20, 3, persist=unavailable)
    with pytest.raises(OSError):
        report.finish(result())
    [entry] = lines(capsys)
    assert calls == ["training_completed"]
    assert entry["evidence_status"] == "progress_not_independent_verification"
    assert "status" not in entry and "private" not in json.dumps(entry)


def test_grid_logs_four_candidates_and_persists_only_the_loss_selected_choice(capsys):
    rows = []
    for width, rate in ((64, .0003), (64, .001), (128, .0003), (128, .001)):
        trial = Trial(width, rate)
        rows.append({"trial": asdict(trial), "trial_sha256": trial.sha256(), "status": "verified",
                     "selected_epoch": 2, "selection_log_loss": .02 if len(rows) == 2 else .2,
                     "selection_f1_at_half": .5 if len(rows) == 2 else .9,
                     "parameter_count": width * 100, "secret": "must-not-be-logged"})
    winner = select_grid(rows)
    assert not capsys.readouterr().out  # Selection policy remains usable without logging side effects.
    persisted = []
    logging.grid_selected(rows, winner, persist=lambda event, fields: persisted.append((event, fields)))
    entries = lines(capsys)
    assert [entry["event"] for entry in entries] == ["grid_candidate"] * 4 + ["grid_selected"]
    assert [entry["trial_sha256"] for entry in entries[:4]] == [row["trial_sha256"] for row in rows]
    assert entries[-1]["width"] == 128 and entries[-1]["learning_rate"] == .0003
    assert entries[-1]["selection_f1_at_half"] == .5 and entries[-1]["selection_log_loss"] == .02
    assert entries[-1]["selection_rule"] == "lowest_selection_log_loss_then_parameter_count_then_trial_sha256"
    assert persisted == [("grid_selected", {k: v for k, v in entries[-1].items()
                                           if k not in ("event", "evidence_status")})]
    assert "secret" not in json.dumps(entries)
