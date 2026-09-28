import hashlib
import json

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.contracts import InputContract  # noqa: E402
from transformer_input_fixtures import make_inputs  # noqa: E402


def test_governed_sources_and_exact_target_order(tmp_path):
    dataset = DevelopmentInputs.open(**make_inputs(tmp_path))
    windows = list(dataset.windows())
    assert len(windows) == 8
    assert [w.fold for w in windows] == ["train"] * 4 + ["validation"] * 4
    assert len({w.target_id for w in windows}) == 8
    assert all(w.values.shape == (64, 60) for w in windows)
    assert dataset.contract.root.feature_release_id == "fixture-features"
    assert dataset.contract.root.feature_release_sha256 == "4" * 64
    assert windows[0].row_ids[:-1] == ("",) * 63
    assert windows[0].valid_steps.tolist() == [False] * 63 + [True]


def test_later_source_row_with_same_timestamp_is_rejected(tmp_path):
    def mutate(rows, fold):
        if fold == "train":
            rows[2]["sequence_row_ids"][-2] = rows[3]["target_supervised_row_id"]
            rows[2]["sequence_timestamps_ns"][-2] = rows[3]["cutoff_timestamp_ns"]
            rows[2]["feature_vectors"][-2] = rows[3]["feature_vectors"][-1]
    args = make_inputs(tmp_path, mutate=mutate)
    with pytest.raises(ValueError, match="exact causal source window"):
        DevelopmentInputs.open(**args)


@pytest.mark.parametrize("defect", ["future", "mask_hole", "mask_type", "padding_value",
                                    "padding_id", "dimension", "value", "duplicate", "drop", "reorder"])
def test_preflight_rejects_corrupt_late_rows_before_returning_adapter(tmp_path, defect):
    def mutate(rows, fold):
        if fold != "validation":
            return
        row = rows[-1]
        if defect == "future":
            row["sequence_timestamps_ns"][-2] = row["cutoff_timestamp_ns"] + 1
        elif defect == "mask_hole":
            row["attention_mask"][-2] = False
        elif defect == "mask_type":
            for item in rows:
                item["attention_mask"] = [int(v) for v in item["attention_mask"]]
        elif defect == "padding_value":
            row["feature_vectors"][0][0] = 1.0
        elif defect == "padding_id":
            row["sequence_row_ids"][0] = "unexpected"
        elif defect == "dimension":
            row["feature_vectors"][-1].pop()
        elif defect == "value":
            row["feature_vectors"][-1][0] += 1
        elif defect == "duplicate":
            rows[-1] = rows[-2]
        elif defect == "drop":
            rows.pop()
        elif defect == "reorder":
            rows[-1], rows[-2] = rows[-2], rows[-1]
    args = make_inputs(tmp_path, mutate=mutate)
    with pytest.raises(ValueError):
        DevelopmentInputs.open(**args)


def test_infinite_source_feature_rejected(tmp_path):
    def corrupt(row, fold, index):
        if index == 3:
            row["spread"] = float("inf")
    args = make_inputs(tmp_path, source_mutate=corrupt)
    with pytest.raises(ValueError, match="infinite"):
        DevelopmentInputs.open(**args)


def test_final_manifest_rejected_without_accessing_shards(tmp_path, monkeypatch):
    args = make_inputs(tmp_path)
    path = args["sequence_path"]
    value = json.loads(path.read_text())
    value.update(access_scope="final_test", folds=["test"])
    value["shards"] = [{**value["shards"][0], "fold": "test"}]
    path.write_text(json.dumps(value))
    args["sequence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr("app.ml.transformer.data._resolve", lambda *a: pytest.fail("shard accessed"))
    with pytest.raises(ValueError, match="before shard access"):
        DevelopmentInputs.open(**args)


def test_feature_order_and_manifest_hash_are_bound(tmp_path):
    args = make_inputs(tmp_path)
    dataset = DevelopmentInputs.open(**args)
    value = dataset.contract.model_dump()
    value["ordered_features"] = tuple(reversed(value["ordered_features"]))
    with pytest.raises(ValueError, match="ordered feature"):
        InputContract.model_validate(value)
    args["tabular_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="external SHA-256"):
        DevelopmentInputs.open(**args)
