"""Inert transport fixtures: no model imports, row reads or network calls."""
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from lightgbm_retention_contract import (  # noqa: E402
    decode, expected_tracking, load_inventory, tracking_mismatches,
)
from lightgbm_retention_transport import (  # noqa: E402
    TrackingReader, audit_storage, audit_tracking, fingerprint,
)


@pytest.fixture
def inventory():
    result = "s3://results/campaigns/example/development/run"
    roles = {k: "artifacts/" + k for k in (
        "training_manifest", "calibration_manifest", "validation_metrics", "feature_importance",
        "reliability_bins", "reliability_diagram", "model")}
    objects = [{"path": p, "uri": result + "/" + p, "size_bytes": 3,
                "sha256": hashlib.sha256(b"abc").hexdigest()}
               for p in [*roles.values(), "SUCCESS", "checksums.sha256"]]
    inputs = [{"fold": fold, "row_count": 1, "session_count": 1, "fold_membership_hash": "a" * 64,
               "artifact": {"logical_name": fold, "uri": fold + "/fixture.parquet",
                            "sha256": "b" * 64, "schema_version": "fixture"}}
              for fold in ("train", "validation")]
    return {"schema_version": "lightgbm_candidate_inventory_v1", "result_uri": result,
            "result_objects": objects, "artifact_roles": roles, "experiment_sha256": "c" * 64,
            "selection": {"campaign_id": "campaign"}, "candidate_sha256": "d" * 64,
            "freeze_sha256": "e" * 64,
            "lineage": {"mlflow_run_id": "1" * 32, "binding": {"model_id": "fixture"},
                        "input_release_uri": "s3://inputs/releases/run/staging", "feature_inputs": inputs,
                        "feature_release_id": "release", "feature_release_sha256": "f" * 64,
                        "training_git_commit": "2" * 40, "run_id": "run"},
            "configuration": {"experiment": {"hyperparameters": {"num_leaves": 8},
                               "excluded_features": [], "operating_mode": "balanced",
                               "precision_floor": .9, "recall_floor": .9},
                              "training_seed": 42, "preprocessing": {"mode": "none"},
                              "class_weights": {"strategy": "balanced_training_fold"},
                              "data_policy": {"base_session_weighting": "normalize_within_class"},
                              "calibration": {"method": "isotonic"}, "ordered_features": ["x"],
                              "early_stopping": {"best_iteration": 32, "best_score": .3},
                              "operating_points": [{"mode": "balanced", "threshold": .5,
                                                    "validation_metrics": {"precision": .7, "recall": .6, "f1": .65}}]}}


def run_fixture(inv):
    tags, params, metrics, inputs = expected_tracking(inv)
    return {"info": {"run_id": "1" * 32, "experiment_id": "7", "status": "FINISHED",
                     "lifecycle_stage": "active", "artifact_uri": "mlflow-artifacts:/7/run/artifacts"},
            "data": {k: [{"key": a, "value": b} for a, b in v.items()]
                     for k, v in (("tags", tags), ("params", params), ("metrics", metrics))},
            "inputs": {"dataset_inputs": [{"dataset": {"name": i["name"], "digest": i["digest"],
                        "source_type": "s3", "source": json.dumps({"uri": i["source"]})},
                        "tags": [{"key": k, "value": v} for k, v in i["tags"].items()]} for i in inputs]}}


def test_anchor_and_development_boundary(inventory):
    raw = json.dumps(inventory).encode()
    assert load_inventory(raw, hashlib.sha256(raw).hexdigest(), "results", "inputs") == inventory
    with pytest.raises(ValueError, match="anchor mismatch"):
        load_inventory(raw, "0" * 64, "results", "inputs")


@pytest.mark.parametrize("mutation", ["bucket", "traversal", "duplicate", "size", "final", "markers"])
def test_invalid_inventory_rejected_before_transport(inventory, mutation):
    obj = inventory["result_objects"][0]
    if mutation == "bucket":
        obj["uri"] = "s3://other/a"
    if mutation == "traversal":
        obj["path"] = "../a"
    if mutation == "duplicate":
        inventory["result_objects"].append(copy.deepcopy(obj))
    if mutation == "size":
        obj["size_bytes"] = 100 * 1024**2
    if mutation == "final":
        inventory["lineage"]["feature_inputs"][0]["fold"] = "test"
    if mutation == "markers":
        inventory["result_objects"].pop()
    raw = json.dumps(inventory).encode()
    with pytest.raises(ValueError):
        load_inventory(raw, hashlib.sha256(raw).hexdigest(), "results", "inputs")


@pytest.mark.parametrize("category,key", [("tags", "feature_release_id"), ("tags", "feature_release_sha256"),
    ("tags", "git_commit"), ("params", "training_seed"), ("params", "num_leaves"), ("metrics", "balanced_threshold")])
def test_live_metadata_drift(inventory, category, key):
    run = run_fixture(inventory)
    assert tracking_mismatches(inventory, run) == []
    next(x for x in run["data"][category] if x["key"] == key)["value"] = "wrong"
    assert category + "." + key in tracking_mismatches(inventory, run)


