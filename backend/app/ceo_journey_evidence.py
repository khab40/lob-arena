"""Fixed original-score window, immutable evidence hashes and factual fallback."""
from datetime import datetime, timezone
import math
import re

from app.ceo_journey_store import ArtifactUnavailable, IDENTIFIER
from app.research.saved_score_io import canonical, sha256
from app.research.saved_scores import CAMPAIGN_ID, THRESHOLDS


def timestamp(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z")


def hashed(value, field):
    return {**value, field: sha256(canonical(value))}


def verify_hash(value, field):
    if not isinstance(value, dict) or not isinstance(value.get(field), str):
        raise ArtifactUnavailable()
    raw = {key: item for key, item in value.items() if key != field}
    if value[field] != sha256(canonical(raw)):
        raise ArtifactUnavailable()
    return value


def prepared(campaign):
    groups = campaign.grouped()
    for row in campaign.rows:
        if row["probability"] >= THRESHOLDS["transformer"]:
            session = sha256(row["run_id"].encode())[:16]
            selected = groups[session]
            index = next(i for i, (_, item) in enumerate(selected) if item["target_id"] == row["target_id"])
            offset = max(0, index - 16)
            return {"session_id": session, "offset": offset, "limit": min(64, len(selected) - offset)}
    raise ArtifactUnavailable()


def paired_pages(campaign, window):
    return {name: campaign.page(window["session_id"], name, window["offset"], window["limit"])
            for name in THRESHOLDS}


def pair(pages, index):
    return {name: {"probability": page["rows"][index]["probability"], "threshold": page["threshold"],
                   "alert": page["rows"][index]["alert"]} for name, page in pages.items()}


def context_row(pages, index):
    row = pages["transformer"]["rows"][index]
    return {**{key: value for key, value in row.items() if key not in {"probability", "alert"}},
            "paired_scores": pair(pages, index)}


def verify_snapshot(value, identifier):
    verify_hash(value, "snapshot_sha256")
    if (set(value) != {"id", "campaign_id", "detector", "threshold", "row", "paired_scores", "context",
                      "provenance", "workspace_id", "created_at", "snapshot_sha256"}
            or not IDENTIFIER.fullmatch(identifier) or value["id"] != identifier
            or value["campaign_id"] != CAMPAIGN_ID or value["workspace_id"] != "ceo-demo"
            or value["detector"] not in THRESHOLDS or value["threshold"] != THRESHOLDS[value["detector"]]
            or not isinstance(value["context"], list) or len(value["context"]) > 16
            or not isinstance(value["provenance"], dict) or not isinstance(value["created_at"], str)):
        raise ArtifactUnavailable()
    verify_row(value["row"], selected=True)
    verify_pair(value["paired_scores"])
    selected = value["paired_scores"][value["detector"]]
    if (value["row"]["probability"] != selected["probability"] or value["row"]["alert"] is not True
            or selected["alert"] is not True):
        raise ArtifactUnavailable()
    previous = value["row"]["ordinal"] - len(value["context"])
    for row in value["context"]:
        verify_row(row, selected=False)
        verify_pair(row["paired_scores"])
        if row["ordinal"] != previous or row["source_ordinal"] >= value["row"]["source_ordinal"]:
            raise ArtifactUnavailable()
        previous += 1
    return value


def verify_row(row, *, selected):
    keys = {"ordinal", "source_ordinal", "target_id", "timestamp_ns", "symbol", "family", "synthetic_label"}
    keys |= {"probability", "alert"} if selected else {"paired_scores"}
    if (not isinstance(row, dict) or set(row) != keys
            or any(type(row[key]) is not int or row[key] < 0 for key in ("ordinal", "source_ordinal"))
            or not isinstance(row["target_id"], str) or not re.fullmatch(r"[a-f0-9]{64}", row["target_id"])
            or not isinstance(row["timestamp_ns"], str) or not re.fullmatch(r"[0-9]{1,30}", row["timestamp_ns"])
            or row["symbol"] not in {"AAPL", "MSFT", "NVDA"}
            or row["family"] not in {"control", "layering_like", "quote_stuffing", "spoofing_like_wall"}
            or type(row["synthetic_label"]) is not int or row["synthetic_label"] not in {0, 1}):
        raise ArtifactUnavailable()
    if selected and (type(row["probability"]) not in (int, float) or not math.isfinite(row["probability"])
                     or not 0 <= row["probability"] <= 1 or type(row["alert"]) is not bool):
        raise ArtifactUnavailable()


def verify_pair(scores):
    if not isinstance(scores, dict) or set(scores) != set(THRESHOLDS):
        raise ArtifactUnavailable()
    for name, item in scores.items():
        if (not isinstance(item, dict) or set(item) != {"probability", "threshold", "alert"}
                or type(item["probability"]) not in (int, float) or not math.isfinite(item["probability"])
                or not 0 <= item["probability"] <= 1 or item["threshold"] != THRESHOLDS[name]
                or type(item["alert"]) is not bool or item["alert"] != (item["probability"] >= item["threshold"])):
            raise ArtifactUnavailable()


def factual_text(snapshot):
    row, scores = snapshot["row"], snapshot["paired_scores"]
    parts = [f"Recorded {row['symbol']} saved research prediction at timestamp {row['timestamp_ns']}."]
    for name in THRESHOLDS:
        item = scores[name]
        decision = "alert" if item["alert"] else "no alert"
        parts.append(f"{name}: probability {item['probability']:.9g}, frozen balanced threshold "
                     f"{item['threshold']:.9g}, recorded decision {decision}.")
    parts.append(f"Synthetic research label: {row['synthetic_label']}; scenario family: {row['family']}. "
                 f"The snapshot retains {len(snapshot['context'])} preceding paired score rows.")
    parts.append("Deterministic factual fallback; no LLM call or fresh inference was performed. "
                 "These saved scores and synthetic labels contain no order-book or trade evidence "
                 "and do not establish adjudicated market abuse.")
    return " ".join(parts)


def verify_explanation(value, snapshot):
    verify_hash(value, "explanation_sha256")
    if (set(value) != {"mode", "input_sha256", "input", "text", "created_at", "explanation_sha256"}
            or value["mode"] != "deterministic_fallback" or value["input_sha256"] != snapshot["snapshot_sha256"]
            or canonical(value["input"]) != canonical(snapshot) or value["text"] != factual_text(snapshot)
            or len(value["text"]) > 4096 or not isinstance(value["created_at"], str)):
        raise ArtifactUnavailable()
    return value
