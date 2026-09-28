import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.batches import iter_batches  # noqa: E402
from app.ml.transformer.contracts import Normalization  # noqa: E402
from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.normalization import (  # noqa: E402
    fit_normalization, load_normalization, save_normalization,
)
from transformer_input_fixtures import make_inputs  # noqa: E402


def test_unique_training_rows_define_population_statistics(tmp_path):
    dataset = DevelopmentInputs.open(**make_inputs(tmp_path))
    normalization = fit_normalization(dataset)
    assert normalization.fitting_rows == 4
    assert normalization.observed_counts[:5] == (4, 0, 4, 4, 3)
    assert normalization.means[:5] == (2.5, 0, 3, 0, 7)
    assert normalization.scales[0] == pytest.approx(np.sqrt(1.25))
    assert normalization.scales[1:4] == (1, 1, 1)
    path = tmp_path / "normalization.json"
    digest = save_normalization(normalization, path)
    restored = load_normalization(path, expected_sha256=digest, contract=dataset.contract)
    assert restored.canonical_bytes() == normalization.canonical_bytes()
    with pytest.raises(FileExistsError):
        save_normalization(normalization, path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        load_normalization(path, expected_sha256=digest, contract=dataset.contract)


def test_validation_changes_cannot_change_fitted_normalization(tmp_path):
    a = DevelopmentInputs.open(**make_inputs(tmp_path / "a"))
    b = DevelopmentInputs.open(**make_inputs(tmp_path / "b", validation_shift=1e6, validation_flip_labels=True))
    first, second = fit_normalization(a), fit_normalization(b)
    assert a.contract.sha256() != b.contract.sha256()
    assert first.canonical_bytes() == second.canonical_bytes()
    before = first.canonical_bytes()
    batches = list(iter_batches(b, first, fold="validation"))
    assert len(batches[0].target_ids) == 4
    assert first.canonical_bytes() == before


def test_masks_missingness_and_attention_have_explicit_semantics(tmp_path):
    data = DevelopmentInputs.open(**make_inputs(tmp_path))
    batch = next(iter_batches(data, fit_normalization(data)))
    assert batch.values.dtype == np.float32
    assert batch.values.shape == (8, 64, 60)
    assert np.isfinite(batch.values).all()
    assert not batch.values[0, :-1].any()
    assert not batch.missing_features[0, :-1].any()
    assert batch.missing_features[0, -1, 1]
    assert batch.missing_features[0, -1, 4]
    assert not batch.missing_features[0, -1, 3]  # Observed zero, not missing.
    assert batch.values[0, -1, 3] == 0
    assert not batch.causal_allowed[0, :-1].any()
    assert not batch.causal_allowed[0, :, :-1].any()
    assert batch.causal_allowed[0, -1, -1]
    assert batch.causal_allowed[1, -1, -2]
    assert not batch.causal_allowed[1, -2, -1]
    with pytest.raises(ValueError):
        batch.values[0, -1, 0] = 0


def test_labels_do_not_enter_input_values_or_masks(tmp_path):
    a = DevelopmentInputs.open(**make_inputs(tmp_path / "a"))
    b = DevelopmentInputs.open(**make_inputs(tmp_path / "b", flip_labels=True))
    first = next(iter_batches(a, fit_normalization(a)))
    second = next(iter_batches(b, fit_normalization(b)))
    np.testing.assert_array_equal(first.values, second.values)
    np.testing.assert_array_equal(first.missing_features, second.missing_features)
    np.testing.assert_array_equal(first.causal_allowed, second.causal_allowed)
    np.testing.assert_array_equal(first.labels, 1 - second.labels)
    assert first.target_ids == second.target_ids


def test_batch_boundaries_never_change_logical_outputs(tmp_path):
    data = DevelopmentInputs.open(**make_inputs(tmp_path))
    normalization = fit_normalization(data)
    reference = list(iter_batches(data, normalization, batch_size=1))
    for size in (3, 64, 256):
        actual = list(iter_batches(data, normalization, batch_size=size))
        assert tuple(t for b in actual for t in b.target_ids) == tuple(t for b in reference for t in b.target_ids)
        for name in ("values", "valid_steps", "missing_features", "causal_allowed", "timestamps_ns", "labels"):
            np.testing.assert_array_equal(np.concatenate([getattr(b, name) for b in actual]),
                                          np.concatenate([getattr(b, name) for b in reference]))


def test_training_binding_changes_fail_closed(tmp_path):
    a = DevelopmentInputs.open(**make_inputs(tmp_path / "a"))
    b = DevelopmentInputs.open(**make_inputs(tmp_path / "b", count=5))
    normalization = fit_normalization(a)
    path = tmp_path / "normalization.json"
    sha = save_normalization(normalization, path)
    with pytest.raises(ValueError, match="lineage"):
        load_normalization(path, expected_sha256=sha, contract=b.contract)
    with pytest.raises(ValueError, match="lineage"):
        list(iter_batches(b, normalization))
    with pytest.raises(ValueError, match="train/validation"):
        list(iter_batches(a, normalization, fold="test"))


@pytest.mark.parametrize("field,value", [("means", float("inf")), ("scales", 0), ("scales", -1),
                                        ("observed_counts", 5), ("observed_counts", 1.5)])
def test_invalid_normalization_statistics_rejected(tmp_path, field, value):
    data = DevelopmentInputs.open(**make_inputs(tmp_path))
    payload = fit_normalization(data).model_dump(mode="json")
    payload[field][0] = value
    with pytest.raises(ValueError):
        Normalization.model_validate(payload)


def test_float32_overflow_is_rejected_instead_of_emitting_infinity(tmp_path):
    data = DevelopmentInputs.open(**make_inputs(tmp_path, validation_shift=1e100))
    normalization = fit_normalization(data)
    with pytest.raises((FloatingPointError, ValueError)):
        list(iter_batches(data, normalization, fold="validation"))


@pytest.mark.parametrize("size", [0, -1, True, 1025])
def test_invalid_batch_size_is_rejected(tmp_path, size):
    data = DevelopmentInputs.open(**make_inputs(tmp_path))
    with pytest.raises(ValueError, match="batch size"):
        list(iter_batches(data, fit_normalization(data), batch_size=size))
