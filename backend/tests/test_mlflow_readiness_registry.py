"""Inert metadata and artifact bytes only: no ML imports, workloads, or network."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deployments.mlflow import readiness_registry as registry  # noqa: E402
from test_lightgbm_retention_audit import (  # noqa: E402
    inventory as inventory_fixture, run_fixture, source_proof,
)


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def case(tmp_path):
    inv = json.loads(raw(inventory_fixture.__wrapped__()).decode().replace(
        "s3://results/", f"s3://{registry.RESULTS_BUCKET}/").replace(
        "s3://inputs/", f"s3://{registry.INPUT_BUCKET}/"))
    inventory = raw(inv)
    proof = source_proof(inv)
    proof.update(inventory_sha256=sha(inventory), source_root_uri=(
        f"s3://{registry.INPUT_BUCKET}/releases/earlier/staging/projection-artifacts"))
    proof = raw(proof)
    artifacts = {path: ("inert " + path).encode() for path in registry.ARTIFACTS}
    manifest = {"schema_version": "lightgbm_lineage_verification_v1", "status": "verified",
                "inventory_sha256": sha(inventory), "dataset_source_proof_sha256": sha(proof),
                "mlflow_run_id": inv["lineage"]["mlflow_run_id"], "dataset_inputs_verified": 2,
                "mlflow_artifacts_verified": 7, "mlflow_artifact_bytes": sum(map(len, artifacts.values())),
                **{k: inv[k] for k in ("candidate_sha256", "freeze_sha256")},
                "artifacts": [{"path": p, "size_bytes": len(b), "sha256": sha(b)} for p, b in artifacts.items()]}
    run = run_fixture(inv)
    for category in ("tags", "params", "metrics"):
        run["data"][category] = {x["key"]: x["value"] for x in run["data"][category]}
    for item in run["inputs"]["dataset_inputs"]:
        item["tags"] = {x["key"]: x["value"] for x in item["tags"]}
    class Client:
        def __init__(self):
            self.versions, self.aliases, self.writes, self.downloads = [], {}, [], []
            self.fail_create = self.fail_alias = False
        def get_run(self, run_id):
            return NS(info=NS(experiment_id="7"), to_dictionary=lambda: copy.deepcopy(run))
        def get_experiment(self, experiment_id):
            return NS(name="lob-arena/lightgbm-development")
        def get_registered_model(self, name):
            return NS(name=name, aliases=self.aliases.copy())
        def search_model_versions(self, filter_string, max_results):
            return self.versions[:max_results]
        def get_model_version(self, name, version):
            return next(v for v in self.versions if v.version == version)
        def create_model_version(self, **kwargs):
            assert len(self.downloads) == 7 and (tmp_path / "create-intent.json").exists()
            self.writes.append("create")
            if self.fail_create:
                raise TimeoutError("ambiguous response")
            kwargs.pop("await_creation_for")
            self.versions.append(NS(**kwargs, version="1", status="READY", current_stage="None"))
        def set_registered_model_alias(self, name, alias, version):
            assert (tmp_path / "alias-intent.json").exists()
            self.writes.append("alias")
            if self.fail_alias:
                raise TimeoutError("ambiguous response")
            self.aliases[alias] = version
        def download(self, run_id, path, limit):
            self.downloads.append(path)
            return artifacts[path]
    client = Client()
    def execute():
        value = raw(manifest)
        return registry.register_baseline(client, client.download, value, inventory, proof,
                                          tmp_path, manifest_sha256=sha(value))
    return NS(client=client, run=run, manifest=manifest, artifacts=artifacts, execute=execute)


def test_verified_research_binding_and_repeat_are_idempotent(case):
    receipt = case.execute()
    assert receipt["verified"] and not receipt["model_execution"]
    assert receipt["binding"]["tags"]["deployable_mlflow_flavor"] == "false"
    assert receipt["alias"] == "research-baseline"
    assert case.execute() == receipt
    assert case.client.writes == ["create", "alias"]


@pytest.mark.parametrize("drift", ["bytes", "feature", "dataset", "duplicate", "run", "size"])
def test_drift_prevents_every_registry_write(case, drift):
    if drift == "bytes":
        case.artifacts["governed/model.txt"] = b"changed"
    if drift == "feature":
        case.run["data"]["tags"]["feature_release_sha256"] = "0" * 64
    if drift == "dataset":
        case.run["inputs"]["dataset_inputs"][0]["tags"]["artifact_sha256"] = "0" * 64
    if drift == "duplicate":
        case.manifest["artifacts"][-1] = case.manifest["artifacts"][0]
    if drift == "run":
        case.run["info"]["status"] = "RUNNING"
    if drift == "size":
        case.manifest["mlflow_artifact_bytes"] = 90459
    with pytest.raises(ValueError):
        case.execute()
    assert case.client.writes == []


@pytest.mark.parametrize("mutation", ["source", "tags", "alias", "extra", "stage"])
def test_existing_registry_conflicts_never_overwritten(case, mutation):
    case.execute()
    if mutation in {"source", "stage"}:
        setattr(case.client.versions[0], "source" if mutation == "source" else "current_stage", "wrong")
    if mutation == "tags":
        case.client.versions[0].tags["candidate_sha256"] = "0" * 64
    if mutation == "alias":
        case.client.aliases[registry.ALIAS] = "2"
    if mutation == "extra":
        case.client.versions.append(case.client.versions[0])
    with pytest.raises(ValueError):
        case.execute()
    assert case.client.writes == ["create", "alias"]


@pytest.mark.parametrize("operation", ["create", "alias"])
def test_ambiguous_mutation_has_no_automatic_retry(case, operation):
    setattr(case.client, "fail_" + operation, True)
    with pytest.raises(TimeoutError):
        case.execute()
    writes = list(case.client.writes)
    with pytest.raises(ValueError, match="no retry"):
        case.execute()
    assert case.client.writes == writes
