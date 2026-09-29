"""Exact validation metadata scope, authenticated through frozen C3 inventories."""
from __future__ import annotations

from app.market_data.preparation import NasdaqPreparationRequest
from app.market_data.preparation_checkpoints import PreparationCheckpointBinding, inventory_model_evidence
from app.nebius.object_storage import ChecksumInventory
from .role_provenance import COMPARISONS, DATE, PREPARATION_KEY, PREPARATION_RUN, checkpoint_keys
from .verification_spec import INPUT_BUCKET, digest

REQUEST_KEY = PREPARATION_KEY.removesuffix("preparation.json") + "request.json"
MAX_OBJECT = 256 * 1024
PHASE_SECONDS = 300


def run_members():
    """Paths match the frozen preparation/exporter, without remote discovery."""
    result = []
    for key, (number, (symbol, family, seed)) in zip(checkpoint_keys()[1:], COMPARISONS, strict=True):
        prefix = key.removesuffix("checkpoint.json")
        base = f"xnas-{DATE}-{symbol.lower()}"
        replay = f"replays/{base}/comparisons/{family}-s{seed}/"
        modes = ("control", "hybrid") if family == "spoofing_like_wall" and seed == 41 else ("hybrid",)
        for mode in modes:
            run = base + ("-control" if mode == "control" else f"-{family}-s{seed}")
            result.append({"number": number, "symbol": symbol, "family": family, "seed": seed,
                "mode": mode, "run_id": run, "base_session_id": base, "prefix": prefix,
                "feature_key": prefix + f"features/{run}/run-metadata.json",
                "replay_key": prefix + replay + mode + "/manifest.json",
                "label_key": prefix + replay + "hybrid/ground-truth.jsonl" if mode == "hybrid" else None})
    return result


def phase_keys(phase):
    members = run_members()
    if phase == 1:
        return [REQUEST_KEY, *(k.removesuffix("checkpoint.json") + "SUCCESS" for k in checkpoint_keys()[1:]),
                *(m["feature_key"] for m in members)]
    if phase == 2:
        return [*(m["replay_key"] for m in members), *(m["label_key"] for m in members if m["label_key"])]
    raise ValueError("lineage audit requires phase 1 or 2")


def verify_request(raw, source, prepared):
    request = NasdaqPreparationRequest.model_validate_json(raw)
    binding = PreparationCheckpointBinding(request_sha256=request.canonical_hash(),
        source_manifest_sha256=request.source_release_manifest_sha256,
        source_sha256=source.source_sha256, image=request.image, git_commit=request.git_commit,
        feature_config_sha256=request.feature_config_sha256)
    if (binding.canonical_hash() != prepared.checkpoint_binding_sha256
            or request.run_id != PREPARATION_RUN or request.sequence_number != 3
            or str(request.source.date) != DATE or request.source.fold != "validation"
            or request.source.filename != source.filename
            or request.source_release_manifest_sha256 != source.source_manifest_sha256
            or request.result_uri != f"s3://{INPUT_BUCKET}/{REQUEST_KEY.rsplit('/', 1)[0]}"):
        raise ValueError("C3 request differs from frozen preparation binding")
    return request


def verify_inventory(raw, reference, checkpoint_raw):
    inventory = ChecksumInventory.model_validate_json(raw)
    observed = inventory_model_evidence(inventory, exclude_checkpoint=True)
    if (len(inventory.files) > 100 or observed != (reference.payload_inventory_sha256,
            reference.payload_file_count, reference.payload_size_bytes)):
        raise ValueError("checkpoint inventory differs from frozen payload binding")
    checkpoint = [entry for entry in inventory.files if entry.path == "checkpoint.json"]
    if (len(checkpoint) != 1 or checkpoint[0].sha256 != digest(checkpoint_raw)
            or checkpoint[0].sha256 != reference.checkpoint_sha256
            or checkpoint[0].size_bytes != len(checkpoint_raw)):
        raise ValueError("inventory checkpoint differs from frozen metadata")
    return {entry.path: entry for entry in inventory.files}


def member_entry(key, inventories):
    if key not in phase_keys(1)[28:] + phase_keys(2):
        raise ValueError("member escaped the exact metadata allowlist")
    matches = [prefix for prefix in inventories if key.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("metadata member lacks one authenticated checkpoint inventory")
    prefix = matches[0]
    relative = key.removeprefix(prefix)
    entry = inventories[prefix].get(relative)
    if entry is None or not 0 < entry.size_bytes <= MAX_OBJECT:
        raise ValueError("metadata member missing or outside its byte bound")
    return entry


def verify_member(key, raw, inventories):
    entry = member_entry(key, inventories)
    if len(raw) != entry.size_bytes or digest(raw) != entry.sha256:
        raise ValueError("metadata member differs from authenticated inventory")
