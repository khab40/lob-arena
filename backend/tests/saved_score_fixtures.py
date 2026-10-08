"""Invented JSON evidence; no training, scoring or private row payloads."""
from app.research.saved_score_io import canonical, sha256
from app.research.saved_scores import SETTINGS_SHA, THRESHOLDS


def evidence(tmp_path, *, mutation=None):
    directory = tmp_path / "private"
    directory.mkdir()
    (directory / "receipts").mkdir()
    ledger = [{"target_id": sha256(str(index).encode()), "label": int(index == 1),
               "run_id": "invented-run", "base_session_id": "invented-session", "campaign_id": None,
               "prediction_timestamp_ns": 34560000000001} for index in range(3)]
    predictions = [{**row, "logit": 0.0, "probability": score,
                    "baseline_probability": THRESHOLDS["lightgbm"], "family": "control", "symbol": "AAPL"}
                   for row, score in zip(ledger, [0.0, THRESHOLDS["transformer"], 1.0], strict=True)]
    result = {"job_id": "invented-job", "request_sha256": "a" * 64, "settings_sha256": SETTINGS_SHA,
              "fitting": False, "baseline_rescored": False,
              "execution_bindings": {"source_commit": "b" * 40, "image_digest": "sha256:" + "c" * 64},
              "measurements": {"ordered_targets_sha256": sha256(canonical([row["target_id"] for row in ledger]))}}
    if mutation:
        mutation(ledger, predictions, result)
    inventory = {}
    for name, value in (("result.json", result), ("target-ledger.json", ledger), ("predictions.json", predictions)):
        raw = canonical(value)
        reference = {"sha256": sha256(raw), "size_bytes": len(raw), "version_id": "1"}
        (directory / name).write_bytes(raw)
        (directory / "receipts" / (name + ".json")).write_bytes(canonical(reference))
        inventory[name] = reference
    verification = {"status": "verified", "rows": 3, "model_execution": False, "baseline_rescored": False,
                    "production_qualified": False, "measurements_verified": True, "inventory": inventory,
                    "job_id": result["job_id"], "request_sha256": result["request_sha256"],
                    "execution_source_commit": "b" * 40, "execution_image_digest": "sha256:" + "c" * 64}
    raw = canonical(verification)
    (directory / "verification.json").write_bytes(raw)
    return directory, sha256(raw)
