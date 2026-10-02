"""Research lineage registration only; injected transports must disable POST retries.

The operator must hold an exclusive registry-write window: MLflow aliases lack CAS.
No model is loaded, packaged, trained, evaluated, or promoted by this helper.
"""
import hashlib
import json
import os
from pathlib import Path

from scripts.lightgbm_retention_contract import (
    decode, load_inventory, load_source_equivalence, require, tracking_mismatches,
)

MODEL = "lob-arena-lightgbm-attack-active"
ALIAS = "research-baseline"
MANIFEST_SHA256 = "de35f415ee803a91373995a9f23d8eff2bf7aa312bc3321839c08cb9f7275882"
ARTIFACTS = {"governed/" + name for name in (
    "training-run.json", "calibration-manifest.json", "validation-metrics.json",
    "feature-importance.json", "reliability-bins.json", "reliability-diagram.svg", "model.txt",
)}
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
INPUT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _run_dictionary(run):
    value = run.to_dictionary()
    for category in ("tags", "params", "metrics"):
        value["data"][category] = [{"key": k, "value": v}
                                   for k, v in value["data"][category].items()]
    for item in value["inputs"]["dataset_inputs"]:
        item["tags"] = [{"key": k, "value": v} for k, v in item["tags"].items()]
    return value


def verify_frozen(client, download, manifest_raw, inventory_raw, proof_raw,
                  manifest_sha256=MANIFEST_SHA256):
    """Recheck all metadata and seven artifacts; download(run_id, path, limit) -> bytes."""
    require(_digest(manifest_raw) == manifest_sha256, "lineage manifest anchor mismatch")
    manifest = decode(manifest_raw)
    require(manifest["schema_version"] == "lightgbm_lineage_verification_v1"
            and manifest["status"] == "verified", "lineage manifest not verified")
    inv = load_inventory(inventory_raw, manifest["inventory_sha256"], RESULTS_BUCKET, INPUT_BUCKET)
    for key in ("candidate_sha256", "freeze_sha256"):
        require(inv[key] == manifest[key], "frozen binding mismatch")
    require(inv["lineage"]["mlflow_run_id"] == manifest["mlflow_run_id"], "frozen run mismatch")
    proof = load_source_equivalence(proof_raw, manifest["dataset_source_proof_sha256"], inv,
                                    manifest["inventory_sha256"], INPUT_BUCKET)
    run = client.get_run(manifest["mlflow_run_id"])
    require(client.get_experiment(run.info.experiment_id).name == "lob-arena/lightgbm-development",
            "frozen experiment mismatch")
    require(not tracking_mismatches(inv, _run_dictionary(run), proof), "frozen run lineage mismatch")
    entries = manifest["artifacts"]
    require(len(entries) == 7 and {e["path"] for e in entries} == ARTIFACTS,
            "seven exact artifacts required")
    total = sum(e["size_bytes"] for e in entries)
    require(manifest["mlflow_artifacts_verified"] == 7 and 0 < total <= 90458
            and total == manifest["mlflow_artifact_bytes"], "artifact byte bound mismatch")
    require(len(inv["lineage"]["feature_inputs"]) == manifest["dataset_inputs_verified"],
            "dataset count mismatch")
    for entry in entries:
        require(type(entry["size_bytes"]) is int and entry["size_bytes"] > 0, "artifact size invalid")
        raw = download(manifest["mlflow_run_id"], entry["path"], entry["size_bytes"])
        require(isinstance(raw, bytes) and len(raw) == entry["size_bytes"]
                and _digest(raw) == entry["sha256"], "frozen artifact mismatch")
    tags = {key: manifest[key] for key in ("candidate_sha256", "freeze_sha256", "inventory_sha256")}
    tags.update({key: inv["lineage"][key] for key in ("feature_release_id", "feature_release_sha256")})
    tags.update(lineage_manifest_sha256=manifest_sha256, governance_state="research_baseline_qualified",
                artifact_kind="lightgbm_text_research_lineage", deployable_mlflow_flavor="false")
    return {"name": MODEL, "run_id": manifest["mlflow_run_id"], "tags": tags,
            "source": f"runs:/{manifest['mlflow_run_id']}/governed/model.txt"}


def _record(directory, name, value):
    """Exclusive durable intent/receipt; never replace a prior attempt."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / name).open("x", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _matches(version, binding):
    require(all(getattr(version, k) == binding[k] for k in ("name", "run_id", "source"))
            and version.tags == binding["tags"] and version.status == "READY"
            and version.current_stage == "None", "conflicting model version")


def reconcile(client, binding):
    """Read-only reconciliation; any extra version/alias blocks automatic writes."""
    model = client.get_registered_model(MODEL)  # Must exist; never create a namespace here.
    require(model.name == MODEL and set(model.aliases) <= {ALIAS}, "conflicting registry aliases")
    versions = client.search_model_versions(f"name = '{MODEL}'", max_results=2)
    require(len(versions) <= 1 and not getattr(versions, "token", None), "conflicting model versions")
    version = None
    if versions:
        version = client.get_model_version(MODEL, versions[0].version)
        _matches(version, binding)
    alias = model.aliases.get(ALIAS)
    require(alias is None or (version is not None and str(alias) == str(version.version)),
            "conflicting research alias")
    return version, alias


def register_baseline(client, download, manifest_raw, inventory_raw, proof_raw, journal,
                      *, manifest_sha256=MANIFEST_SHA256):
    """For an explicitly approved operation; ambiguous writes require operator reconciliation."""
    binding = verify_frozen(client, download, manifest_raw, inventory_raw, proof_raw, manifest_sha256)
    version, alias = reconcile(client, binding)
    journal = Path(journal)
    intent = journal / "create-intent.json"
    if intent.exists():
        require(decode(intent.read_bytes()) == binding, "existing intent binding mismatch")
    if version is None:
        require(not intent.exists(), "unresolved create intent; no retry")
        _record(journal, intent.name, binding)
        client.create_model_version(**binding, await_creation_for=0)
        version, alias = reconcile(client, binding)
        require(version is not None, "created version not visible; reconcile without retry")
    alias_binding = {"name": MODEL, "alias": ALIAS, "version": str(version.version)}
    alias_intent = journal / "alias-intent.json"
    if alias_intent.exists():
        require(decode(alias_intent.read_bytes()) == alias_binding, "existing alias intent mismatch")
    if alias is None:
        require(not alias_intent.exists(), "unresolved alias intent; no retry")
        _record(journal, alias_intent.name, alias_binding)
        version, alias = reconcile(client, binding)  # Recheck immediately before mutation.
        require(version is not None and str(version.version) == alias_binding["version"]
                and alias is None, "registry changed before alias write")
        client.set_registered_model_alias(**alias_binding)
    observed, alias = reconcile(client, binding)
    require(observed is not None and str(alias) == str(observed.version), "alias readback mismatch")
    receipt = {**alias_binding, "binding": binding, "verified": True, "model_execution": False}
    complete = journal / "registry-receipt.json"
    if complete.exists():
        require(decode(complete.read_bytes()) == receipt, "receipt binding mismatch")
    else:
        _record(journal, complete.name, receipt)
    return receipt
