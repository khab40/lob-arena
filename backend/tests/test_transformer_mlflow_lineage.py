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

    def log_metric(self, run_id, key, value, *, timestamp, step, synchronous):
        assert synchronous
        self.bank.histories.setdefault((run_id, key), []).append(
            {"key": key, "value": value, "timestamp": timestamp, "step": step})
        latest = max(self.bank.histories[run_id, key], key=lambda row: (row["step"], row["timestamp"]))
        self.bank.runs[run_id].data.metrics[key] = latest["value"]
        self.bank.changed("metric")

    def log_inputs(self, run_id, *, datasets):
        self.bank.runs[run_id].inputs.dataset_inputs.extend(deepcopy(datasets))
        self.bank.changed("dataset")

    def set_terminated(self, run_id, *, status, end_time):
        self.bank.runs[run_id].info.status = status
        self.bank.runs[run_id].info.end_time = end_time
        self.bank.changed("finish")


class Artifacts(Client):
    def list(self, run_id):
        return [path for owner, path in self.bank.files if owner == run_id]

    def read(self, run_id, path, limit):
        return self.bank.files[run_id, path]

    def write(self, run_id, path, raw):
        self.bank.files[run_id, path] = raw
        self.bank.changed("artifact")


@pytest.fixture
def session(tmp_path):
    tmp_path.chmod(0o700)
    bank = Bank()
    return bank, {"journal": tmp_path, "writer": Client(bank, "governed-writer"),
                  "reader": Client(bank, "prometheus"), "writer_artifacts": Artifacts(bank, "governed-writer"),
                  "reader_artifacts": Artifacts(bank, "prometheus")}


def run(plan, args):
    return logging.reconcile(plan, approved_plan_sha256=plan.sha256(), expires=time.monotonic() + 60, **args)


def test_sealed_plan_preserves_original_epoch_time_params_and_metadata_only_uploads(plan):
    value, files = plan.checked(plan.sha256())
    assert len(value["datasets"]) == 180 and len(value["artifacts"]) == 28
    assert len(value["metrics"]) == 34
    assert {item["timestamp"] for item in value["metrics"]} == {value["end_time"]}
    assert [item["step"] for item in value["metrics"] if item["key"] == "epoch.selection_log_loss"] == list(range(1, 10))
    assert value["params"]["training.seed"] == "42"
    assert value["params"]["architecture.precision"] == "float32"
    assert value["params"]["campaign.training.optimizer"] == "AdamW"
    assert all(not path.endswith((".pt", ".parquet", "MLmodel")) for path in files)


def test_metadata_module_import_is_torch_and_mlflow_free():
    code = "import sys; import deployments.mlflow.transformer_lineage; assert 'torch' not in sys.modules; "
    code += "assert 'mlflow' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, timeout=20)


@pytest.mark.parametrize("failure", ["hash", "version", "events", "pin", "oversize", "time"])
def test_builder_rejects_changed_original_inputs_before_plan(failure):
    snapshots, pins, events = fixture_sources()
    when = "2026-10-09T15:00:00Z"
    if failure == "hash":
        snapshots["result"] = replace(snapshots["result"], data=b"{}")
    elif failure == "version":
        snapshots["result"] = replace(snapshots["result"], receipt=pins["root"])
    elif failure == "events":
        events["event-0003.json"] = events["event-0002.json"]
    elif failure == "pin":
        pins["settings"] = pins["root"]
    elif failure == "oversize":
        snapshots["settings"] = replace(snapshots["settings"], data=b"x" * (2 * 1024**2 + 1))
    else:
        when = "2025-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        build_plan(snapshots, pins, events, reconciled_at=when)


def test_complete_independent_readback_and_replay_have_zero_remote_writes(plan, session):
    bank, args = session
    receipt = run(plan, args)
    assert receipt["counts"]["datasets"] == 180 and bank.creates == 1
    before = bank.writes
    assert run(plan, args) == receipt and bank.writes == before
    assert (args["journal"] / "complete.json").is_file()
    assert record((args["journal"] / "writer-readback.json").read_bytes()) == record(
        (args["journal"] / "reader-readback.json").read_bytes())
    for path, raw in plan.uploads:
        assert (args["journal"] / "reader-artifacts" / path).read_bytes() == raw


