"""Persistence and adversarial metadata tests; no training/scoring runtime."""
import json

import pytest

from app.features.pipeline import FEATURE_COLUMNS
from app.ml.transformer.settings_release import ArtifactRead, build_release, load_release, save_release
from app.ml.transformer.settings_schema import Artifact, SettingsRelease
from transformer_settings_fixtures import SettingsFixture, encode, sha


@pytest.fixture
def fixture():
    return SettingsFixture()


def load(raw, fixture, **kwargs):
    return load_release(raw, fixture.reader, expected_sha256=sha(raw), **fixture.pins, **kwargs)


def test_complete_round_trip_and_research_only_gate(fixture, tmp_path):
    release = fixture.release()
    path = tmp_path / "settings.json"
    checksum = save_release(release, path)
    restored = load(path.read_bytes(), fixture)
    assert restored == release
    assert restored.sha256() == checksum
    assert restored.release_id == "transformer-research-" + checksum
    assert restored.preprocessing.ordered_features == FEATURE_COLUMNS
    assert restored.lineage.training_binding_sha256 == fixture.normalization.training_binding_sha256
    assert restored.lineage.selected_epoch == 4
    assert (restored.training.width, restored.training.learning_rate, restored.training.seed) == (128, .0003, 42)
    restored.require_research_inference()
    with pytest.raises(ValueError, match="production serving"):
        restored.require_serving()
    assert restored.lineage.selection_job_id == "fixture-training-job"
    assert len(fixture.calls) == 14  # Seven bounded reads per complete validation.


@pytest.mark.parametrize("features", [FEATURE_COLUMNS[::-1], FEATURE_COLUMNS[:-1], (*FEATURE_COLUMNS, "extra")])
def test_consumer_feature_drift_fails_before_artifact_reads(fixture, features):
    release = fixture.release()
    fixture.calls.clear()
    with pytest.raises(ValueError, match="feature order"):
        load(release.canonical_bytes(), fixture, ordered_features=features)
    assert fixture.calls == []


def test_untrusted_manifest_hash_and_evidence_pins(fixture):
    release = fixture.release()
    fixture.calls.clear()
    with pytest.raises(ValueError, match="checksum"):
        load_release(release.canonical_bytes(), fixture.reader, expected_sha256="0" * 64, **fixture.pins)
    with pytest.raises(ValueError, match="trust pins"):
        build_release(fixture.artifacts, fixture.reader, **{**fixture.pins, "verification_sha256": "0" * 64})
    assert fixture.calls == []


@pytest.mark.parametrize("artifact", ["checkpoint", "contract", "normalization", "verification",
                                     "selection_verification", "decision"])
@pytest.mark.parametrize("defect", ["bytes", "version", "size", "missing"])
def test_reader_drift_or_missing_artifact_rejected(fixture, artifact, defect):
    release = fixture.release()
    ref = getattr(release.artifacts, artifact)
    read = fixture.reads[ref.uri]
    if defect == "missing":
        del fixture.reads[ref.uri]
    else:
        fixture.reads[ref.uri] = ArtifactRead(read.data + b"x" if defect == "size" else
                                            b"x" * len(read.data) if defect == "bytes" else read.data,
                                            "another-version" if defect == "version" else read.version_id)
    with pytest.raises((ValueError, KeyError)):
        load(release.canonical_bytes(), fixture)


@pytest.mark.parametrize("section,key,value", [
    (None, "schema_version", "future"), (None, "scope", "production"), (None, "unexpected", "execute"),
    ("training", "width", True), ("training", "width", 128.0), ("training", "seed", "42"),
    ("architecture", "input_dimension", 60), ("architecture", "pooling", "first_token"),
    ("preprocessing", "sequence_length", 32), ("preprocessing", "stride", 2),
    ("preprocessing", "cutoff", "future_allowed"), ("preprocessing", "history_reset", "global"),
])
def test_unsupported_or_unsafe_settings_rejected_before_reads(fixture, section, key, value):
    payload = fixture.release().model_dump(mode="json")
    (payload if section is None else payload[section])[key] = value
    fixture.calls.clear()
    with pytest.raises(ValueError):
        load(encode(payload), fixture)
    assert fixture.calls == []


@pytest.mark.parametrize("section,key,value", [
    ("training", "learning_rate", .001), ("lineage", "selected_epoch", 5),
    ("lineage", "feature_release_sha256", "0" * 64), (None, "temperature", 2.),
    (None, "decision", "inconclusive"), (None, "gates_passed", False),
])
def test_rehashed_manifest_cannot_rewrite_verified_selection(fixture, section, key, value):
    payload = fixture.release().model_dump(mode="json")
    (payload if section is None else payload[section])[key] = value
    with pytest.raises(ValueError, match="verified source evidence"):
        load(encode(payload), fixture)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1., 21.])
def test_nonfinite_or_out_of_range_temperature_rejected(fixture, value):
    payload = fixture.release().model_dump(mode="json")
    payload["temperature"] = value
    with pytest.raises(ValueError):
        load(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(), fixture)


@pytest.mark.parametrize("uri", ["https://example.org/model", "s3://user:pass@bucket/model", "s3://b/a?token=abc",
                                 "s3://b/a#fragment", "s3://b/../key", "s3://b/a%2Fb", "s3://b/a//b"])
def test_no_credentials_or_ambiguous_artifact_locations(uri):
    with pytest.raises(ValueError):
        Artifact(uri=uri, version_id="1", size_bytes=1, sha256="a" * 64)


def test_duplicate_json_and_noncanonical_manifest_rejected(fixture):
    raw = fixture.release().canonical_bytes()
    with pytest.raises(ValueError, match="duplicate"):
        load(raw.replace(b'{', b'{"scope":"research_only",', 1), fixture)
    with pytest.raises(ValueError, match="noncanonical"):
        load(raw + b"\n", fixture)


def test_immutable_models_do_not_accept_assignment(fixture):
    release = fixture.release()
    with pytest.raises(ValueError):
        release.temperature = 2.
    assert SettingsRelease.model_validate_json(release.canonical_bytes()) == release
