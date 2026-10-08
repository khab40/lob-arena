"""Replay the verified December paired predictions without fitting or scoring."""
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .saved_score_io import canonical, checked_read, json_value, read_publication, sha256, validate_private_roots

VERIFICATION_SHA = "329158009e8de6b73ff7571acd414cab5cbcfcc760edd8963d61884349a81869"
SETTINGS_SHA = "2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab"
CAMPAIGN_ID = "december-holdout-20261007"
THRESHOLDS = {"transformer": 0.996423148187864, "lightgbm": 0.5769230769230769}
LEDGER_KEYS = {"target_id", "label", "run_id", "base_session_id", "campaign_id", "prediction_timestamp_ns"}
PREDICTION_KEYS = LEDGER_KEYS | {"logit", "probability", "baseline_probability", "family", "symbol"}
FAMILIES = {"control", "layering_like", "quote_stuffing", "spoofing_like_wall"}
SETTINGS_PATH = Path(__file__).resolve().parents[3] / "configs/releases/transformer/selected-settings-20261005.json"


def validate_rows(ledger, predictions, result, expected_rows, expected_positives):
    if not isinstance(ledger, list) or not isinstance(predictions, list) or len(ledger) != expected_rows:
        raise ValueError("saved population differs")
    if len(predictions) != len(ledger):
        raise ValueError("saved population differs")
    targets = set()
    for row, prediction in zip(ledger, predictions, strict=True):
        if (not isinstance(row, dict) or set(row) != LEDGER_KEYS
                or not isinstance(prediction, dict) or set(prediction) != PREDICTION_KEYS
                or {key: prediction[key] for key in LEDGER_KEYS} != row
                or any(type(prediction[key]) is not type(row[key]) for key in LEDGER_KEYS)):
            raise ValueError("saved target alignment differs")
        target = row["target_id"]
        if not isinstance(target, str) or not re.fullmatch(r"[a-f0-9]{64}", target) or target in targets:
            raise ValueError("saved target identity differs")
        targets.add(target)
        if (type(row["label"]) is not int or row["label"] not in (0, 1)
                or type(row["prediction_timestamp_ns"]) is not int or row["prediction_timestamp_ns"] < 0
                or any(not isinstance(row[key], str) or not 0 < len(row[key]) <= 256
                       for key in ("run_id", "base_session_id"))
                or (row["campaign_id"] is not None and not isinstance(row["campaign_id"], str))
                or not isinstance(prediction["family"], str) or prediction["family"] not in FAMILIES
                or not isinstance(prediction["symbol"], str) or prediction["symbol"] not in {"AAPL", "MSFT", "NVDA"}):
            raise ValueError("saved row schema differs")
        for key in ("logit", "probability", "baseline_probability"):
            number = prediction[key]
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError("saved score is not finite")
            if key != "logit" and not 0 <= number <= 1:
                raise ValueError("saved probability outside range")
    if (sum(row["label"] for row in ledger) != expected_positives
            or sha256(canonical([row["target_id"] for row in ledger]))
            != result["measurements"]["ordered_targets_sha256"]):
        raise ValueError("ordered population differs")


@dataclass
class SavedCampaign:
    rows: list
    provenance: dict

    def grouped(self):
        groups = {}
        for source_ordinal, row in enumerate(self.rows):
            session_id = sha256(row["run_id"].encode())[:16]
            group = groups.setdefault(session_id, [])
            if group and group[0][1]["run_id"] != row["run_id"]:
                raise ValueError("opaque session collision")
            group.append((source_ordinal, row))
        return groups

    def catalog(self):
        return {"kind": "saved_research_predictions", "campaign_id": CAMPAIGN_ID,
            "label_context": "synthetic_research_labels", "provenance": self.provenance,
            "limitations": ["One December date and three base sessions with synthetic research labels.",
                "Saved predictions only; no fresh inference, order-book replay or production qualification.",
                "Transformer: 60 features plus history; LightGBM: 31 features. Attention gains are not isolated.",
                "MLflow reconciliation and complete event-to-alert measurements remain pending."],
            "detectors": [{"id": name, "threshold": value, "mode": "balanced"}
                          for name, value in THRESHOLDS.items()],
            "sessions": [{"id": session, "rows": len(rows), "symbol": rows[0][1]["symbol"],
                          "family": rows[0][1]["family"]} for session, rows in self.grouped().items()]}

    def page(self, session_id, detector, offset, limit):
        groups = self.grouped()
        if session_id not in groups or detector not in THRESHOLDS:
            raise LookupError("saved source or detector unavailable")
        selected = groups[session_id]
        if type(offset) is not int or not 0 <= offset <= len(selected) or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("saved page outside bounds")
        threshold = THRESHOLDS[detector]
        key = "probability" if detector == "transformer" else "baseline_probability"
        rows = [{"ordinal": offset + index, "source_ordinal": source, "target_id": row["target_id"],
                 "timestamp_ns": str(row["prediction_timestamp_ns"]), "symbol": row["symbol"],
                 "family": row["family"], "synthetic_label": row["label"], "probability": row[key],
                 "alert": row[key] >= threshold}
                for index, (source, row) in enumerate(selected[offset:offset + limit])]
        following = offset + len(rows)
        return {"campaign_id": CAMPAIGN_ID, "session_id": session_id, "detector": detector,
                "threshold": threshold, "mode": "balanced", "total": len(selected), "offset": offset,
                "next_offset": following if following < len(selected) else None,
                "provenance": self.provenance, "rows": rows}


def load_campaign(directory, artifact_roots, *, verification_sha=VERIFICATION_SHA,
                  expected_rows=15160, expected_positives=135):
    """Trust overrides are for inert unit fixtures; routes always use the reviewed pins."""
    base = validate_private_roots(directory, artifact_roots)
    verification = json_value(checked_read(base / "verification.json", bound=65536, digest=verification_sha))
    if (verification["status"] != "verified" or verification["rows"] != expected_rows
            or verification["model_execution"] is not False or verification["baseline_rescored"] is not False
            or verification["production_qualified"] is not False or verification["measurements_verified"] is not True):
        raise ValueError("verified research receipt required")
    inventory = verification["inventory"]
    result = read_publication(base, "result.json", inventory["result.json"])
    if (result["job_id"] != verification["job_id"] or result["request_sha256"] != verification["request_sha256"]
            or result["settings_sha256"] != SETTINGS_SHA or result["fitting"] is not False
            or result["baseline_rescored"] is not False or result["execution_bindings"]["source_commit"]
            != verification["execution_source_commit"] or result["execution_bindings"]["image_digest"]
            != verification["execution_image_digest"]):
        raise ValueError("saved result lineage differs")
    ledger = read_publication(base, "target-ledger.json", inventory["target-ledger.json"])
    predictions = read_publication(base, "predictions.json", inventory["predictions.json"])
    validate_rows(ledger, predictions, result, expected_rows, expected_positives)
    settings = json_value(checked_read(SETTINGS_PATH, bound=16384, digest=SETTINGS_SHA))
    if next(point["threshold"] for point in settings["operating_points"] if point["mode"] == "balanced") != THRESHOLDS["transformer"]:
        raise ValueError("saved threshold differs")
    return SavedCampaign(predictions, {"verification_sha256": verification_sha, "settings_sha256": SETTINGS_SHA,
        "job_id": verification["job_id"], "request_sha256": verification["request_sha256"],
        "predictions": inventory["predictions.json"],
        "model_checkpoint_sha256": settings["artifacts"]["checkpoint"]["sha256"]})
