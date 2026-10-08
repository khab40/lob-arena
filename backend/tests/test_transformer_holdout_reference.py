import copy
import hashlib

import pytest

from app.ml.transformer import holdout_reference as module
from app.ml.transformer.verification_spec import canonical, digest


@pytest.fixture
def saved(monkeypatch):
    rows = [{"target_id": hashlib.sha256(str(i).encode()).hexdigest(),
             "label": i % 2, "logit": i / 100 - .4} for i in range(70)]
    ordered_sha = digest("".join(r["target_id"] + "\n" for r in rows).encode())
    source = canonical(rows)
    lineage = {"comparison_job_id": "aijob-fixture", "comparison_request_sha256": "a" * 64,
               "comparison_image_digest": "sha256:" + "b" * 64, "calibration_targets_sha256": ordered_sha}
    settings = {"scope": "research_only", "gates_passed": True, "decision": "continue_research",
        "lineage": lineage, "artifacts": {"contract": {"uri": "s3://results/development/run/input-contract.json"},
                                           "checkpoint": {"sha256": "c" * 64}}}
    report = {"status": "verified", "context": {"job_id": lineage["comparison_job_id"],
        "request_sha256": lineage["comparison_request_sha256"], "image_digest": lineage["comparison_image_digest"]},
        "result": {"final_test_access": False, "checkpoint_origin": {"checkpoint": {"sha256": "c" * 64}}},
        "inventory": {"calibration-predictions.json": {"sha256": digest(source), "size_bytes": len(source),
                                                       "version_id": "1"}},
        "audit": {"roles": {"calibration": {"row_count": len(rows), "row_identity_sha256": ordered_sha}}}}

    def prepare(*, altered_rows=None, altered_report=None, altered_settings=None, repin=True):
        s = canonical(settings if altered_settings is None else altered_settings)
        r = canonical(report if altered_report is None else altered_report)
        if repin:
            monkeypatch.setattr(module, "SETTINGS_SHA", digest(s))
            monkeypatch.setattr(module, "VERIFICATION_SHA", digest(r))
        return module.prepare_reference(s, r, source if altered_rows is None else canonical(altered_rows))

    prepare()  # Set inert trust pins; no model/scoring fixture.
    return settings, report, rows, prepare


def test_reference_is_exact_saved_prefix_and_deterministic(saved):
    _, _, rows, prepare = saved
    raw, receipt = prepare()
    assert raw == canonical(rows[:64])
    assert prepare() == (raw, receipt)
    assert receipt["reference_targets_sha256"] == digest(canonical([r["target_id"] for r in rows[:64]]))
    assert receipt["source"]["version_id"] == "1"
    assert receipt["source_rows"] == 70 and receipt["reference_rows"] == 64
    for key in ("model_execution", "reference_published", "cuda_parity_verified", "execution_authorized"):
        assert receipt[key] is False


@pytest.mark.parametrize("kind", ["logit", "label", "reorder", "omit", "duplicate", "extra"])
def test_changed_prediction_file_is_rejected(saved, kind):
    _, _, rows, prepare = saved
    rows = copy.deepcopy(rows)
    if kind == "logit":
        rows[-1]["logit"] += 1
    elif kind == "label":
        rows[-1]["label"] = 1 - rows[-1]["label"]
    elif kind == "reorder":
        rows.reverse()
    elif kind == "omit":
        rows.pop()
    elif kind == "duplicate":
        rows[-1] = rows[0]
    else:
        rows[0]["probability"] = .5
    with pytest.raises(ValueError):
        prepare(altered_rows=rows)


@pytest.mark.parametrize("field,value", [("status", "failed"), ("final_test_access", True),
    ("job_id", "aijob-other"), ("request_sha256", "d" * 64), ("image_digest", "sha256:" + "e" * 64),
    ("checkpoint", "f" * 64), ("version_id", "null"), ("count", 69), ("targets", "0" * 64)])
def test_unapproved_or_inconsistent_source_is_rejected(saved, field, value):
    _, report, _, prepare = saved
    report = copy.deepcopy(report)
    if field == "status":
        report[field] = value
    elif field == "final_test_access":
        report["result"][field] = value
    elif field in ("job_id", "request_sha256", "image_digest"):
        report["context"][field] = value
    elif field == "checkpoint":
        report["result"]["checkpoint_origin"]["checkpoint"]["sha256"] = value
    elif field == "version_id":
        report["inventory"]["calibration-predictions.json"][field] = value
    else:
        report["audit"]["roles"]["calibration"]["row_count" if field == "count" else "row_identity_sha256"] = value
    with pytest.raises(ValueError):
        prepare(altered_report=report)


def test_supplied_receipt_cannot_approve_its_own_modified_bytes(saved):
    _, report, _, prepare = saved
    report = copy.deepcopy(report)
    report["invented"] = "unreviewed"
    with pytest.raises(ValueError, match="trust pin"):
        prepare(altered_report=report, repin=False)


@pytest.mark.parametrize("field,value", [("scope", "production"), ("gates_passed", False),
                                        ("decision", "stop")])
def test_ineligible_settings_are_rejected(saved, field, value):
    settings, _, _, prepare = saved
    settings = {**settings, field: value}
    with pytest.raises(ValueError):
        prepare(altered_settings=settings)


def test_oversize_inputs_reject_before_json_parsing():
    with pytest.raises(ValueError):
        module.prepare_reference(b"x" * 65537, b"", b"")
