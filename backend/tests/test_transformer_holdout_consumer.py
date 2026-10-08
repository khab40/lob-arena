import copy

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.batches import iter_batches  # noqa: E402
from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.holdout_baseline import pair_saved_predictions  # noqa: E402
from app.ml.transformer.holdout_context import check_parity, verify_context  # noqa: E402
from app.ml.transformer.holdout_data import HoldoutInputs  # noqa: E402
from app.ml.transformer.holdout_spec import HoldoutRequest  # noqa: E402
from app.ml.transformer.normalization import fit_normalization  # noqa: E402
from transformer_holdout_fixtures import baseline_rows, final_inputs  # noqa: E402


def opened(tmp_path, **kwargs):
    req, gate, contract, args, envelope = final_inputs(tmp_path, **kwargs)
    data = HoldoutInputs.open(request=req, gate=gate, contract=contract, artifact_root=tmp_path)
    return data, req, gate, args, envelope


def test_signature_external_approval_and_parity_precede_access(tmp_path, monkeypatch):
    data, req, gate, _, envelope = opened(tmp_path)
    pins = dict(approved_request_sha256=req.sha256(), trusted_public_key=req.context_public_key)
    assert verify_context(req, envelope, **pins) == envelope["context"]
    for bad in ({"approved_request_sha256": "0" * 64}, {"trusted_public_key": "0" * 64}):
        with pytest.raises(ValueError, match="authorization"):
            verify_context(req, envelope, **{**pins, **bad})
    changed = copy.deepcopy(envelope)
    changed["context"]["job_id"] = "aijob-another"
    with pytest.raises(Exception):
        verify_context(req, changed, **pins)
    monkeypatch.setattr("app.ml.transformer.holdout_data._load_bound_manifest",
                        lambda *a, **k: pytest.fail("manifest read before gate"))
    wrong = req.model_copy(update={"nonce": "f" * 32})
    with pytest.raises(ValueError, match="final access"):
        HoldoutInputs.open(request=wrong, gate=gate, contract=data.contract, artifact_root=tmp_path)


@pytest.mark.parametrize("defect", ["logit", "nan", "order", "label", "count"])
def test_parity_failure(defect, tmp_path):
    _, req, gate, _, _ = opened(tmp_path)
    target = ("a" * 64,)
    label, logits = (1,), (1.0,)
    if defect == "logit":
        logits = (1.01,)
    elif defect == "nan":
        logits = (float("nan"),)
    elif defect == "order":
        target = ("b" * 64,)
    elif defect == "label":
        label = (0,)
    else:
        logits = ()
    raw = b'[{"label":1,"logit":1.0,"target_id":"' + b"a" * 64 + b'"}]'
    with pytest.raises(ValueError):
        check_parity(req, gate.context, raw, target, label, logits)


def test_final_adapter_reuses_training_binding_and_resets_history(tmp_path):
    data, _, _, _, _ = opened(tmp_path)
    dev = DevelopmentInputs.open(**__import__("transformer_input_fixtures").make_inputs(tmp_path / "other"))
    norm = fit_normalization(dev)
    batches = list(iter_batches(data, norm, batch_size=2))
    assert len(batches) == 2
    assert batches[0].valid_steps[0].sum() == 1
    assert batches[0].valid_steps[1].sum() == 2
    assert batches[0].missing_features[0, -1, 1]
    assert not batches[0].missing_features[0, 0].any()
    assert batches[0].contract_sha256 == data.contract.sha256()
    assert batches[0].folds == ("test", "test")
    assert not np.any(batches[0].causal_allowed & ~np.tri(64, dtype=bool))
    with pytest.raises(ValueError):
        list(data.windows("train"))


@pytest.mark.parametrize("defect", ["future", "mask", "padding", "value", "duplicate", "drop", "reorder", "tie"])
def test_corrupt_final_sequence_rejected_completely(tmp_path, defect):
    def mutate(rows, fold):
        if fold != "validation":
            return
        row = rows[-1]
        if defect == "future":
            row["sequence_timestamps_ns"][-1] += 1
        elif defect == "mask":
            row["attention_mask"][-2] = False
        elif defect == "padding":
            row["feature_vectors"][0][0] = 1.
        elif defect == "value":
            row["feature_vectors"][-1][0] += 1
        elif defect == "duplicate":
            rows[-1] = rows[-2]
        elif defect == "drop":
            rows.pop()
        elif defect == "reorder":
            rows[-1], rows[-2] = rows[-2], rows[-1]
        else:
            rows[2]["sequence_row_ids"][-2] = rows[3]["target_supervised_row_id"]
    with pytest.raises(ValueError):
        opened(tmp_path, mutate=mutate)


@pytest.mark.parametrize("defect", ["label", "order", "duplicate", "drop", "probability", "identity", "fold", "session"])
def test_saved_g8_pairing_rejects_different_population(tmp_path, defect):
    data, _, _, _, _ = opened(tmp_path)
    saved = list(baseline_rows(data))
    assert pair_saved_predictions(data, saved)[1].tolist() == [.1, .9, .1, .9]
    if defect == "label":
        saved[-1]["label"] = 0
    elif defect == "order":
        saved[-1], saved[-2] = saved[-2], saved[-1]
    elif defect == "duplicate":
        saved[-1] = saved[-2]
    elif defect == "drop":
        saved.pop()
    elif defect == "probability":
        saved[-1]["calibrated_probability"] = None
    elif defect == "identity":
        saved[-1]["prediction_row_id"] = "0" * 64
    elif defect == "fold":
        saved[-1]["fold"] = "validation"
    else:
        saved[-1]["base_session_id"] = "different"
    with pytest.raises(ValueError):
        pair_saved_predictions(data, saved)


@pytest.mark.parametrize("field,value", [("batch_size", 128), ("fitting", True), ("timeout_seconds", 7200),
    ("reference_atol", .01), ("settings_sha256", "0" * 64), ("image_repository", "x" * 65)])
def test_request_rejects_relaxed_protocol_bounds(tmp_path, field, value):
    _, req, _, _, _ = opened(tmp_path)
    raw = req.model_dump(mode="json")
    raw[field] = value
    import json
    with pytest.raises(ValueError):
        HoldoutRequest.model_validate_json(json.dumps(raw))
