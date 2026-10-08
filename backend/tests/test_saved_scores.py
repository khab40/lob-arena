import json

import pytest

from app.research.saved_score_io import canonical, checked_read, json_value, sha256, validate_private_roots
from app.research.saved_scores import THRESHOLDS, load_campaign
from tests.saved_score_fixtures import evidence


def load(directory, pin, tmp_path):
    return load_campaign(directory, (tmp_path / "public",), verification_sha=pin, expected_rows=3, expected_positives=1)


def test_both_detectors_preserve_targets_and_frozen_threshold_equality(tmp_path):
    directory, pin = evidence(tmp_path)
    campaign = load(directory, pin, tmp_path)
    catalog = campaign.catalog()
    assert catalog["kind"] == "saved_research_predictions"
    session = catalog["sessions"][0]["id"]
    first = campaign.page(session, "transformer", 0, 2)
    last = campaign.page(session, "transformer", first["next_offset"], 2)
    baseline = campaign.page(session, "lightgbm", 0, 3)
    assert [row["ordinal"] for row in first["rows"] + last["rows"]] == [0, 1, 2]
    assert [row["target_id"] for row in baseline["rows"]] == [row["target_id"] for row in campaign.page(session, "transformer", 0, 3)["rows"]]
    assert [row["alert"] for row in first["rows"]] == [False, True]
    assert first["rows"][1]["probability"] == THRESHOLDS["transformer"]
    assert all(row["alert"] for row in baseline["rows"])
    assert first["rows"][0]["timestamp_ns"] == "34560000000001"
    assert last["next_offset"] is None
    assert campaign.page(session, "transformer", 3, 1)["rows"] == []
    assert "private" not in json.dumps(catalog)
    assert first["provenance"] == baseline["provenance"] == catalog["provenance"]


@pytest.mark.parametrize("name", ["verification.json", "result.json", "predictions.json", "target-ledger.json",
                                 "receipts/predictions.json.json"])
def test_corruption_or_missing_receipt_fails_closed(tmp_path, name):
    directory, pin = evidence(tmp_path)
    (directory / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        load(directory, pin, tmp_path)


def test_forged_self_consistent_verification_does_not_supply_its_own_trust(tmp_path):
    directory, _pin = evidence(tmp_path)
    with pytest.raises(ValueError, match="bytes differ"):
        load_campaign(directory, (tmp_path / "public",))


@pytest.mark.parametrize("mutation", [
    lambda ledger, predictions, result: predictions.reverse(),
    lambda ledger, predictions, result: predictions.pop(),
    lambda ledger, predictions, result: predictions[0].update(probability=True),
    lambda ledger, predictions, result: predictions[0].update(probability=1.001),
    lambda ledger, predictions, result: predictions[0].update(label=False),
    lambda ledger, predictions, result: predictions[0].update(extra="untrusted"),
    lambda ledger, predictions, result: predictions[0].update(family="unverified-family"),
    lambda ledger, predictions, result: ledger[0].update(prediction_timestamp_ns=True),
    lambda ledger, predictions, result: result.update(settings_sha256="0" * 64),
    lambda ledger, predictions, result: result.update(fitting=True),
    lambda ledger, predictions, result: result["execution_bindings"].update(source_commit="0" * 40),
    lambda ledger, predictions, result: result["measurements"].update(ordered_targets_sha256="0" * 64),
])
def test_authenticated_but_invalid_schema_alignment_or_lineage_rejected(tmp_path, mutation):
    directory, pin = evidence(tmp_path, mutation=mutation)
    with pytest.raises(ValueError):
        load(directory, pin, tmp_path)


def test_duplicate_target_rejected(tmp_path):
    def duplicate(ledger, predictions, _result):
        ledger[1]["target_id"] = ledger[0]["target_id"]
        predictions[1]["target_id"] = ledger[0]["target_id"]
    directory, pin = evidence(tmp_path, mutation=duplicate)
    with pytest.raises(ValueError, match="identity differs"):
        load(directory, pin, tmp_path)


@pytest.mark.parametrize("raw", [b'{"score":1,"score":2}', b'{"score":NaN}', b'{"score":Infinity}'])
def test_json_rejects_ambiguous_or_nonfinite_values(raw):
    with pytest.raises(ValueError):
        json_value(raw)


def test_receipt_version_and_size_are_exact(tmp_path):
    directory, pin = evidence(tmp_path)
    sidecar = directory / "receipts/result.json.json"
    reference = json.loads(sidecar.read_bytes())
    reference["version_id"] = "2"
    sidecar.write_bytes(canonical(reference))
    with pytest.raises(ValueError):
        load(directory, pin, tmp_path)
    with pytest.raises(ValueError):
        checked_read(directory / "predictions.json", bound=10, digest=sha256(b"{}"))


def test_private_and_generic_artifact_roots_must_be_disjoint(tmp_path):
    directory, _pin = evidence(tmp_path)
    for root in (tmp_path, directory, directory / "public"):
        with pytest.raises(ValueError, match="overlaps"):
            validate_private_roots(directory, (root,))
    with pytest.raises(ValueError):
        validate_private_roots(None, (tmp_path,))


@pytest.mark.parametrize("target", ["predictions.json", "receipts", "directory"])
def test_symlinked_private_paths_rejected(tmp_path, target):
    directory, pin = evidence(tmp_path)
    path = directory if target == "directory" else directory / target
    retained = path.with_name(path.name + "-retained")
    path.rename(retained)
    path.symlink_to(retained, target_is_directory=retained.is_dir())
    with pytest.raises(ValueError, match="symlink"):
        load(directory, pin, tmp_path)


@pytest.mark.parametrize("offset,limit", [(-1, 1), (4, 1), (0, 0), (0, 101), (True, 1)])
def test_page_bounds_and_unavailable_sources(tmp_path, offset, limit):
    directory, pin = evidence(tmp_path)
    campaign = load(directory, pin, tmp_path)
    session = campaign.catalog()["sessions"][0]["id"]
    with pytest.raises(ValueError):
        campaign.page(session, "transformer", offset, limit)
    with pytest.raises(LookupError):
        campaign.page("../private", "transformer", 0, 1)
    with pytest.raises(LookupError):
        campaign.page(session, "hybrid", 0, 1)
