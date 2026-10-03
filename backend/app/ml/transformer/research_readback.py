"""Verify research artifacts without loading or executing model weights."""
import json
import math

import numpy as np

from .research_context import verify as verify_context
from .research_execution_spec import request_sha, validate
from .research_policy import Trial, improved
from .role_audit import verify_package
from .verification_spec import digest

AUDIT = {"role-audit.json", "target-ledger.jsonl", "input-contract.json", "normalization.json"}


def predictions(raw, ledger, role, metadata):
    runs = {s["run_id"] for g in metadata["groups"] if g["role"] == role for s in g["shards"]}
    expected = [(r["target_id"], r["label"]) for r in map(json.loads, ledger.splitlines()) if r["run_id"] in runs]
    rows = json.loads(raw)
    if ([(r["target_id"], r["label"]) for r in rows] != expected
            or any(set(r) != {"target_id", "label", "logit"} or not math.isfinite(r["logit"]) for r in rows)):
        raise ValueError("saved predictions differ from verified role/labels")
    return np.array([r["label"] for r in rows]), np.array([r["logit"] for r in rows])


def verify_trial(result, artifacts, inventory, metadata, *, slot):
    trial = Trial(**result["trial"])
    if result["trial_sha256"] != trial.sha256():
        raise ValueError("trial identity differs")
    labels, logits = predictions(artifacts["selection-predictions.json"], artifacts["target-ledger.jsonl"],
                                 "selection", metadata)
    loss = float(np.mean(np.logaddexp(0, logits) - labels * logits))
    positive = logits >= 0
    tp = int(np.sum(positive & (labels == 1)))
    f1 = 2 * tp / max(1, int(np.sum(positive)) + int(np.sum(labels)))
    if (not math.isfinite(result["selection_log_loss"]) or not math.isfinite(result["selection_f1_at_half"])
            or abs(loss - result["selection_log_loss"]) > 1e-9
            or abs(f1 - result["selection_f1_at_half"]) > 1e-9):
        raise ValueError("selection metrics differ from saved predictions")
    history = result["progress"]["history"]
    if not 1 <= len(history) <= 30 or result["progress"]["epoch"] != len(history):
        raise ValueError("invalid epoch history")
    best, best_epoch, stale = math.inf, 0, 0
    for epoch, row in enumerate(history, 1):
        if row["epoch"] != epoch or stale >= 5:
            raise ValueError("epoch order or early stopping differs")
        if improved(row["selection_log_loss"], best):
            best, best_epoch, stale = row["selection_log_loss"], epoch, 0
        else:
            stale += 1
    if (best_epoch != result["selected_epoch"] or abs(best - loss) > 1e-9
            or len(history) < 30 and stale < 5):
        raise ValueError("selected epoch or stopping rule differs")
    selected = result["selected_checkpoint"]
    name = f"epoch-{best_epoch:02}.pt"
    published = [item for item in result["published_checkpoints"] if item.get("epoch") == best_epoch]
    if (type(selected.get("epoch")) is not int or selected["epoch"] != best_epoch
            or selected.get("name") != name or selected.get("object_name") != f"{slot}-{name}"
            or len(published) != 1 or published[0] != selected):
        raise ValueError("selected checkpoint differs from the verified best epoch publication")
    if inventory.get(selected["object_name"]) != {k: selected[k] for k in ("sha256", "size_bytes", "version_id")}:
        raise ValueError("selected checkpoint is absent from immutable inventory")
    return {**result, "status": "verified"}


def collect(store, slot, success, expected_request_sha, bundle, source, metadata, *, output=None):
    inventory = store.read_publication(slot, success, expected_request_sha)
    required = AUDIT | {"configuration.json", "execution-context.json", "result.json", "baseline-verification.json"}
    if not required <= set(inventory):
        raise ValueError("incomplete research publication")
    artifacts = {}
    for name, item in inventory.items():
        # Model bytes are checked by streaming S3 receipts; never deserialized here.
        raw, _ = store.read(slot, name, item)
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            path = output / name
            with path.open("xb") as stream:
                stream.write(raw)
        if not name.endswith(".pt"):
            artifacts[name] = raw
    request = json.loads(artifacts["configuration.json"])
    validate(request)
    if (request["slot"] != slot or request_sha(request) != expected_request_sha
            or any(request[k] != store.request[k] for k in ("source_commit", "image_digest", "context_public_key"))):
        raise ValueError("prior campaign code/image/key differs")
    context = verify_context(json.loads(artifacts["execution-context.json"]), request)
    audit = verify_package({k: artifacts[k] for k in AUDIT}, bundle, source)
    if not audit["class_support_passed"]:
        raise ValueError("research roles lack required class support")
    previous, count = None, 0
    for name in sorted(n for n in artifacts if n.startswith("event-")):
        event = json.loads(artifacts[name])
        if (name != f"event-{count:04}.json" or event["index"] != count
                or event["previous_sha256"] != previous or event["request_sha256"] != expected_request_sha):
            raise ValueError("event journal is not a complete request-bound chain")
        previous, count = digest(artifacts[name]), count + 1
    if not count or event["kind"] != "completed" or event["payload"] != {"result_sha256": digest(artifacts["result.json"])}:
        raise ValueError("event journal lacks terminal result binding")
    result = json.loads(artifacts["result.json"])
    if result["request_sha256"] != expected_request_sha or result["job_id"] != context["job_id"]:
        raise ValueError("result execution lineage differs")
    if result["kind"] == "trial":
        if not (slot.startswith("search-") or slot.startswith("seed-")):
            raise ValueError("trial result in a non-training slot")
        if slot.startswith("search-"):
            _, width, rate = slot.split("-")
            if result["trial_sha256"] != Trial(int(width), .0003 if rate == "0003" else .001).sha256():
                raise ValueError("grid slot configuration differs")
        elif result["trial"]["seed"] != int(slot.split("-")[1]):
            raise ValueError("confirmation slot seed differs")
        result = verify_trial(result, artifacts, inventory, metadata, slot=slot)
    elif slot == "smoke":
        if (result["checks"]["status"] != "verified" or result["real_data"]["optimizer_steps"] != 32
                or result["real_data"]["rows"] != 1024 or result["real_data"]["epochs"] != 2):
            raise ValueError("GPU smoke checks incomplete")
    elif slot == "inference" and result["kind"] == "inference":
        from .research_comparison_readback import verify
        prior = {name: collect(store, name, item["success"], item["request"]["sha256"], bundle, source, metadata)
                 for name, item in request["prior"].items()}
        verify(result, artifacts, metadata, prior, predictions)
    else:
        raise ValueError("unexpected research result kind")
    return {"request": request, "context": context, "result": result, "audit": audit,
            "artifacts": artifacts, "inventory": inventory, "status": "verified"}