@pytest.mark.parametrize("mutation", ["hash", "context", "source", "missing", "extra", "duplicate"])
def test_dataset_lineage_drift(inventory, mutation):
    run = run_fixture(inventory)
    inputs = run["inputs"]["dataset_inputs"]
    if mutation in {"hash", "context"}:
        key = "artifact_sha256" if mutation == "hash" else "mlflow.data.context"
        next(x for x in inputs[0]["tags"] if x["key"] == key)["value"] = "wrong"
    if mutation == "source":
        inputs[0]["dataset"]["source"] = '{"uri":"s3://other/wrong"}'
    if mutation == "missing":
        inputs.pop()
    if mutation in {"extra", "duplicate"}:
        inputs.append(copy.deepcopy(inputs[0]))
        if mutation == "extra":
            inputs[-1]["dataset"]["name"] = "unexpected"
    if mutation == "duplicate":
        with pytest.raises(ValueError, match="duplicate dataset"):
            tracking_mismatches(inventory, run)
    else:
        assert tracking_mismatches(inventory, run)


def test_storage_hashes_and_size_bound(inventory):
    class Reader:
        def object(self, obj): return fingerprint(io.BytesIO(b"abc"), obj["size_bytes"])
    assert audit_storage(inventory, Reader())["count"] == 9
    inventory["result_objects"][-1]["sha256"] = "0" * 64
    result = audit_storage(inventory, Reader())
    assert result["verified"] is False
    assert result["count"] == 8
    assert result["failed_path"] == "checksums.sha256"
    with pytest.raises(ValueError, match="exceeds"):
        fingerprint(io.BytesIO(b"abcd"), 3)


def test_tracking_artifacts_and_pagination(inventory):
    class Reader:
        def metadata(self, route, query):
            if route.endswith("runs/get"):
                return {"run": run_fixture(inventory)}
            if route.endswith("experiments/get"):
                return {"experiment": {"name": "lob-arena/lightgbm-development"}}
            return {"files": [{"path": "governed/" + role, "is_dir": False, "file_size": 3}
                              for role in inventory["artifact_roles"]]}
        def artifact(self, root, path, size): return fingerprint(io.BytesIO(b"abc"), size)
    assert audit_tracking(inventory, Reader())["artifacts_checked"] == 7
    class Repeating(Reader):
        def metadata(self, route, query):
            if route.endswith("artifacts/list"):
                return {"next_page_token": "same"}
            return super().metadata(route, query)
    with pytest.raises(ValueError, match="repeated pagination"):
        audit_tracking(inventory, Repeating())


@pytest.mark.parametrize("uri", ["http://remote:5500", "http://user:pass@localhost:5500", "https://localhost:5500", "http://localhost:5500/path"])
def test_only_loopback_tracking_transport(uri):
    with pytest.raises(ValueError, match="loopback"):
        TrackingReader(uri)


def test_duplicate_json_and_nonfinite():
    for raw in ('{"a":1,"a":2}', '{"x":NaN}'):
        with pytest.raises(ValueError):
            decode(raw)


@pytest.mark.parametrize("optimization", ["", "-O", "-OO"])
def test_plan_and_no_overwrite_without_dependencies(inventory, tmp_path, optimization):
    import subprocess
    source = tmp_path / "inventory.json"
    source.write_text(json.dumps(inventory))
    target = tmp_path / "receipt.json"
    command = [sys.executable, "-S", *([optimization] if optimization else []),
               str(SCRIPTS / "audit_lightgbm_retention.py"), "--inventory", str(source),
               "--inventory-sha256", hashlib.sha256(source.read_bytes()).hexdigest(),
               "--results-bucket", "results", "--input-bucket", "inputs", "--output", str(target)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(target.read_text())
    assert report["status"] == "planned"
    assert report["storage"]["verified"] is False
    original = target.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert target.read_bytes() == original
    component_target = tmp_path / "mlflow-plan.json"
    component_command = [*command, "--component", "mlflow"]
    component_command[component_command.index("--output") + 1] = str(component_target)
    assert subprocess.run(component_command, capture_output=True).returncode == 0
    component_plan = json.loads(component_target.read_text())
    assert component_plan["requested_components"] == ["mlflow"]
    assert component_plan["bounds"]["result_objects"] == 0
    assert component_plan["storage"]["verified"] is False
    command[command.index("--inventory-sha256") + 1] = "0" * 64
    assert subprocess.run(command, capture_output=True).returncode != 0


def test_redirects_and_untrusted_artifact_root(monkeypatch):
    from lightgbm_retention_transport import NoRedirect
    monkeypatch.setenv("MLFLOW_TRACKING_USERNAME", "fixture")
    monkeypatch.setenv("MLFLOW_TRACKING_PASSWORD", "fixture")
    reader = TrackingReader("http://127.0.0.1:5500")
    assert NoRedirect().redirect_request(None) is None
    with pytest.raises(ValueError, match="proxy root"):
        reader.artifact("mlflow-artifacts://elsewhere/path", "model", 1)
    with pytest.raises(ValueError, match="unsafe"):
        reader.artifact("mlflow-artifacts:/../path", "model", 1)