@pytest.mark.parametrize("failure", ["create", "param", "metric", "dataset", "artifact", "finish"])
def test_uncertain_committed_writes_reconcile_without_duplicate_record_or_history(plan, session, failure):
    bank, args = session
    bank.fail = failure
    with pytest.raises(TimeoutError):
        run(plan, args)
    receipt = run(plan, args)
    assert bank.creates == 1 and receipt["counts"]["metrics"] == 34
    assert all(len(rows) == len({logging.metric_identity(row) for row in rows}) for rows in bank.histories.values())
    before = bank.writes
    assert run(plan, args) == receipt and bank.writes == before


def test_unresolved_create_intent_never_creates_a_replacement(plan, session):
    bank, args = session
    bank.fail = "create"
    with pytest.raises(TimeoutError):
        run(plan, args)
    bank.runs.clear()
    with pytest.raises(ValueError, match="never recreate"):
        run(plan, args)
    assert bank.creates == 1


@pytest.mark.parametrize("failure", ["params", "metrics", "duplicate_metric", "datasets", "duplicate_dataset",
                                    "artifact", "status", "start", "end", "duplicate_run"])
def test_existing_conflicting_or_duplicate_state_stops_without_remote_writes(plan, session, failure):
    bank, args = session
    run(plan, args)
    run_id = next(iter(bank.runs))
    item = bank.runs[run_id]
    if failure == "params":
        item.data.params["training.seed"] = "7"
    elif failure in {"metrics", "duplicate_metric"}:
        key = next(iter(item.data.metrics))
        if failure == "metrics":
            bank.histories[run_id, key][0]["value"] = 123.
        else:
            bank.histories[run_id, key].append(deepcopy(bank.histories[run_id, key][0]))
    elif failure == "datasets":
        item.inputs.dataset_inputs[0]["tags"]["version_id"] = "2"
    elif failure == "duplicate_dataset":
        item.inputs.dataset_inputs.append(deepcopy(item.inputs.dataset_inputs[0]))
    elif failure == "artifact":
        bank.files[next(iter(bank.files))] = b"changed metadata"
    elif failure == "status":
        item.info.status = "FAILED"
    elif failure == "start":
        item.info.start_time += 1
    elif failure == "end":
        item.info.end_time += 1
    else:
        bank.runs["f" * 32] = deepcopy(item)
    before = bank.writes
    with pytest.raises(ValueError):
        run(plan, args)
    assert bank.writes == before


@pytest.mark.parametrize("failure", ["permission", "experiment", "identity", "controls", "shared_reader", "pin"])
def test_admission_gates_have_zero_remote_writes(plan, session, failure):
    bank, args = session
    if failure == "permission":
        args["writer"].allowed = False
    elif failure == "experiment":
        args["reader"].active = False
    elif failure == "identity":
        args["reader"].identity = "governed-writer"
    elif failure == "controls":
        args["writer"].transport_controls = {**logging.CONTROLS, "http_retries": 1}
    elif failure == "shared_reader":
        args["reader"] = args["writer"]
    else:
        plan = replace(plan, data=plan.data + b" ")
        with pytest.raises(ValueError, match="external logging plan pin"):
            logging.reconcile(plan, approved_plan_sha256=sha(plan.data[:-1]), expires=time.monotonic() + 60, **args)
        assert bank.writes == 0
        return
    with pytest.raises((ValueError, PermissionError)):
        run(plan, args)
    assert bank.writes == 0


def test_reader_byte_mismatch_cannot_finish_or_establish_completion(plan, session):
    bank, args = session
    args["reader_artifacts"].read = lambda *_: b"wrong independent bytes"
    with pytest.raises(ValueError, match="readback differs"):
        run(plan, args)
    assert next(iter(bank.runs.values())).info.status == "RUNNING"
    assert not (args["journal"] / "complete.json").exists()


