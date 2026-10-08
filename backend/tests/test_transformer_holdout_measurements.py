from types import SimpleNamespace

import pytest

from app.ml.transformer.holdout_measurements import FIELDS, validate_measurements
from app.ml.transformer.verification_spec import canonical, digest


def evidence():
    ledger = [{"target_id": "a"}, {"target_id": "b"}]
    values = {"elapsed_seconds": 1.25, "batch_size": 64, "rows": 2,
              "peak_gpu_allocated_bytes": 1024, "peak_gpu_reserved_bytes": 2048,
              "includes_host_to_device": True,
              "lightgbm_latency": "not_measured_saved_predictions_reused",
              "ordered_targets_sha256": digest(canonical(["a", "b"]))}
    return values, ledger, SimpleNamespace(timeout_seconds=3600, batch_size=64)


@pytest.mark.parametrize("elapsed", [0, 1.25, 3600])
def test_consistent_measurements_at_time_boundaries(elapsed):
    values, ledger, request = evidence()
    values["elapsed_seconds"] = elapsed
    validate_measurements(values, ledger, request)


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_each_measurement_is_required(field):
    values, ledger, request = evidence()
    del values[field]
    with pytest.raises(ValueError, match="structure"):
        validate_measurements(values, ledger, request)


@pytest.mark.parametrize("values", [None, [], "measurements", {}, {"unexpected": 1}])
def test_measurement_block_must_have_exact_shape(values):
    _, ledger, request = evidence()
    with pytest.raises(ValueError, match="structure"):
        validate_measurements(values, ledger, request)


@pytest.mark.parametrize("field,value", [
    ("elapsed_seconds", -1), ("elapsed_seconds", 3600.01),
    ("elapsed_seconds", float("nan")), ("elapsed_seconds", float("inf")),
    ("elapsed_seconds", -float("inf")), ("elapsed_seconds", True),
    ("elapsed_seconds", "1.25"), ("elapsed_seconds", 10**1000),
    ("batch_size", 32), ("batch_size", 64.0), ("batch_size", True),
    ("rows", 3), ("rows", 2.0), ("rows", True),
    ("peak_gpu_allocated_bytes", -1), ("peak_gpu_allocated_bytes", 1024.0),
    ("peak_gpu_allocated_bytes", True), ("peak_gpu_allocated_bytes", "1024"),
    ("peak_gpu_reserved_bytes", -1), ("peak_gpu_reserved_bytes", 1023),
    ("peak_gpu_reserved_bytes", 2048.0), ("peak_gpu_reserved_bytes", True),
    ("peak_gpu_reserved_bytes", float("inf")),
    ("includes_host_to_device", False), ("includes_host_to_device", 1),
    ("lightgbm_latency", "measured"), ("ordered_targets_sha256", "0" * 64),
])
def test_invalid_measurement_value_is_rejected(field, value):
    values, ledger, request = evidence()
    values[field] = value
    with pytest.raises(ValueError):
        validate_measurements(values, ledger, request)


def test_extra_field_is_rejected():
    values, ledger, request = evidence()
    values["unexpected"] = 1
    with pytest.raises(ValueError, match="structure"):
        validate_measurements(values, ledger, request)


def test_equal_memory_peaks_and_zero_are_nonnegative():
    values, ledger, request = evidence()
    values["peak_gpu_allocated_bytes"] = values["peak_gpu_reserved_bytes"] = 0
    validate_measurements(values, ledger, request)


def test_target_digest_binds_order():
    values, ledger, request = evidence()
    with pytest.raises(ValueError, match="target order"):
        validate_measurements(values, list(reversed(ledger)), request)
