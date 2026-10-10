"""Sealed original-run metadata only; no MLflow, Torch, credentials or IO imports."""
from dataclasses import dataclass
from datetime import datetime
import calendar
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

EXPERIMENT = "lob-arena/transformer-development"
RUN = "transformer-research-c4-20261003-r2-search-128-0003"
JOB = "aijob-e00s0s76j0pgrq9bjp"
RESERVATION = "transformer.original_reservation_sha256"
RESULTS = "s3://aimada-wave1-results-e00g6zvxpr00/campaigns/wave1-research-20260816/development/"
INPUTS = "s3://aimada-wave1-dev-e00g6zvxpr00/releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging/"
MAX_OBJECT = 2 * 1024**2
MAX_TOTAL = 8 * 1024**2
SOURCES = {"settings", "verification", "selection_verification", "decision", "comparison_summary",
           "selected_index", "campaign", "configuration", "result", "root", "tabular", "sequence",
           "development_inventory", "contract", "normalization"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate metadata key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("nonfinite metadata")

    value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
    canonical(value)  # Also reject overflow-to-infinity numeric values.
    return value


def require(ok, message):
    if not ok:
        raise ValueError(message)


def milliseconds(value):
    require(isinstance(value, str), "UTC timestamp required")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|\+00:00)", value)
    require(match is not None, "UTC timestamp required")
    dt = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(dt.timetuple()) * 1000 + int(((match[2] or "") + "000")[:3])


@dataclass(frozen=True)
class Receipt:
    uri: str
    version_id: str
    size_bytes: int
    sha256: str

    def __post_init__(self):
        require(type(self.size_bytes) is int and 0 < self.size_bytes <= MAX_OBJECT, "metadata size bound")
        require(isinstance(self.sha256, str) and re.fullmatch(r"[a-f0-9]{64}", self.sha256), "metadata SHA")
        if self.uri == "evidence:sha256:" + self.sha256:
            require(self.version_id == "content-addressed", "content-addressed version required")
        else:
            parts = urlsplit(self.uri)
            require(self.uri.startswith((RESULTS, INPUTS)) and self.version_id == "1"
                    and not parts.query and not parts.fragment and not parts.username
                    and not any(p in ("", ".", "..") for p in parts.path[1:].split("/"))
                    and not re.search(r"[\s%\\]", self.uri), "exact original development reference required")

    def as_dict(self):
        return {"uri": self.uri, "version_id": self.version_id,
                "size_bytes": self.size_bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class Snapshot:
    receipt: Receipt
    data: bytes

    def checked(self, expected):
        require(type(self.receipt) is Receipt and self.receipt == expected and type(self.data) is bytes
                and len(self.data) == expected.size_bytes and sha(self.data) == expected.sha256,
                "original metadata version, size or SHA differs")
        return self.data


@dataclass(frozen=True)
class SealedPlan:
    data: bytes
    uploads: tuple  # Immutable (relative path, exact metadata bytes) pairs.

    def sha256(self):
        return sha(self.data)

    def checked(self, expected_sha256):
        require(type(self.data) is bytes and 0 < len(self.data) <= MAX_OBJECT
                and self.sha256() == expected_sha256, "external logging plan pin differs")
        value = record(self.data)
        require(canonical(value) == self.data and value["schema_version"] == "original_transformer_mlflow_v1"
                and value["run_name"] == RUN and value["experiment"] == EXPERIMENT, "logging plan scope differs")
        files = dict(self.uploads)
        require(len(files) == len(self.uploads) == len(value["artifacts"])
                and set(files) == set(value["artifacts"]), "logging artifact inventory differs")
        for name, raw in files.items():
            require(type(raw) is bytes and 0 < len(raw) <= MAX_OBJECT
                    and re.fullmatch(r"lineage/[a-z_0-9-]+\.(json|jsonl)", name)
                    and value["artifacts"][name] == {"size_bytes": len(raw), "sha256": sha(raw)},
                    "sealed metadata upload differs")
        require(sum(len(raw) for raw in files.values()) <= MAX_TOTAL, "metadata aggregate bound")
        return value, files


def _flatten(value, prefix, output):
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]+", key), "parameter key differs")
            _flatten(item, prefix + "." + key if prefix else key, output)
    else:
        text = value if isinstance(value, str) else canonical(value).decode()
        require(prefix not in output and len(prefix) <= 250 and len(text) <= 6000, "parameter payload bound")
        output[prefix] = text


