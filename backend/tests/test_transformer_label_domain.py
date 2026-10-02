from copy import deepcopy

import pytest

from app.ml.transformer.label_domain import verify_labels


def run():
    return {
        "run_id": "fixture-run", "campaign_id": "fixture-run",
        "negative_label_source": "research_control_assumption",
        "independently_verified_clean": False,
        "label_windows": [{
            "label": 1, "attack_family": "spoofing_like_wall",
            "label_source": "synthetic_scenario", "provenance_id": None,
            "start_tick": 1, "end_tick": 4, "end_inclusive": True,
            "start_timestamp_ns": None, "end_timestamp_ns": None,
            "phases": {"pressure_phase": [1, 3], "cancellation_phase": [4, 4]},
        }],
    }


@pytest.mark.parametrize("family,end", [
    ("spoofing_like_wall", 4), ("layering_like", 5), ("quote_stuffing", 6),
])
def test_supported_labels_are_checked_without_mutation_or_time_conversion(family, end):
    record = run()
    record["label_windows"][0].update(attack_family=family, end_tick=end)
    before = deepcopy(record)
    assert verify_labels(record) == 1
    assert record == before
    assert record["independently_verified_clean"] is False


def test_control_requires_no_windows():
    record = run()
    record.update(campaign_id=None, label_windows=[])
    assert verify_labels(record) == 0
    record["label_windows"] = run()["label_windows"]
    with pytest.raises(ValueError, match="control replay"):
        verify_labels(record)


@pytest.mark.parametrize("field,value", [
    ("label", True), ("label", 0), ("attack_family", "future_return"), ("attack_family", []),
    ("label_source", "future_return"), ("provenance_id", "global-label"),
    ("start_tick", True), ("end_tick", True), ("start_tick", 0), ("end_tick", -1),
    ("start_tick", 5), ("end_tick", 4.0), ("start_tick", None),
    ("end_inclusive", False), ("end_inclusive", 1),
    ("start_timestamp_ns", 100), ("end_timestamp_ns", 200), ("phases", []),
])
def test_unsupported_label_semantics_fail_closed(field, value):
    record = run()
    record["label_windows"][0][field] = value
    with pytest.raises(ValueError):
        verify_labels(record)


@pytest.mark.parametrize("field,value", [
    ("campaign_id", "another-run"), ("run_id", ""), ("label_windows", []),
    ("label_windows", {}), ("label_windows", [None]),
    ("negative_label_source", "independently_clean"),
    ("independently_verified_clean", True), ("independently_verified_clean", 0),
])
def test_unbound_or_relabelled_runs_fail(field, value):
    record = run()
    record[field] = value
    with pytest.raises(ValueError):
        verify_labels(record)


@pytest.mark.parametrize("field", [
    "campaign_id", "label_windows", "negative_label_source", "independently_verified_clean",
])
def test_required_run_fields_are_not_inferred(field):
    record = run()
    del record[field]
    with pytest.raises(ValueError):
        verify_labels(record)


def test_unknown_label_fields_and_multiple_windows_are_rejected():
    record = run()
    record["label_windows"][0]["future_horizon_ticks"] = 1
    with pytest.raises(ValueError, match="schema"):
        verify_labels(record)
    record = run()
    del record["label_windows"][0]["end_timestamp_ns"]
    with pytest.raises(ValueError, match="schema"):
        verify_labels(record)
    record = run()
    record["label_windows"] *= 2
    with pytest.raises(ValueError, match="single label window"):
        verify_labels(record)
