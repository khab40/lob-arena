"""Derive parity bytes from verified saved development logits; no model or IO."""
import json
import math
import re

from .verification_spec import canonical, digest

SETTINGS_SHA = "2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab"
VERIFICATION_SHA = "22f65037c0533cf10d8b4693033b3b80e388bf1e6743692d16140e863e14de98"
REFERENCE_ROWS = 64
MAX_METADATA = 2 * 1024**2


def _json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate reference metadata key")
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError("nonfinite reference metadata")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def prepare_reference(settings_raw, verification_raw, predictions_raw):
    """Trust pins are reviewed constants, never inferred from supplied receipts."""
    for raw, pin, bound in ((settings_raw, SETTINGS_SHA, 65536),
                            (verification_raw, VERIFICATION_SHA, MAX_METADATA)):
        if type(raw) is not bytes or len(raw) > bound or digest(raw) != pin:
            raise ValueError("reference settings or verification trust pin differs")
    if type(predictions_raw) is not bytes or len(predictions_raw) > MAX_METADATA:
        raise ValueError("saved reference predictions exceed metadata bound")
    settings, report = _json(settings_raw), _json(verification_raw)
    context, result = report["context"], report["result"]
    lineage = settings["lineage"]
    source = report["inventory"]["calibration-predictions.json"]
    if (settings["scope"] != "research_only" or settings["gates_passed"] is not True
            or settings["decision"] != "continue_research" or report["status"] != "verified"
            or result["final_test_access"] is not False
            or context["job_id"] != lineage["comparison_job_id"]
            or context["request_sha256"] != lineage["comparison_request_sha256"]
            or context["image_digest"] != lineage["comparison_image_digest"]
            or result["checkpoint_origin"]["checkpoint"]["sha256"] != settings["artifacts"]["checkpoint"]["sha256"]
            or source["size_bytes"] != len(predictions_raw) or source["sha256"] != digest(predictions_raw)
            or type(source["version_id"]) is not str or not source["version_id"]
            or source["version_id"] == "null"):
        raise ValueError("reference source bytes or development lineage differs")
    rows = _json(predictions_raw)
    if not isinstance(rows, list) or not REFERENCE_ROWS <= len(rows) <= 100000:
        raise ValueError("reference prediction population outside bound")
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"target_id", "label", "logit"}
                or type(row["target_id"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", row["target_id"])
                or type(row["label"]) is not int or row["label"] not in (0, 1)
                or type(row["logit"]) not in (int, float) or not math.isfinite(row["logit"])):
            raise ValueError("invalid saved reference row")
    targets = [row["target_id"] for row in rows]
    ordered_sha = digest("".join(target + "\n" for target in targets).encode())
    role = report["audit"]["roles"]["calibration"]
    if (len(set(targets)) != len(targets) or len(rows) != role["row_count"]
            or ordered_sha != role["row_identity_sha256"]
            or ordered_sha != lineage["calibration_targets_sha256"]):
        raise ValueError("saved calibration target population or order differs")
    reference = canonical(rows[:REFERENCE_ROWS])
    receipt = {"schema_version": "transformer_saved_reference_v1", "selection": "first_64_calibration_rows",
        "settings_sha256": SETTINGS_SHA, "verification_sha256": VERIFICATION_SHA,
        "source": {"uri": settings["artifacts"]["contract"]["uri"].rsplit("/", 1)[0]
                   + "/calibration-predictions.json", **source},
        "source_rows": len(rows), "source_targets_sha256": ordered_sha,
        "reference_rows": REFERENCE_ROWS, "reference_sha256": digest(reference),
        "reference_size_bytes": len(reference),
        "reference_targets_sha256": digest(canonical(targets[:REFERENCE_ROWS])),
        "checkpoint_sha256": settings["artifacts"]["checkpoint"]["sha256"],
        "cloud_gets": 0, "model_execution": False, "final_payload_reads": 0,
        "reference_published": False, "cuda_parity_verified": False, "execution_authorized": False}
    return reference, receipt