def _datasets(metadata, inventory, settings):
    root, tabular, sequence = (metadata[name] for name in ("root", "tabular", "sequence"))
    lineage = settings["lineage"]
    root_sha = sha(canonical(root))
    require(root_sha == lineage["root_sha256"]
            and all(root[key] == lineage[key] for key in ("feature_release_id", "feature_release_sha256",
                                                        "feature_config_sha256")), "root feature identity differs")
    require(len(inventory) == 185, "exact original input inventory count required")
    refs = {}
    for item in inventory:
        require(set(item) == {"key", "sha256", "size_bytes", "version_id"}
                and item["key"] not in refs and item["version_id"] == "1"
                and type(item["size_bytes"]) is int and 0 < item["size_bytes"] <= MAX_OBJECT
                and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]), "input inventory differs")
        refs[item["key"]] = item
    result, domains = [], {}
    for name, artifact_key, count_key, identity_key in (
            ("tabular", "rows", "supervised_row_count", "row_identity_sha256"),
            ("sequence", "sequences", "sequence_count", "sequence_identity_sha256")):
        projection = tabular if name == "tabular" else sequence
        require(projection["access_scope"] == "development" and projection["folds"] == ["train", "validation"]
                and projection["root_sha256"] == root_sha
                and projection["root_release_id"] == root["release_id"] and len(projection["shards"]) == 90,
                "development projection binding differs")
        for key in ("protocol_sha256", "corpus_sha256", "assignment_sha256", "feature_release_sha256"):
            require(projection[key] == root[key], "projection provenance differs")
        seen, counts = set(), {"train": 0, "validation": 0}
        for shard in projection["shards"]:
            fold, run_id, artifact = shard["fold"], shard["run_id"], shard[artifact_key]
            require(fold in counts and run_id not in seen and type(shard[count_key]) is int
                    and shard[count_key] > 0, "duplicate or invalid development shard")
            seen.add(run_id)
            counts[fold] += shard[count_key]
            uri = INPUTS + "artifacts/" + artifact["uri"]
            key = urlsplit(uri).path[1:]
            reference = refs.get(key)
            require(reference is not None and all(reference[k] == artifact[k] for k in ("sha256", "size_bytes"))
                    and not re.search(r"[\s%\\]", artifact["uri"])
                    and not any(p in ("", ".", "..") for p in artifact["uri"].split("/")),
                    "dataset absent from exact original inventory")
            domain = (fold, shard["base_session_id"], shard["campaign_id"], shard["replay_manifest_sha256"])
            if name == "tabular":
                domains[run_id] = domain
            else:
                require(domains.get(run_id) == domain and shard["sequence_length"] == 64,
                        "sequence/tabular replay identity differs")
            result.append({"dataset": {"name": name + "-" + run_id, "digest": "sha256:" + artifact["sha256"][:29],
                "source_type": "s3", "source": {"uri": uri}, "schema": None, "profile": None},
                "tags": {"mlflow.data.context": "training" if fold == "train" else "validation",
                    "fold": fold, "artifact_sha256": artifact["sha256"], "version_id": reference["version_id"],
                    "size_bytes": str(artifact["size_bytes"]), "row_count": str(shard[count_key]),
                    "ordered_identity_sha256": shard[identity_key], "base_session_id": shard["base_session_id"],
                    "replay_manifest_sha256": shard["replay_manifest_sha256"],
                    **{key: root[key] for key in ("protocol_sha256", "corpus_sha256", "assignment_sha256",
                                                 "feature_config_sha256")},
                    "feature_release_id": lineage["feature_release_id"],
                    "feature_release_sha256": lineage["feature_release_sha256"],
                    "raw_rows_uploaded_to_mlflow": "false"}})
        require(counts == {"train": 33450, "validation": 9210}
                and (name == "tabular" or seen == set(domains)), "original development row/domain count differs")
    require(len({canonical(item) for item in result}) == len(result) <= 180, "duplicate dataset lineage")
    return sorted(result, key=canonical)


