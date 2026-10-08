import io
from types import SimpleNamespace

import pytest

from app.ml.transformer import holdout_metadata as module
from app.ml.transformer.verification_spec import canonical, digest


@pytest.fixture
def audit(monkeypatch):
    root = {"schema_version": "inert-root"}
    monkeypatch.setattr(module, "ROOT_IDENTITY_SHA", digest(canonical(root)))
    tab, seq = [], []
    for i, run in enumerate(module.RUNS):
        count = 15131 if i == 0 else 1
        def ref(kind):
            return {"uri": f"{kind}/test/{run}.parquet", "sha256": "a" * 64, "size_bytes": 10}
        tab.append({"run_id": run, "supervised_row_count": count, "row_identity_sha256": "b" * 64,
                    "rows": ref("tabular")})
        seq.append({"run_id": run, "sequence_count": count, "sequence_length": 64,
                    "sequence_identity_sha256": "b" * 64, "sequences": ref("sequence")})
    common = {"access_scope": "final_test", "folds": ["test"], "root_sha256": module.ROOT_IDENTITY_SHA}
    values = {"frozen-root.json": root, "tabular-projection.json": {**common, "shards": tab},
        "sequence-projection.json": {**common, "shards": seq, "order_columns": ["prediction_timestamp_ns", "sequence"]}}
    raw = {name: canonical(value) for name, value in values.items()}
    monkeypatch.setattr(module, "MANIFESTS", {name: digest(value) for name, value in raw.items()})
    proposal = canonical({"final_keys": list(module.FINAL_KEYS),
        "baseline_keys": [module.BASELINE_PREFIX + n for n in module.BASELINE],
        "bounds": {"get_attempts": 3, "head_attempts": 62, "max_object_bytes": module.MAX_OBJECT,
                   "seconds": 300, "automatic_retries": 0}})

    class S3:
        def __init__(self):
            self.calls, self.bodies = [], []
            self.meta = SimpleNamespace(endpoint_url=module.ENDPOINT, config=SimpleNamespace(
                region_name="eu-north1", s3={"addressing_style": "path"},
                retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=5))

        def get_object(self, **args):
            self.calls.append(("GET", args))
            data = raw[args["Key"].rsplit("/", 1)[1]]
            body = io.BytesIO(data)
            self.bodies.append(body)
            return {"Body": body, "ContentLength": len(data), "VersionId": "1"}

        def head_object(self, **args):
            self.calls.append(("HEAD", args))
            size = module.BASELINE.get(args["Key"].rsplit("/", 1)[1], {"size_bytes": 10})["size_bytes"]
            return {"ContentLength": size, "VersionId": "1"}

    return S3(), proposal, values, raw


def test_exact_audit_fetches_no_parquet_body_and_pins_versions(audit, tmp_path):
    s3, proposal, _, _ = audit
    result = module.collect(s3, proposal, digest(proposal), tmp_path / "audit")
    assert result["get_attempts"] == 3 and result["head_attempts"] == 62
    assert len(result["objects"]) == 65
    assert all(args["Key"].endswith(".json") for method, args in s3.calls if method == "GET")
    assert all(body.closed for body in s3.bodies)
    assert all(args["VersionId"] == "1" for method, args in s3.calls
               if method == "HEAD" and args["Bucket"] == module.BASELINE_BUCKET)
    assert result["final_payload_reads"] == 0 and result["model_execution"] is False
    assert result["fresh_payload_integrity_verified"] is result["execution_authorized"] is False


def test_bad_approval_and_existing_output_do_not_touch_cloud(audit, tmp_path):
    s3, proposal, _, _ = audit
    for pin, output in (("0" * 64, tmp_path / "new"), (digest(proposal), tmp_path)):
        with pytest.raises((ValueError, FileExistsError)):
            module.collect(s3, proposal, pin, output)
    assert s3.calls == []


def test_changed_manifest_stops_once_before_any_heads_and_closes_body(audit, tmp_path):
    s3, proposal, _, raw = audit
    raw["frozen-root.json"] += b" "
    with pytest.raises(ValueError):
        module.collect(s3, proposal, digest(proposal), tmp_path / "audit")
    assert len(s3.calls) == 1 and s3.calls[0][0] == "GET"
    assert s3.bodies[0].closed
    assert (tmp_path / "audit/failure.json").exists()
    assert not (tmp_path / "audit/verification.json").exists()


@pytest.mark.parametrize("field,value", [("VersionId", "null"), ("VersionId", ""),
    ("ContentLength", True), ("ContentLength", 0), ("ContentLength", 9),
    ("Metadata", {"sha256": "c" * 64})])
def test_changed_header_is_rejected(field, value):
    response = {"VersionId": "1", "ContentLength": 10, field: value}
    with pytest.raises(ValueError):
        module._header(response, {"sha256": "a" * 64, "size_bytes": 10, "version_id": "1"})


@pytest.mark.parametrize("kind", ["scope", "count", "path", "run", "shape", "order"])
def test_manifest_semantics_reject_unexpected_population(audit, kind):
    _, _, values, _ = audit
    tab, seq = values["tabular-projection.json"], values["sequence-projection.json"]
    if kind == "scope":
        tab["access_scope"] = "development"
    elif kind == "count":
        tab["shards"][0]["supervised_row_count"] -= 1
    elif kind == "path":
        seq["shards"][0]["sequences"]["uri"] = "sequence/test/../other.parquet"
    elif kind == "run":
        tab["shards"][0]["run_id"] = tab["shards"][1]["run_id"]
    elif kind == "shape":
        seq["shards"][0]["sequence_length"] = 32
    else:
        seq["order_columns"].reverse()
    with pytest.raises(ValueError):
        module.shard_inventory(values)


def test_retrying_sdk_is_rejected_before_io(audit, tmp_path):
    s3, proposal, _, _ = audit
    s3.meta.config.retries["total_max_attempts"] = 4
    with pytest.raises(ValueError):
        module.collect(s3, proposal, digest(proposal), tmp_path / "audit")
    assert s3.calls == []
