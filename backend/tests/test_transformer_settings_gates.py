"""Gate failures and publication interruption must preserve research evidence."""
import json
import os

import pytest

from app.ml.transformer.settings_release import ArtifactRead, build_release, load_release, save_release
from transformer_settings_fixtures import SettingsFixture, encode, sha


@pytest.mark.parametrize("decision", ["stop_transformer", "inconclusive"])
@pytest.mark.parametrize("missing_calibration", [False, True])
def test_negative_decision_archives_without_serving(decision, missing_calibration, tmp_path):
    fixture = SettingsFixture()
    fixture.decision = decision
    if missing_calibration:
        fixture.report["result"]["calibration"] = None
        fixture.report["result"]["comparison"]["transformer_selected_operating_points"] = []
    release = fixture.release()
    path = tmp_path / "settings.json"
    checksum = save_release(release, path)
    restored = load_release(path.read_bytes(), fixture.reader, expected_sha256=checksum, **fixture.pins)
    assert restored.decision == decision
    assert restored.limitations == release.limitations
    with pytest.raises(ValueError, match="blocked"):
        restored.require_research_inference()
    with pytest.raises(ValueError, match="blocked"):
        restored.require_serving()


@pytest.mark.parametrize("gate", ["calibration", "points", "stability", "freeze", "boundary", "role", "floor"])
def test_missing_or_failed_gate_blocks_consumer(gate):
    fixture = SettingsFixture()
    result = fixture.report["result"]
    if gate == "calibration":
        result["calibration"] = None
    elif gate == "points":
        result["comparison"]["transformer_selected_operating_points"].pop()
    elif gate == "stability":
        result["stability"]["passed"] = False
    elif gate == "freeze":
        result["freeze_blocked"] = True
    elif gate == "boundary":
        result["calibration"]["boundary_hit"] = True
    elif gate == "role":
        result["calibration"]["fitting_role"] = "operating_point"
    else:
        result["comparison"]["unattainable_floor"] = True
    release = fixture.release()
    assert release.gates_passed is False
    with pytest.raises(ValueError, match="blocked"):
        release.require_research_inference()


@pytest.mark.parametrize("field,value", [("training_binding_sha256", "0" * 64), ("fitting_row_sha256", "0" * 64)])
def test_valid_normalizer_with_wrong_training_lineage_rejected(field, value):
    fixture = SettingsFixture()
    fixture.normalization = fixture.normalization.model_copy(update={field: value})
    bindings = fixture.report["result"]["checkpoint_origin"]["bindings"]
    bindings["normalization_sha256"] = fixture.normalization.sha256()
    fixture.report["result"]["execution_bindings"]["normalization_sha256"] = fixture.normalization.sha256()
    fixture.prepare()
    with pytest.raises(ValueError, match="training lineage"):
        build_release(fixture.artifacts, fixture.reader, **fixture.pins)


@pytest.mark.parametrize("defect", ["winner", "request", "job", "source", "checkpoint", "input_version"])
def test_internally_inconsistent_verified_receipt_rejected(defect):
    fixture = SettingsFixture()
    result = fixture.report["result"]
    if defect == "winner":
        result["winner_trial_sha256"] = "0" * 64
    elif defect == "request":
        result["request_sha256"] = "0" * 64
    elif defect == "job":
        result["job_id"] = "different-job"
    elif defect == "source":
        result["execution_bindings"]["source_binding"] = {}
    elif defect == "checkpoint":
        result["checkpoint_origin"]["checkpoint"]["epoch"] = 5
    fixture.prepare()
    if defect == "input_version":
        fixture.artifacts = fixture.artifacts.model_copy(update={"contract":
            fixture.artifacts.contract.model_copy(update={"version_id": "2"})})
    with pytest.raises(ValueError, match="differs"):
        build_release(fixture.artifacts, fixture.reader, **fixture.pins)


def test_publish_never_overwrites_existing_file_or_symlink(tmp_path):
    release = SettingsFixture().release()
    path = tmp_path / "settings.json"
    save_release(release, path)
    old = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_release(release, path)
    link = tmp_path / "alias.json"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        save_release(release, link)
    assert path.read_bytes() == old
    assert link.is_symlink()
    assert not list(tmp_path.glob(".settings-*"))


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_interrupted_publication_exposes_no_manifest_or_temporary_file(tmp_path, monkeypatch, operation):
    release = SettingsFixture().release()
    path = tmp_path / "settings.json"

    def fail(*args):
        raise OSError("injected interrupted publication")

    monkeypatch.setattr(os, operation, fail)
    with pytest.raises(OSError, match="interrupted"):
        save_release(release, path)
    assert not path.exists()
    assert not list(tmp_path.iterdir())


def test_contradictory_original_checkpoint_version_rejected():
    fixture = SettingsFixture().prepare()
    ref = fixture.artifacts.selection_verification
    report = json.loads(fixture.reads[ref.uri].data)
    report["inventory"]["search-128-0003-epoch-04.pt"]["version_id"] = "2"
    raw = encode(report)
    replacement = ref.model_copy(update={"uri": "evidence:sha256:" + sha(raw), "sha256": sha(raw),
                                         "size_bytes": len(raw)})
    fixture.reads[replacement.uri] = ArtifactRead(raw, replacement.version_id)
    fixture.artifacts = fixture.artifacts.model_copy(update={"selection_verification": replacement})
    with pytest.raises(ValueError, match="checkpoint inventory"):
        build_release(fixture.artifacts, fixture.reader, **{**fixture.pins, "selection_sha256": replacement.sha256})


def test_large_metadata_rejected_before_reader_is_called():
    fixture = SettingsFixture().prepare()
    fixture.artifacts = fixture.artifacts.model_copy(update={"verification":
        fixture.artifacts.verification.model_copy(update={"size_bytes": 3 * 1024 * 1024})})
    with pytest.raises(ValueError, match="read bound"):
        build_release(fixture.artifacts, fixture.reader, **fixture.pins)
    assert fixture.calls == []


@pytest.mark.parametrize("field,value", [("kind", "inference"), ("final_test_access", True), ("selected_epoch", 5)])
def test_contradictory_training_provenance_rejected(field, value):
    fixture = SettingsFixture().prepare()
    ref = fixture.artifacts.selection_verification
    report = json.loads(fixture.reads[ref.uri].data)
    report["result"][field] = value
    raw = encode(report)
    replacement = ref.model_copy(update={"uri": "evidence:sha256:" + sha(raw), "sha256": sha(raw),
                                         "size_bytes": len(raw)})
    fixture.reads[replacement.uri] = ArtifactRead(raw, replacement.version_id)
    fixture.artifacts = fixture.artifacts.model_copy(update={"selection_verification": replacement})
    with pytest.raises(ValueError, match="selection receipt"):
        build_release(fixture.artifacts, fixture.reader, **{**fixture.pins, "selection_sha256": replacement.sha256})
