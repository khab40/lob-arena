"""Invented metadata and in-memory adapters; no model, credential or network calls."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from deployments.mlflow import transformer_lineage as logging
from deployments.mlflow.transformer_lineage_plan import (
    INPUTS, JOB, RESULTS, RUN, Receipt, Snapshot, build_plan, canonical, record, sha,
    milliseconds,
)

ROOT = Path(__file__).resolve().parents[2]


def fixture_sources():
    """Public metadata identities plus invented bodies: never read private custody."""
    settings = record((ROOT / "configs/releases/transformer/selected-settings-20261005.json").read_bytes())
    index = record((ROOT / "docs/evidence/transformer-training-grid-20261003/search-128-0003.json").read_bytes())
    campaign = record((ROOT / "configs/experiments/transformer/c4-campaign-20260928.json").read_bytes())
    lineage = settings["lineage"]
    root = {"release_id": "invented-c4", "protocol_sha256": "a" * 64, "corpus_sha256": "b" * 64,
            "assignment_sha256": "c" * 64, "feature_release_id": lineage["feature_release_id"],
            "feature_release_sha256": lineage["feature_release_sha256"],
            "feature_config_sha256": lineage["feature_config_sha256"]}
    lineage["root_sha256"] = sha(canonical(root))
    data, inventory = {}, []
    for family in ("tabular", "sequence"):
        shards = []
        for fold, count, total in (("train", 60, 33450), ("validation", 30, 9210)):
            for number in range(count):
                run = f"invented-{fold}-{number}"
                body = (family + run).encode()
                relative = f"{family}/{fold}/{run}.parquet"
                artifact = {"uri": relative, "sha256": sha(body), "size_bytes": len(body)}
                shard = {"fold": fold, "run_id": run, "base_session_id": "session-" + fold,
                         "campaign_id": run, "replay_manifest_sha256": "d" * 64}
                if family == "tabular":
                    shard.update(rows=artifact, supervised_row_count=total // count + (number < total % count),
                                 row_identity_sha256="e" * 64)
                else:
                    shard.update(sequences=artifact, sequence_count=total // count + (number < total % count),
                                 sequence_identity_sha256="f" * 64, sequence_length=64)
                shards.append(shard)
                inventory.append({"key": INPUTS.split("/", 3)[3] + "artifacts/" + relative,
                                  "sha256": sha(body), "size_bytes": len(body), "version_id": "1"})
        data[family] = {"access_scope": "development", "folds": ["train", "validation"],
                        "root_release_id": root["release_id"], "root_sha256": lineage["root_sha256"],
                        **{key: root[key] for key in ("protocol_sha256", "corpus_sha256", "assignment_sha256",
                                                     "feature_release_sha256")}, "shards": shards}
    for name in ("SUCCESS", "checksums.sha256", "root", "tabular", "sequence"):
        inventory.append({"key": INPUTS.split("/", 3)[3] + name, "sha256": sha(name.encode()),
                          "size_bytes": len(name), "version_id": "1"})
    config = {"run_id": RUN, "source_commit": lineage["numerical_source_commit"],
              "image_digest": lineage["training_image_digest"], "final_test": False,
              "resources": {"platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb", "timeout_seconds": 7200}}
    lineage["selection_request_sha256"] = sha(canonical(config))
    index["request_sha256"] = lineage["selection_request_sha256"]
    history = [{"epoch": epoch, "weighted_train_loss": .2 / epoch,
                "selection_log_loss": index["selection_log_loss"] if epoch == 4 else .01 + epoch / 1000,
                "selection_f1_at_half": 1.} for epoch in range(1, 10)]
    contract = {"root": root, "ordered_features": settings["preprocessing"]["ordered_features"]}
    normalization = {"training_binding_sha256": lineage["training_binding_sha256"],
                     "fitting_row_sha256": lineage["train_targets_sha256"]}
    bindings = {"source_commit": config["source_commit"], "image_digest": config["image_digest"],
                "contract_sha256": sha(canonical(contract)), "normalization_sha256": sha(canonical(normalization))}
    result = {"status": "completed_pending_independent_verification", "kind": "trial", "job_id": JOB,
              "final_test_access": False, "trial": index["trial"], "selected_epoch": 4,
              "selected_checkpoint": index["selected_checkpoint"], "request_sha256": index["request_sha256"],
              "bindings": bindings, "progress": {"epoch": 9, "history": history},
              "parameter_count": 412417, "selection_log_loss": index["selection_log_loss"],
              "selection_f1_at_half": 1., "duration_seconds": 40.,
              "peak_allocated_gpu_bytes": 100, "peak_reserved_gpu_bytes": 200}
    snapshots, pins = {}, {}

    def add(name, value, *, raw=None, uri=None, version="content-addressed"):
        raw = canonical(value) if raw is None else raw
        ref = Receipt(uri or "evidence:sha256:" + sha(raw), version, len(raw), sha(raw))
        snapshots[name], pins[name] = Snapshot(ref, raw), ref
        return ref.as_dict()

    base = RESULTS + "transformer-research-c4-20261003-r2/search-128-0003/"
    add("configuration", config, uri=base + "configuration.json", version="1")
    add("result", result, uri=base + "result.json", version="1")
    events, previous, receipts = {}, None, {}
    for count in range(12):
        name = f"event-{count:04}.json"
        event = {"index": count, "request_sha256": index["request_sha256"], "previous_sha256": previous,
                 "kind": "completed" if count == 11 else "checkpoint",
                 "payload": {"result_sha256": sha(canonical(result))} if count == 11 else {}}
        body = canonical(event)
        ref = Receipt(base + name, "1", len(body), sha(body))
        events[name], previous = Snapshot(ref, body), ref.sha256
        receipts[name] = {key: getattr(ref, key) for key in ("sha256", "size_bytes", "version_id")}
    receipts.update({name + ".json": {key: getattr(pins[name], key) for key in ("sha256", "size_bytes", "version_id")}
                     for name in ("configuration", "result")})
    selection = {"status": "verified", "result": {**result, "status": "verified"}, "inventory": receipts}
    settings["artifacts"]["selection_verification"] = add("selection_verification", selection)
    index["verification_sha256"] = pins["selection_verification"].sha256
    settings["artifacts"]["verification"] = add("verification", {"status": "verified", "result": {
        "checkpoint_origin": {"bindings": bindings}, "calibration": {"temperature": settings["temperature"]},
        "comparison": {"transformer_selected_operating_points": settings["operating_points"]}}})
    settings["artifacts"]["comparison_summary"] = add("comparison_summary", {"verification": {
        "status": "verified", "receipt_sha256": pins["verification"].sha256}})
    settings["artifacts"]["decision"] = add("decision", {"decision": settings["decision"],
        "results_evidence_sha256": pins["comparison_summary"].sha256})
    for name, value in (("root", root), ("tabular", data["tabular"]), ("sequence", data["sequence"])):
        add(name, value)
        campaign["inputs"][{"root": "root_file_sha256", "tabular": "tabular_sha256",
                            "sequence": "sequence_sha256"}[name]] = pins[name].sha256
    inventory_raw = b"\n".join(canonical(item) for item in inventory) + b"\n"
    add("development_inventory", None, raw=inventory_raw)
    campaign["inputs"]["inventory_sha256"] = pins["development_inventory"].sha256
    for name, value in (("contract", contract), ("normalization", normalization)):
        settings["artifacts"][name] = add(name, value)
    add("campaign", campaign)
    add("selected_index", index)
    add("settings", settings)
    return snapshots, pins, events


@pytest.fixture
def plan():
    return build_plan(*fixture_sources(), reconciled_at="2026-10-09T15:00:00Z")


class Bank:
    def __init__(self):
        self.runs, self.histories, self.files = {}, {}, {}
        self.writes, self.creates, self.fail = 0, 0, None

    def changed(self, kind):
        self.writes += 1
        if self.fail == kind:
            self.fail = None
            raise TimeoutError("inert uncertain response")


class Client:
    transport_controls = logging.CONTROLS

    def __init__(self, bank, identity):
        self.bank, self.identity = bank, identity
        self.allowed, self.active = True, True

    def authenticated_identity(self):
        return self.identity

    def require_permission(self, experiment_id, permission):
        if not self.allowed:
            raise PermissionError("inert missing permission")

    def get_experiment_by_name(self, name):
        return NS(experiment_id="7", lifecycle_stage="active") if self.active else None

    def search_runs(self, ids, filter_string, **kwargs):
        target = filter_string.split("'")[1]
        key = "mlflow.runName" if "mlflow.runName" in filter_string else logging.RESERVATION
        return [deepcopy(run) for run in self.bank.runs.values()
                if run.data.tags.get(key) == target]

    def create_run(self, experiment_id, *, start_time, tags, run_name):
        self.bank.creates += 1
        run_id = f"{self.bank.creates:032x}"
        run = NS(info=NS(run_id=run_id, experiment_id=experiment_id, lifecycle_stage="active",
                        status="RUNNING", start_time=start_time, end_time=None),
                 data=NS(tags={**deepcopy(tags), "mlflow.runName": run_name}, params={}, metrics={}),
                 inputs=NS(dataset_inputs=[]))
        self.bank.runs[run_id] = run
        self.bank.changed("create")
        return deepcopy(run)

    def get_run(self, run_id):
        return deepcopy(self.bank.runs[run_id])

    def get_metric_history(self, run_id, key):
        return deepcopy(self.bank.histories[run_id, key])

    def log_param(self, run_id, key, value, *, synchronous):
        assert synchronous
        self.bank.runs[run_id].data.params[key] = value
        self.bank.changed("param")

    def set_tag(self, run_id, key, value, *, synchronous):
        assert synchronous
        self.bank.runs[run_id].data.tags[key] = value
        self.bank.changed("tag")

