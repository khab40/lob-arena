"""Validate recorded telemetry against the request and ordered target ledger."""
import math

from .verification_spec import canonical, digest


FIELDS = {"elapsed_seconds", "batch_size", "rows", "peak_gpu_allocated_bytes",
          "peak_gpu_reserved_bytes", "includes_host_to_device", "lightgbm_latency",
          "ordered_targets_sha256"}


def validate_measurements(measurements, ledger, request):
    if type(measurements) is not dict or set(measurements) != FIELDS:
        raise ValueError("holdout measurement structure differs")
    elapsed = measurements["elapsed_seconds"]
    if (type(elapsed) not in (int, float) or not 0 <= elapsed <= request.timeout_seconds
            or not math.isfinite(elapsed)):
        raise ValueError("holdout elapsed time is outside approved bounds")
    for key, expected in (("batch_size", request.batch_size), ("rows", len(ledger))):
        if type(measurements[key]) is not int or measurements[key] != expected:
            raise ValueError("holdout measurement count differs: " + key)
    allocated = measurements["peak_gpu_allocated_bytes"]
    reserved = measurements["peak_gpu_reserved_bytes"]
    if (type(allocated) is not int or type(reserved) is not int
            or allocated < 0 or reserved < allocated):
        raise ValueError("holdout GPU memory measurements differ")
    if (measurements["includes_host_to_device"] is not True
            or measurements["lightgbm_latency"] != "not_measured_saved_predictions_reused"
            or measurements["ordered_targets_sha256"] != digest(canonical(
                [row["target_id"] for row in ledger]))):
        raise ValueError("holdout measurement scope or target order differs")
