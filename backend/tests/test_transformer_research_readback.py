"""Adversarial saved-artifact checks, with no model execution."""
from dataclasses import asdict
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from app.ml.transformer import research_baseline as baseline  # noqa: E402
from app.ml.transformer.research_context import observed, verify  # noqa: E402
from app.ml.transformer.research_execution_spec import PROJECT, provider_spec, template  # noqa: E402
from app.ml.transformer.research_policy import Trial  # noqa: E402
from app.ml.transformer.research_readback import verify_trial  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402


def test_signed_context_rejects_resource_drift_and_wrong_request():
    signer = Ed25519PrivateKey.generate()
    req = template("smoke", "a" * 40, "sha256:" + "b" * 64,
                   signer.public_key().public_bytes_raw().hex(), "c" * 32, {})
    job = {"metadata": {"id": "aijob-abc123", "name": req["run_id"], "parent_id": PROJECT},
           "status": {"state": "RUNNING"}, "spec": provider_spec(req)}
    context = observed(job, req)
    envelope = {"context": context, "signature": signer.sign(canonical(context)).hex()}
    assert verify(envelope, req)["job_id"] == "aijob-abc123"
    with pytest.raises(ValueError):
        verify(envelope, {**req, "nonce": "d" * 32})
    job["spec"]["preset"] = "8gpu-128vcpu-1600gb"
    with pytest.raises(ValueError):
        observed(job, req)


def test_baseline_hash_checked_before_parquet_parsing(monkeypatch):
    def unexpected(*args):
        pytest.fail("untrusted parquet parsed")
    monkeypatch.setattr(baseline.pq, "read_table", unexpected)
    with pytest.raises(ValueError):
        baseline.load(b"x" * 618114, b"{}", {})


def test_baseline_alignment_requires_order_and_labels():
    split = SimpleNamespace(target_ids=("a", "b"), labels=np.array([0, 1]))
    baseline.align(split, {"target_ids": ("a", "b"), "labels": [0, 1]})
    for ids, labels in [(("b", "a"), [0, 1]), (("a", "b"), [1, 0])]:
        with pytest.raises(ValueError):
            baseline.align(split, {"target_ids": ids, "labels": labels})


def trial_fixture():
    loss = float(np.log(2))
    trial = Trial(64, .0003)
    item = {"sha256": "e" * 64, "size_bytes": 10, "version_id": "one"}
    checkpoints = [{**item, "epoch": i, "name": f"epoch-{i:02}.pt",
                    "object_name": f"search-64-0003-epoch-{i:02}.pt"} for i in range(1, 7)]
    result = {"trial": asdict(trial), "trial_sha256": trial.sha256(), "selection_log_loss": loss,
        "selection_f1_at_half": 2/3, "progress": {"epoch": 6, "history": [
            {"epoch": i, "selection_log_loss": loss} for i in range(1, 7)]},
        "selected_epoch": 1, "selected_checkpoint": deepcopy(checkpoints[0]),
        "published_checkpoints": checkpoints}
    ledger = b"".join(canonical({"run_id": "run", "target_id": t, "label": y}) + b"\n"
                      for t, y in (("a", 0), ("b", 1)))
    artifacts = {"target-ledger.jsonl": ledger, "selection-predictions.json": canonical([
        {"target_id": "a", "label": 0, "logit": 0.}, {"target_id": "b", "label": 1, "logit": 0.}])}
    return result, artifacts, {c["object_name"]: item.copy() for c in checkpoints}, {
        "groups": [{"role": "selection", "shards": [{"run_id": "run"}]}]}


def test_selected_epoch_verified_from_predictions_and_complete_history():
    args = trial_fixture()
    assert verify_trial(*args, slot="search-64-0003")["status"] == "verified"


@pytest.mark.parametrize("mutation", ["loss", "nan", "early_stop", "epoch", "order", "checkpoint"])
def test_trial_tampering_is_rejected(mutation):
    result, artifacts, inventory, metadata = trial_fixture()
    if mutation == "loss":
        result["selection_log_loss"] += .1
    elif mutation == "nan":
        result["selection_log_loss"] = float("nan")
    elif mutation == "early_stop":
        result["progress"]["history"].pop()
        result["progress"]["epoch"] = 5
    elif mutation == "epoch":
        result["selected_epoch"] = 2
    elif mutation == "order":
        artifacts["selection-predictions.json"] = canonical(json.loads(artifacts["selection-predictions.json"])[::-1])
    else:
        inventory.clear()
    with pytest.raises(ValueError):
        verify_trial(result, artifacts, inventory, metadata, slot="search-64-0003")


@pytest.mark.parametrize("mutation", ["other_epoch", "renamed_other_epoch", "name", "object_name",
    "receipt", "missing_publication", "duplicate_publication", "publication_version", "boolean_epoch"])
def test_rejects_inventoried_checkpoint_not_bound_to_best_epoch(mutation):
    result, artifacts, inventory, metadata = trial_fixture()
    selected = result["selected_checkpoint"]
    if mutation in {"other_epoch", "renamed_other_epoch"}:
        result["selected_checkpoint"] = deepcopy(result["published_checkpoints"][1])
        if mutation == "renamed_other_epoch":
            result["selected_checkpoint"]["epoch"] = 1
    elif mutation == "name":
        selected["name"] = "epoch-02.pt"
    elif mutation == "object_name":
        selected["object_name"] = "search-64-0003-epoch-02.pt"
    elif mutation == "receipt":
        selected["sha256"] = "f" * 64
        inventory[selected["object_name"]]["sha256"] = "f" * 64
    elif mutation == "missing_publication":
        result["published_checkpoints"].pop(0)
    elif mutation == "duplicate_publication":
        result["published_checkpoints"].append(deepcopy(selected))
    elif mutation == "publication_version":
        result["published_checkpoints"][0]["version_id"] = "another"
    else:
        selected["epoch"] = True
    with pytest.raises(ValueError, match="best epoch publication"):
        verify_trial(result, artifacts, inventory, metadata, slot="search-64-0003")


def test_rejects_checkpoint_from_another_slot_even_with_valid_inventory():
    with pytest.raises(ValueError, match="best epoch publication"):
        verify_trial(*trial_fixture(), slot="search-128-0003")


def test_accepts_later_best_epoch_in_a_confirmation_slot():
    result, artifacts, inventory, metadata = trial_fixture()
    trial = Trial(64, .0003, seed=7)
    result.update(trial=asdict(trial), trial_sha256=trial.sha256(), selected_epoch=2)
    result["progress"]["history"][0]["selection_log_loss"] += .1
    result["progress"]["history"].append({"epoch": 7, "selection_log_loss": result["selection_log_loss"]})
    result["progress"]["epoch"] = 7
    seventh = {**result["published_checkpoints"][-1], "epoch": 7, "name": "epoch-07.pt",
               "object_name": "search-64-0003-epoch-07.pt"}
    result["published_checkpoints"].append(seventh)
    inventory[seventh["object_name"]] = {k: seventh[k] for k in ("sha256", "size_bytes", "version_id")}
    for item in result["published_checkpoints"]:
        old_name = item["object_name"]
        item["object_name"] = "seed-7-" + item["name"]
        inventory[item["object_name"]] = inventory.pop(old_name)
    result["selected_checkpoint"] = deepcopy(result["published_checkpoints"][1])
    assert verify_trial(result, artifacts, inventory, metadata, slot="seed-7")["status"] == "verified"
