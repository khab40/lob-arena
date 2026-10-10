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


def forged(package, defect):
    if defect == "checkpoint":
        return replace(package, checkpoint_bytes=b"x" * len(package.checkpoint_bytes))
    if defect == "checkpoint_size":
        return replace(package, checkpoint_bytes=package.checkpoint_bytes + b"x")
    if defect == "normalization":
        return replace(package, normalization=package.normalization.model_copy(update={"means": (1.,) * 60}))
    if defect == "contract":
        return replace(package, contract=package.contract.model_copy(update={"sequence_manifest_sha256": "0" * 64}))
    if defect == "bindings":
        return replace(package, original_bindings=b"{}")
    if defect == "release":
        return replace(package, release=package.release.model_copy(update={"temperature": 2.0}))
    if defect == "settings":
        return replace(package, settings_bytes=package.settings_bytes + b"\n")
    if defect == "pins":
        return replace(package, trust_pins=tuple((name, "0" * 64) for name, _ in package.trust_pins))
    if defect == "missing_receipts":
        return replace(package, snapshots=())
    if defect == "duplicate_receipts":
        return replace(package, snapshots=(package.snapshots[0],) * 7)
    if defect == "direct":
        return type(package)(**{**vars(package), "snapshots": (), "trust_pins": ()})
    snapshots = list(package.snapshots)
    name, ref, read = snapshots[0]
    if defect == "receipt_version":
        read = ArtifactRead(read.data, "changed-version")
    elif defect == "receipt_size":
        ref = ref.model_copy(update={"size_bytes": ref.size_bytes + 1})
    elif defect == "receipt_sha":
        ref = ref.model_copy(update={"sha256": "0" * 64})
    elif defect == "receipt_bytes":
        read = ArtifactRead(b"x" * len(read.data), read.version_id)
    snapshots[0] = (name, ref, read)
    return replace(package, snapshots=tuple(snapshots))


@pytest.mark.parametrize("boundary", ["public", "gpu", "header"])
@pytest.mark.parametrize("defect", ["checkpoint", "checkpoint_size", "normalization", "contract", "bindings",
    "release", "settings", "pins", "missing_receipts", "duplicate_receipts", "direct",
    "receipt_version", "receipt_size", "receipt_sha", "receipt_bytes"])
def test_constructed_or_replaced_package_fails_before_opens_and_numerical_imports(monkeypatch, boundary, defect):
    _, package = prepared()
    changed = forged(package, defect)
    calls, numerical_imports = [], []
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in ("numpy", "torch") or name.startswith(("numpy.", "torch.")):
            numerical_imports.append(name)
            raise AssertionError("invalid package imported numerical modules")
        return original(name, *args, **kwargs)

    def never(*args, **kwargs):
        calls.append(True)
        raise AssertionError("invalid package reached source/numerical execution")

    monkeypatch.setattr(builtins, "__import__", guarded)
    gpu = importlib.import_module("app.ml.transformer.classifier_gpu")
    monkeypatch.setattr(gpu, "_numerical_runtime", never)
    monkeypatch.setattr(classifier, "_open_development", never)
    monkeypatch.setattr(classifier, "_consumer", never)
    with pytest.raises(ValueError):
        if boundary == "gpu":
            gpu.DedicatedGpuClassifier(changed, expires=time.monotonic() + 60)
        elif boundary == "header":
            classifier.verify_checkpoint_header(changed, header(package))
        else:
            classifier.research_inference(changed, tabular_path="unused", sequence_path="unused",
                artifact_root="unused", expires=time.monotonic() + 60)
    assert calls == numerical_imports == []


def test_reauthentication_uses_retained_original_pins_receipts_and_fresh_metadata():
    fixture, package = prepared()
    fixture.reads.clear()
    restored = classifier.reauthenticate_classifier(package)
    assert restored == package and restored is not package
    assert restored.settings_bytes == package.release.canonical_bytes()
    assert dict(restored.trust_pins) == {"expected_sha256": package.release.sha256(), **fixture.pins}
    assert classifier.checked_checkpoint_bytes(restored) is package.checkpoint_bytes


@pytest.mark.parametrize("defect", ["checkpoint", "checkpoint_size"])
def test_exact_checkpoint_check_precedes_deserialization(defect):
    _, package = prepared()
    with pytest.raises(ValueError, match="exact size or checksum"):
        classifier.checked_checkpoint_bytes(forged(package, defect))


def test_adapter_collection_skips_when_optional_numpy_is_absent(monkeypatch):
    original = builtins.__import__
    attempts = []

    def guarded(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            attempts.append(name)
            raise ModuleNotFoundError("inert missing optional NumPy", name=name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(pytest.skip.Exception, match="numpy"):
        runpy.run_path(str(Path(__file__).with_name("test_transformer_classifier_adapter.py")))
    assert attempts == ["numpy"]
