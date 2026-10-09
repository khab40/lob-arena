"""Authenticated research classifier metadata; numerical imports stay lazy."""
from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Integral, Real
from pathlib import Path
import time

from app.features.pipeline import FEATURE_COLUMNS
from .contracts import InputContract, Normalization
from .research_policy import Trial
from .settings_release import ArtifactRead, json_record, load_release
from .settings_schema import Artifact, Artifacts, SettingsRelease

PINS = ("expected_sha256", "verification_sha256", "decision_sha256", "selection_sha256")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _target_digest(targets):
    return hashlib.sha256("".join(t + "\n" for t in targets).encode()).hexdigest()


@dataclass(frozen=True)
class ClassifierPackage:
    release: SettingsRelease
    checkpoint_bytes: bytes
    contract: InputContract
    normalization: Normalization
    original_bindings: bytes
    snapshots: tuple  # (artifact name, original reference, exact ArtifactRead)
    settings_bytes: bytes
    trust_pins: tuple  # Original caller pins, never derived from the manifest.


def prepare_classifier(raw, reader, *, expected_sha256, verification_sha256,
                       decision_sha256, selection_sha256, ordered_features=FEATURE_COLUMNS):
    """Authenticate seven original artifacts once, retaining their exact receipts."""
    captured = {}

    def snapshot(reference):
        previous = captured.get(reference.uri)
        if previous is not None:
            if previous[0] != reference:
                raise ValueError("conflicting classifier artifact receipt")
            return previous[1]
        result = reader(reference)
        captured[reference.uri] = (reference, result)
        return result

    release = load_release(raw, snapshot, expected_sha256=expected_sha256,
        verification_sha256=verification_sha256, decision_sha256=decision_sha256,
        selection_sha256=selection_sha256, ordered_features=ordered_features)
    release.require_research_inference()
    snapshots = tuple((name, reference, captured[reference.uri][1])
                     for name in type(release.artifacts).model_fields
                     for reference in (getattr(release.artifacts, name),))
    records = {name: result.data for name, _, result in snapshots}
    bindings = json_record(records["selection_verification"])["result"]["bindings"]
    return ClassifierPackage(release, records["checkpoint"],
        InputContract.model_validate_json(records["contract"]),
        Normalization.model_validate_json(records["normalization"]), _canonical(bindings), snapshots, bytes(raw),
        tuple(zip(PINS, (expected_sha256, verification_sha256, decision_sha256, selection_sha256), strict=True)))


def reauthenticate_classifier(package):
    """Rebuild from retained pins/receipts before trusting constructed/replaced fields."""
    if (type(package) is not ClassifierPackage or type(package.settings_bytes) is not bytes
            or type(package.trust_pins) is not tuple or type(package.snapshots) is not tuple
            or type(package.release) is not SettingsRelease or type(package.contract) is not InputContract
            or type(package.normalization) is not Normalization or type(package.original_bindings) is not bytes
            or type(package.checkpoint_bytes) is not bytes):
        raise ValueError("classifier package authentication state differs")
    try:
        if (len(package.trust_pins) != len(PINS)
                or any(type(item) is not tuple or len(item) != 2 for item in package.trust_pins)
                or tuple(name for name, _ in package.trust_pins) != PINS
                or any(type(pin) is not str or len(pin) != 64
                       or any(c not in "0123456789abcdef" for c in pin) for _, pin in package.trust_pins)
                or len(package.snapshots) != len(Artifacts.model_fields)
                or any(type(item) is not tuple or len(item) != 3 for item in package.snapshots)
                or tuple(name for name, _, _ in package.snapshots) != tuple(Artifacts.model_fields)
                or any(type(ref) is not Artifact or type(read) is not ArtifactRead
                       for _, ref, read in package.snapshots)):
            raise ValueError("classifier package pins or original receipts differ")
        retained = {ref.uri: (ref, read) for _, ref, read in package.snapshots}
        if len(retained) != len(package.snapshots):
            raise ValueError("classifier package repeats an artifact location")

        def reader(reference):
            ref, read = retained[reference.uri]
            if ref != reference:
                raise ValueError("classifier package original reference differs")
            return read

        restored = prepare_classifier(package.settings_bytes, reader, **dict(package.trust_pins))
        if package != restored:
            raise ValueError("classifier package derived metadata or checkpoint differs")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("classifier package authentication state is incomplete") from error
    return restored


