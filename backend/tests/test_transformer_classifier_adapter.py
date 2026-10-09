"""Declared fake-consumer outputs over invented metadata; no model execution."""
from dataclasses import replace
from types import SimpleNamespace
import time

import pytest

np = pytest.importorskip("numpy")

import app.ml.transformer.classifier_package as classifier  # noqa: E402
from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.market_data.projections import (  # noqa: E402
    SequenceProjectionManifest, SequenceProjectionShard, TabularProjectionManifest,
)
from transformer_settings_fixtures import SettingsFixture, sha  # noqa: E402

TARGETS = ("a" * 64, "b" * 64, "c" * 64)
LABELS = (0, 1, 1)


@pytest.fixture
def environment(monkeypatch, tmp_path):
    fixture = SettingsFixture()
    root, train = fixture.contract.root, fixture.contract.training_shards[0]
    validation = train.model_copy(update={"fold": "validation", "base_session_id": "fixture-validation",
        "run_id": "fixture-validation", "rows": train.rows.model_copy(update={"uri": "validation.parquet"})})
    common = dict(access_scope="development", root_release_id=root.release_id, root_sha256=root.canonical_hash(),
        protocol_sha256=root.protocol_sha256, corpus_sha256=root.corpus_sha256, assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256, folds=("train", "validation"))
    tabular = TabularProjectionManifest(projection_id="fixture-tabular", shards=(train, validation), **common)
    sequences = SequenceProjectionManifest(projection_id="fixture-sequences", shards=tuple(
        SequenceProjectionShard(fold=s.fold, base_session_id=s.base_session_id, run_id=s.run_id,
            replay_manifest_sha256=s.replay_manifest_sha256, sequence_count=s.supervised_row_count,
            sequence_length=64, sequence_identity_sha256=s.row_identity_sha256,
            sequences=dict(uri=s.fold + "-sequence.parquet", sha256="e" * 64, size_bytes=1,
                           logical_name=s.fold, schema_version="causal_feature_sequences_v1"))
        for s in (train, validation)), **common)
    (tmp_path / "tabular.json").write_bytes(tabular.canonical_bytes())
    (tmp_path / "sequence.json").write_bytes(sequences.canonical_bytes())
    fixture.contract = fixture.contract.model_copy(update={"tabular_manifest_sha256": sha(tabular.canonical_bytes()),
        "sequence_manifest_sha256": sha(sequences.canonical_bytes())})
    fixture.report = fixture.make_report()
    fixture.report["result"]["calibration"]["temperature"] = 2.0
    for point, threshold in zip(fixture.report["result"]["comparison"]["transformer_selected_operating_points"],
                                (.9, .5, .1), strict=True):
        point["threshold"] = threshold
    release = fixture.release()
    package = classifier.prepare_classifier(release.canonical_bytes(), fixture.reader,
        expected_sha256=release.sha256(), **fixture.pins)
    dataset = DevelopmentInputs(package.contract.root, tabular, sequences, tmp_path, package.contract)
    opens, calls = [], []

    def opened(**kwargs):
        opens.append(kwargs)
        return dataset

    monkeypatch.setattr(DevelopmentInputs, "open", opened)
    monkeypatch.setattr(DevelopmentInputs, "windows", lambda self, fold:
        iter(SimpleNamespace(target_id=target, label=label)
             for target, label in zip(TARGETS, LABELS, strict=True)))

    class FakeConsumer:
        measurements = {"scope": "inert_declared_output", "rows": 3}

        def infer(self, actual, normalizer, *, fold, tabular_path, sequence_path):
            calls.append((actual, normalizer, fold))
            return TARGETS, LABELS, np.asarray([-2., 0., 2.])

    monkeypatch.setattr(classifier, "_consumer", lambda *args: FakeConsumer())
    args = {"tabular_path": tmp_path / "tabular.json", "sequence_path": tmp_path / "sequence.json",
            "artifact_root": tmp_path, "expires": time.monotonic() + 60}
    return package, dataset, args, opens, calls