def test_sealed_upload_drift_and_journal_rebinding_fail_before_remote_mutations(plan, session):
    bank, args = session
    changed = replace(plan, uploads=((plan.uploads[0][0], b"changed"), *plan.uploads[1:]))
    with pytest.raises(ValueError, match="upload differs"):
        run(changed, args)
    assert bank.writes == 0
    run(plan, args)
    before = bank.writes
    value, files = plan.checked(plan.sha256())
    value["tags"]["transformer.reconciliation_at"] = "2026-10-09T16:00:00Z"
    changed = replace(plan, data=canonical(value))
    with pytest.raises(ValueError, match="journal conflict"):
        run(changed, args)
    assert bank.writes == before


def test_symlink_journal_and_duplicate_dataset_tags_are_rejected(plan, session, tmp_path):
    bank, args = session
    target = tmp_path / "link"
    target.symlink_to(args["journal"], target_is_directory=True)
    args["journal"] = target
    with pytest.raises(ValueError, match="canonical journal"):
        run(plan, args)
    assert bank.writes == 0
    entity = NS(dataset=NS(to_dictionary=lambda: {}), tags=[NS(key="same", value="1"), NS(key="same", value="2")])
    with pytest.raises(ValueError, match="duplicate dataset input tag"):
        logging.dataset_identity(entity)


def test_existing_named_original_without_our_journal_cannot_create_a_duplicate(plan, session):
    bank, args = session
    value, _ = plan.checked(plan.sha256())
    old = args["writer"].create_run("7", start_time=value["start_time"], tags=value["tags"], run_name=RUN)
    bank.runs[old.info.run_id].data.tags.pop(logging.RESERVATION)
    before = bank.writes
    with pytest.raises(ValueError, match="source-bound adoption"):
        run(plan, args)
    assert bank.writes == before and bank.creates == 1


@pytest.mark.parametrize("failure", ["experiment", "name"])
def test_get_run_identity_drift_stops_before_remote_writes(plan, session, failure):
    bank, args = session
    run(plan, args)
    original = args["writer"].get_run

    def changed(run_id):
        item = original(run_id)
        if failure == "experiment":
            item.info.experiment_id = "different-experiment"
        else:
            item.data.tags.pop("mlflow.runName")
        return item

    args["writer"].get_run = changed
    before = bank.writes
    with pytest.raises(ValueError):
        run(plan, args)
    assert bank.writes == before


def test_unresolved_uncommitted_write_never_retries_or_completes(plan, session):
    bank, args = session
    bank.fail = "param"
    with pytest.raises(TimeoutError):
        run(plan, args)
    next(iter(bank.runs.values())).data.params.clear()
    before = bank.writes
    with pytest.raises(ValueError, match="unresolved write intent"):
        run(plan, args)
    assert bank.writes == before and not (args["journal"] / "complete.json").exists()


def test_call_returning_after_deadline_has_no_protocol_success(monkeypatch):
    clock = [100.]
    monkeypatch.setattr(logging.time, "monotonic", lambda: clock[0])
    budget = logging.Budget(101.)

    def late():
        clock[0] = 102.
        return "late result"

    with pytest.raises(TimeoutError):
        budget.call(late)


def test_final_persistence_after_deadline_cannot_return_success(plan, session, monkeypatch):
    bank, args = session
    clock = [100.]
    monkeypatch.setattr(logging.time, "monotonic", lambda: clock[0])
    original = logging.persist

    def late(path, value):
        original(path, value)
        if path.name == "complete.json":
            clock[0] = 200.

    monkeypatch.setattr(logging, "persist", late)
    with pytest.raises(TimeoutError):
        run(plan, args)


@pytest.mark.parametrize("value", ["2026-10-03T17:42:11.824179027Z", "2026-10-03T17:42:11.824+00:00"])
def test_original_nanosecond_timestamp_has_exact_milliseconds(value):
    assert milliseconds(value) == 1791049331824


@pytest.mark.parametrize("value", ["2026-10-03T17:42:11+03:00", "2026-10-03", None])
def test_timestamp_requires_explicit_utc(value):
    with pytest.raises(ValueError, match="UTC timestamp"):
        milliseconds(value)


def test_existing_artifact_custody_symlink_fails_before_creating_external_directory(plan, session, tmp_path):
    bank, args = session
    external = tmp_path / "unrelated"
    external.mkdir()
    (args["journal"] / "writer-artifacts").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="custody path"):
        run(plan, args)
    assert bank.writes == 0 and not (external / "lineage").exists()