def checked_checkpoint_bytes(package):
    raw, ref = package.checkpoint_bytes, package.release.artifacts.checkpoint
    if (type(raw) is not bytes or len(raw) != ref.size_bytes
            or hashlib.sha256(raw).hexdigest() != ref.sha256):
        raise ValueError("classifier checkpoint exact size or checksum differs")
    return raw


def verify_checkpoint_header(package, state):
    """Validate only selected-state metadata; never restore optimizer or RNG."""
    package = reauthenticate_classifier(package)
    trial = {name: getattr(package.release.training, name) for name in Trial.__dataclass_fields__}
    try:
        valid = (type(state) is dict and set(state) == {
            "schema", "trial", "bindings", "model", "optimizer", "rng", "progress", "sampler_position", "precision"}
            and state["schema"] == "transformer_research_epoch_v1"
            and state["precision"] == package.release.architecture.precision
            and type(state["sampler_position"]) is int and state["sampler_position"] == 0
            and type(state["progress"]) is dict and type(state["progress"].get("epoch")) is int
            and state["progress"]["epoch"] == package.release.lineage.selected_epoch
            and _canonical(state["trial"]) == _canonical(trial)
            and _canonical(state["bindings"]) == package.original_bindings
            and isinstance(state["model"], dict))
    except (TypeError, ValueError, KeyError):
        valid = False
    if not valid:
        raise ValueError("classifier checkpoint schema, selected epoch or lineage differs")


def validate_development_inputs(package, dataset, *, tabular_path, sequence_path):
    """Bind actual development metadata back to its exact original source manifests."""
    from app.market_data.projections import SequenceProjectionManifest, TabularProjectionManifest, _load_bound_manifest
    from .data import DevelopmentInputs, baseline_order
    contract = package.contract
    if (type(dataset) is not DevelopmentInputs or type(dataset.contract) is not InputContract
            or type(dataset.root) is not type(contract.root) or dataset.root != contract.root
            or dataset.contract.canonical_bytes() != contract.canonical_bytes()
            or type(dataset.tabular) is not TabularProjectionManifest
            or type(dataset.sequences) is not SequenceProjectionManifest
            or dataset.tabular.access_scope != "development" or dataset.sequences.access_scope != "development"
            or not isinstance(dataset.artifact_root, Path)):
        raise ValueError("classifier development input contract differs")
    for manifest, path, expected_sha, model in (
            (dataset.tabular, tabular_path, contract.tabular_manifest_sha256, TabularProjectionManifest),
            (dataset.sequences, sequence_path, contract.sequence_manifest_sha256, SequenceProjectionManifest)):
        verified = _load_bound_manifest(Path(path), expected_sha256=expected_sha, model=model, root=contract.root)
        if manifest != verified:
            raise ValueError("classifier development manifest metadata differs from pinned source")
    training = tuple(sorted((s for s in dataset.tabular.shards if s.fold == "train"), key=baseline_order))
    if training != contract.training_shards:
        raise ValueError("classifier development training source binding differs")
    return dataset


def _open_development(package, *, tabular_path, sequence_path, artifact_root):
    from .data import DevelopmentInputs
    contract = package.contract
    dataset = DevelopmentInputs.open(root=contract.root, tabular_path=tabular_path,
        tabular_sha256=contract.tabular_manifest_sha256, sequence_path=sequence_path,
        sequence_sha256=contract.sequence_manifest_sha256, artifact_root=artifact_root)
    return validate_development_inputs(package, dataset, tabular_path=tabular_path, sequence_path=sequence_path)


def _consumer(package, expires):
    from .classifier_gpu import DedicatedGpuClassifier
    return DedicatedGpuClassifier(package, expires=expires)


@dataclass(frozen=True)
class ClassifierPrediction:
    target_id: str
    label: int
    release_id: str
    mode: str
    logit: float
    probability: float
    alert: bool


@dataclass(frozen=True)
class ClassifierResult:
    predictions: tuple[ClassifierPrediction, ...]
    measurements: tuple  # Immutable key/value runtime measurements; no event-to-alert claim.


