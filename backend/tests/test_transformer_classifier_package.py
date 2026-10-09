"""Invented metadata and inert checkpoint bytes only; never load Torch/weights."""
import builtins
import copy
from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path
import runpy
import time

import pytest

import app.ml.transformer.classifier_package as classifier
from app.ml.transformer.classifier_package import prepare_classifier, verify_checkpoint_header
from app.ml.transformer.settings_release import ArtifactRead
from transformer_settings_fixtures import SettingsFixture, sha


def prepared():
    fixture = SettingsFixture()
    raw = fixture.release().canonical_bytes()
    fixture.calls.clear()
    package = prepare_classifier(raw, fixture.reader, expected_sha256=sha(raw), **fixture.pins)
    return fixture, package


def header(package):
    return {"schema": "transformer_research_epoch_v1", "precision": "float32", "sampler_position": 0,
        "trial": {name: getattr(package.release.training, name) for name in
                  ("width", "learning_rate", "seed", "max_epochs", "batch_size", "patience")},
        "bindings": json.loads(package.original_bindings), "progress": {"epoch": 4},
        "model": {}, "optimizer": {"never_loaded": True}, "rng": {"never_restored": True}}


def test_authenticated_snapshots_keep_original_bytes_and_receipts():
    fixture, package = prepared()
    assert len(fixture.calls) == len(package.snapshots) == 7
    assert package.checkpoint_bytes is fixture.checkpoint
    for name, reference, snapshot in package.snapshots:
        assert reference == getattr(package.release.artifacts, name)
        assert snapshot.version_id == reference.version_id
        assert sha(snapshot.data) == reference.sha256
    fixture.reads.clear()
    assert package.checkpoint_bytes == fixture.checkpoint
    with pytest.raises(FrozenInstanceError):
        package.original_bindings = b"{}"
    with pytest.raises(ValueError, match="production serving"):
        package.release.require_serving()


@pytest.mark.parametrize("artifact", ["checkpoint", "normalization", "contract", "verification",
    "selection_verification", "comparison_summary", "decision"])
@pytest.mark.parametrize("defect", ["bytes", "version", "size"])
def test_package_drift_rejected_before_runtime(artifact, defect):
    fixture = SettingsFixture()
    release = fixture.release()
    ref = getattr(release.artifacts, artifact)
    old = fixture.reads[ref.uri]
    fixture.reads[ref.uri] = ArtifactRead(b"x" * len(old.data) if defect == "bytes" else
        old.data + b"x" if defect == "size" else old.data, "changed" if defect == "version" else old.version_id)
    with pytest.raises(ValueError, match="version, size or checksum"):
        prepare_classifier(release.canonical_bytes(), fixture.reader, expected_sha256=release.sha256(), **fixture.pins)


@pytest.mark.parametrize("pin", ["expected_sha256", "verification_sha256", "decision_sha256", "selection_sha256"])
def test_external_trust_pin_drift_has_no_artifact_reads(pin):
    fixture = SettingsFixture()
    release = fixture.release()
    fixture.calls.clear()
    pins = {"expected_sha256": release.sha256(), **fixture.pins, pin: "0" * 64}
    with pytest.raises(ValueError):
        prepare_classifier(release.canonical_bytes(), fixture.reader, **pins)
    assert fixture.calls == []


def test_changed_consumer_feature_order_has_no_artifact_reads():
    fixture = SettingsFixture()
    release = fixture.release()
    fixture.calls.clear()
    with pytest.raises(ValueError, match="feature order"):
        prepare_classifier(release.canonical_bytes(), fixture.reader, expected_sha256=release.sha256(),
            ordered_features=release.preprocessing.ordered_features[::-1], **fixture.pins)
    assert fixture.calls == []


@pytest.mark.parametrize("field", ["schema", "precision", "trial", "epoch", "bindings", "sampler", "extra"])
def test_selected_checkpoint_header_drift_rejected_without_deserialization(field):
    _, package = prepared()
    state = header(package)
    verify_checkpoint_header(package, state)
    changed = copy.deepcopy(state)
    if field in ("schema", "precision"):
        changed[field] = "changed"
    elif field == "trial":
        changed[field]["width"] = 128.0
    elif field == "epoch":
        changed["progress"]["epoch"] = 5
    elif field == "bindings":
        changed[field]["source_commit"] = "0" * 40
    elif field == "sampler":
        changed["sampler_position"] = False
    else:
        changed["future_schema_field"] = True
    with pytest.raises(ValueError, match="checkpoint schema"):
        verify_checkpoint_header(package, changed)


def test_metadata_import_and_preparation_do_not_import_torch(monkeypatch):
    original = builtins.__import__
    attempted = []

    def guarded(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            attempted.append(name)
            raise AssertionError("metadata imported numerical runtime")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    module = importlib.reload(__import__("app.ml.transformer.classifier_package", fromlist=["prepare_classifier"]))
    fixture = SettingsFixture()
    raw = fixture.release().canonical_bytes()
    package = module.prepare_classifier(raw, fixture.reader, expected_sha256=sha(raw), **fixture.pins)
    module.verify_checkpoint_header(package, header(package))
    assert attempted == []