def test_frozen_calibration_boundaries_and_original_order(environment):
    package, dataset, args, opens, calls = environment
    result = classifier.research_inference(package, **args)
    assert tuple(row.target_id for row in result.predictions) == TARGETS
    assert tuple(row.label for row in result.predictions) == LABELS
    assert tuple(row.alert for row in result.predictions) == (False, True, True)
    assert [row.probability for row in result.predictions] == pytest.approx([.2689414213699951, .5, .7310585786300049])
    assert all(row.release_id == package.release.release_id and row.mode == "balanced" for row in result.predictions)
    assert opens[0]["root"] == package.contract.root
    assert opens[0]["tabular_sha256"] == package.contract.tabular_manifest_sha256
    assert opens[0]["sequence_sha256"] == package.contract.sequence_manifest_sha256
    assert calls == [(dataset, package.normalization, "validation")]
    assert not any(row.alert for row in classifier.research_inference(package, **args, mode="high_precision").predictions)
    assert all(row.alert for row in classifier.research_inference(package, **args, mode="high_recall").predictions)


@pytest.mark.parametrize("kwargs", [{"fold": "test"}, {"fold": None}, {"mode": "refit"},
    {"expires": float("inf")}, {"expires": float("nan")}, {"expires": 0}, {"expires": True}])
def test_invalid_scope_or_deadline_has_zero_opens_or_numerical_calls(environment, kwargs):
    package, _, args, opens, calls = environment
    with pytest.raises(ValueError):
        classifier.research_inference(package, **{**args, **kwargs})
    assert opens == calls == []


@pytest.mark.parametrize("defect", ["contract", "features", "final", "type"])
def test_changed_development_contract_rejected_before_consumer(environment, monkeypatch, defect):
    package, dataset, args, _, calls = environment
    if defect == "type":
        changed = object()
    elif defect == "final":
        changed = replace(dataset, tabular=SimpleNamespace(access_scope="final_test"))
    else:
        field, value = ("sequence_manifest_sha256", "0" * 64) if defect == "contract" else (
            "ordered_features", package.contract.ordered_features[::-1])
        changed = replace(dataset, contract=package.contract.model_copy(update={field: value}))
    monkeypatch.setattr(DevelopmentInputs, "open", lambda **kwargs: changed)
    with pytest.raises(ValueError, match="input contract"):
        classifier.research_inference(package, **args)
    assert calls == []


@pytest.mark.parametrize("defect", ["reverse", "labels", "short", "matrix", "nan", "inf", "string", "boolean"])
def test_invalid_declared_output_returns_no_scores(environment, monkeypatch, defect):
    package, _, args, _, _ = environment
    ids, labels, values = TARGETS, LABELS, [-2., 0., 2.]
    if defect == "reverse":
        ids = TARGETS[::-1]
    elif defect == "labels":
        labels = (1, 1, 1)
    elif defect == "short":
        values.pop()
    elif defect == "matrix":
        values = [values]
    elif defect in ("nan", "inf"):
        values[1] = float(defect)
    elif defect == "string":
        values = ["-2", "0", "2"]
    else:
        values = [False, True, True]
    fake = SimpleNamespace(infer=lambda *a, **k: (ids, labels, np.asarray(values)), measurements={})
    monkeypatch.setattr(classifier, "_consumer", lambda *args: fake)
    with pytest.raises(ValueError, match="order or labels|finite aligned"):
        classifier.research_inference(package, **args)


@pytest.mark.parametrize("targets", [(), ("a" * 64,) * 3, ("invalid", *TARGETS[1:])])
def test_invalid_verified_target_inventory_precedes_numerical_consumer(environment, monkeypatch, targets):
    package, _, args, _, calls = environment
    monkeypatch.setattr(DevelopmentInputs, "windows", lambda self, fold:
        iter(SimpleNamespace(target_id=target, label=0) for target in targets))
    with pytest.raises(ValueError, match="target identity"):
        classifier.research_inference(package, **args)
    assert calls == []


def test_changed_train_target_digest_precedes_numerical_consumer(environment):
    package, _, args, _, calls = environment
    with pytest.raises(ValueError, match="target identity"):
        classifier.research_inference(package, **args, fold="train")
    assert calls == []