def build_plan(snapshots, pins, events, *, reconciled_at):
    """Caller supplies external receipts; never read missing artifacts or regenerate originals.

    `pins` maps every SOURCES name to an independently approved Receipt. `events`
    maps the twelve exact event names to Snapshot values authenticated by the
    externally pinned original selection inventory. Model checkpoint bytes are
    deliberately absent from this interface.
    """
    require(set(snapshots) == set(pins) == SOURCES
            and set(events) == {f"event-{i:04}.json" for i in range(12)}
            and all(type(snapshots[name]) is Snapshot and type(pins[name]) is Receipt for name in SOURCES)
            and all(type(item) is Snapshot for item in events.values()), "exact original metadata inputs required")
    raw = {name: snapshots[name].checked(pins[name]) for name in SOURCES}
    require(sum(map(len, raw.values())) + sum(len(item.data) for item in events.values()) <= MAX_TOTAL,
            "metadata aggregate bound")
    metadata = {name: record(data) for name, data in raw.items() if name != "development_inventory"}
    inventory = [record(line) for line in raw["development_inventory"].splitlines()]
    settings, selection, index = (metadata[name] for name in ("settings", "selection_verification", "selected_index"))
    result, config, lineage = metadata["result"], metadata["configuration"], settings["lineage"]
    require(settings["schema_version"] == "transformer_selected_settings_v1" and settings["scope"] == "research_only"
            and lineage["selection_run_id"] == config["run_id"] == RUN
            and lineage["selection_job_id"] == result["job_id"] == index["job_id"] == JOB
            and lineage["selected_epoch"] == index["selected_epoch"] == result["selected_epoch"] == 4
            and index["status"] == "verified" and index["stopped_epoch"] == result["progress"]["epoch"] == 9
            and result["final_test_access"] is False and config["final_test"] is False,
            "original selected execution identity differs")
    trial = {key: settings["training"][key] for key in ("width", "learning_rate", "seed", "max_epochs",
                                                       "batch_size", "patience")}
    require(trial == result["trial"] == index["trial"]
            == {"width": 128, "learning_rate": .0003, "seed": 42, "max_epochs": 30, "batch_size": 64, "patience": 5},
            "original selected trial differs")
    require(config["source_commit"] == lineage["numerical_source_commit"]
            and config["image_digest"] == lineage["training_image_digest"]
            and sha(raw["configuration"]) == result["request_sha256"] == index["request_sha256"]
            == lineage["selection_request_sha256"]
            and selection["status"] == selection["result"]["status"] == "verified"
            and {**result, "status": "verified"} == selection["result"]
            and result["bindings"] == metadata["verification"]["result"]["checkpoint_origin"]["bindings"],
            "original configuration/result evidence differs")
    for name in ("verification", "selection_verification", "decision", "comparison_summary", "contract", "normalization"):
        require(pins[name].as_dict() == settings["artifacts"][name], "settings original receipt differs")
    require(index["verification_sha256"] == pins["selection_verification"].sha256
            and metadata["verification"]["status"] == metadata["comparison_summary"]["verification"]["status"]
            == "verified"
            and metadata["comparison_summary"]["verification"]["receipt_sha256"] == pins["verification"].sha256
            and metadata["decision"]["results_evidence_sha256"] == pins["comparison_summary"].sha256
            and metadata["decision"]["decision"] == settings["decision"], "original evidence trust chain differs")
    checkpoint = result["selected_checkpoint"]
    require(checkpoint == index["selected_checkpoint"]
            and all(checkpoint[k] == settings["artifacts"]["checkpoint"][k]
                    for k in ("sha256", "size_bytes", "version_id"))
            and checkpoint["epoch"] == 4 and checkpoint["version_id"] == "1"
            and settings["artifacts"]["checkpoint"]["uri"] == RESULTS + RUN.removesuffix("-search-128-0003")
            + "/search-128-0003/" + checkpoint["object_name"], "original checkpoint reference differs")
    for name in ("configuration", "result"):
        ref = selection["inventory"][name + ".json"]
        require(ref == {k: getattr(pins[name], k) for k in ("sha256", "size_bytes", "version_id")},
                "original publication receipt differs")
    previous = None
    for count in range(12):
        name = f"event-{count:04}.json"
        ref = selection["inventory"][name]
        expected = Receipt(RESULTS + RUN.removesuffix("-search-128-0003") + "/search-128-0003/" + name, **ref)
        event_raw = events[name].checked(expected)
        event = record(event_raw)
        require(event["index"] == count and event["previous_sha256"] == previous
                and event["request_sha256"] == lineage["selection_request_sha256"], "original journal chain differs")
        previous = sha(event_raw)
        if count == 11:
            require(event["kind"] == "completed" and event["payload"]["result_sha256"] == sha(raw["result"]),
                    "original journal completion differs")
    campaign_inputs = metadata["campaign"]["inputs"]
    require(pins["development_inventory"].sha256 == campaign_inputs["inventory_sha256"], "input inventory pin differs")
    for name, key in (("root", "root_file_sha256"), ("tabular", "tabular_sha256"), ("sequence", "sequence_sha256")):
        require(pins[name].sha256 == campaign_inputs[key], "original manifest pin differs")
    require(metadata["contract"]["root"] == metadata["root"]
            and metadata["contract"]["ordered_features"] == settings["preprocessing"]["ordered_features"]
            and metadata["normalization"]["training_binding_sha256"] == lineage["training_binding_sha256"]
            and metadata["normalization"]["fitting_row_sha256"] == lineage["train_targets_sha256"],
            "original preprocessing/feature binding differs")
    require(settings["artifacts"]["contract"]["sha256"] == result["bindings"]["contract_sha256"]
            and settings["artifacts"]["normalization"]["sha256"] == result["bindings"]["normalization_sha256"]
            and settings["temperature"] == metadata["verification"]["result"]["calibration"]["temperature"]
            and settings["operating_points"] == [{"mode": item["mode"], "threshold": item["threshold"]}
                for item in metadata["verification"]["result"]["comparison"]["transformer_selected_operating_points"]],
            "original frozen calibration or preprocessing differs")
    params = {}
    for name, value in (("trial", trial), ("campaign", metadata["campaign"]), ("architecture", settings["architecture"]),
                        ("preprocessing", settings["preprocessing"]), ("training", settings["training"]),
                        ("resources", config["resources"]), ("data", metadata["root"]),
                        ("source", result["bindings"]), ("calibration", {"temperature": settings["temperature"],
                          "operating_points": settings["operating_points"]})):
        _flatten(value, name, params)
    start, finish = milliseconds(index["started_at"]), milliseconds(index["finished_at"])
    require(start < finish <= milliseconds(reconciled_at), "original/reconciliation time order differs")
    history = result["progress"]["history"]
    require(len(history) == 9 and [row["epoch"] for row in history] == list(range(1, 10)), "original nine epochs required")
    require(result["selection_log_loss"] == history[3]["selection_log_loss"]
            and result["selection_f1_at_half"] == history[3]["selection_f1_at_half"], "selected epoch metrics differ")
    metrics = []
    for row in history:
        for key in ("weighted_train_loss", "selection_log_loss", "selection_f1_at_half"):
            require(type(row[key]) in (int, float) and math.isfinite(row[key]), "finite original epoch metric required")
            metrics.append({"key": "epoch." + key, "value": row[key], "step": row["epoch"], "timestamp": finish})
    for key in ("selected_epoch", "parameter_count", "selection_log_loss", "selection_f1_at_half", "duration_seconds",
                "peak_allocated_gpu_bytes", "peak_reserved_gpu_bytes"):
        value = result[key]
        require(type(value) in (int, float) and math.isfinite(value), "finite original summary metric required")
        metrics.append({"key": "selected." + key, "value": value, "step": 0, "timestamp": finish})
    binding = {"run_name": RUN, "job_id": JOB, "request_sha256": lineage["selection_request_sha256"],
               "settings_sha256": pins["settings"].sha256, "source_commit": lineage["numerical_source_commit"],
               "image_digest": lineage["training_image_digest"]}
    tags = {RESERVATION: sha(canonical(binding)), "transformer.reconciliation_at": reconciled_at,
            "transformer.metric_timestamp_policy": "original_finish_utc_ms",
            "transformer.purpose": "retrospective_original_execution_metadata",
            **{"transformer." + key: str(value) for key, value in lineage.items()},
            "transformer.settings_sha256": pins["settings"].sha256,
            "transformer.original_completed_at": index["finished_at"],
            "transformer.original_started_at": index["started_at"]}
    uploads = [("lineage/" + name + (".jsonl" if name == "development_inventory" else ".json"), data)
               for name, data in sorted(raw.items())]
    uploads += [("lineage/" + name, events[name].data) for name in sorted(events)]
    uploads += [("lineage/artifact-index.json", canonical(settings["artifacts"]))]
    plan = {"schema_version": "original_transformer_mlflow_v1", "experiment": EXPERIMENT, "run_name": RUN,
            "start_time": start, "end_time": finish, "binding": binding, "tags": tags, "params": params,
            "metrics": metrics, "datasets": _datasets(metadata, inventory, settings),
            "artifacts": {name: {"size_bytes": len(data), "sha256": sha(data)} for name, data in uploads}}
    sealed = SealedPlan(canonical(plan), tuple(uploads))
    sealed.checked(sealed.sha256())
    return sealed
