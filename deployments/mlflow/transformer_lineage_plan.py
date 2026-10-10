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


