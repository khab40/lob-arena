"""Inert S3 fault injection; no credentials, cloud calls or model execution."""
import io
import json

import pytest

pytest.importorskip("numpy")
from app.ml.transformer.research_execution_spec import template, validate  # noqa: E402
from app.ml.transformer.research_storage import Store, key  # noqa: E402
from app.ml.transformer.role_execution_transport import PublicationUncertain  # noqa: E402


class S3:
    def __init__(self):
        self.objects = {}
        self.corrupt = False
        self.ambiguous = False
        self.metadata_case = "sha256"

    def list_objects_v2(self, **args):
        return {"KeyCount": sum(name.startswith(args["Prefix"]) for name in self.objects)}

    def put_object(self, **args):
        assert args["IfNoneMatch"] == "*"
        if args["Key"] in self.objects:
            raise RuntimeError("conditional write conflict")
        self.objects[args["Key"]] = (args["Body"], args["Metadata"])
        if self.ambiguous:
            raise TimeoutError("response lost after successful write")
        return {"VersionId": "version-1"}

    def get_object(self, **args):
        assert args.get("VersionId", "version-1") == "version-1"
        raw, metadata = self.objects[args["Key"]]
        raw = b"x" * len(raw) if self.corrupt else raw
        metadata = {self.metadata_case: metadata["sha256"]}
        return {"Body": io.BytesIO(raw), "ContentLength": len(raw), "VersionId": "version-1", "Metadata": metadata}


def request():
    return template("smoke", "a" * 40, "sha256:" + "b" * 64, "c" * 64, "d" * 32, {})


@pytest.mark.parametrize("metadata_case", ["sha256", "Sha256", "SHA256"])
def test_durable_publication_has_terminal_inventory_and_journal(metadata_case):
    s3, req = S3(), request()
    s3.metadata_case = metadata_case
    store = Store(s3, req)
    store.claim()
    store.event("started", {})
    store.put("measurement.json", b"{}")
    terminal = store.finish({"quality": "unknown"})
    manifest = store.read_publication("smoke", terminal, json.loads(s3.objects[key("smoke", "SUCCESS")][0])["request_sha256"])
    assert set(manifest) == {"event-0000.json", "measurement.json", "result.json", "event-0001.json"}
    assert manifest["result.json"]["version_id"] == "version-1"
    with pytest.raises(ValueError, match="already has evidence"):
        Store(s3, req).claim()


@pytest.mark.parametrize("failure", ["corrupt", "ambiguous"])
def test_uncertain_publication_never_acknowledges_or_retries(failure):
    s3 = S3()
    setattr(s3, failure, True)
    store = Store(s3, request())
    with pytest.raises(PublicationUncertain):
        store.put("checkpoint.pt", b"not-real-model-fixture")
    assert not store.artifacts
    assert len(s3.objects) == 1
    assert key("smoke", "SUCCESS") not in s3.objects


@pytest.mark.parametrize("slot,name", [("test", "result"), ("smoke", "../x"), ("smoke", "/tmp/x")])
def test_storage_scope_rejects_other_slots_and_paths(slot, name):
    with pytest.raises(ValueError):
        key(slot, name)


def test_readback_binds_exact_version_and_checksum():
    store = Store(S3(), request())
    item = store.put("data.json", b"{}")
    with pytest.raises(ValueError):
        store.read("smoke", "data.json", {**item, "sha256": "f" * 64})


@pytest.mark.parametrize("field,value", [("final_test", True), ("output_prefix", "elsewhere/"),
    ("image_digest", "mutable:tag"), ("prior", {"smoke": {}}), ("slot", "search-unbounded")])
def test_execution_request_cannot_expand_scope(field, value):
    req = request()
    req[field] = value
    with pytest.raises(ValueError):
        validate(req)


def test_image_repository_limit_preserves_digest_addressing(monkeypatch):
    from app.ml.transformer import research_execution_spec as spec
    req = request()
    assert spec.provider_spec(req)["image"].endswith("@" + req["image_digest"])
    assert len(spec.REPOSITORY) <= 64
    monkeypatch.setattr(spec, "REPOSITORY", "r" * 65)
    with pytest.raises(ValueError, match="label limit"):
        spec.validate(req)
