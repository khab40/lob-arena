import io
import json
import os
from pathlib import Path

import pytest

from app.ml.transformer.role_execution_spec import (
    INPUT_BUCKET, INPUT_PREFIX, INVENTORY_SHA, MAX_GET_ATTEMPTS, OUTPUT_BUCKET,
    OUTPUT_PREFIX, canonical, digest, load_inventory,
)
from app.ml.transformer.role_execution_transport import (
    Budget, PublicationUncertain, claim, download, publish, put_new, read_result, read_version,
)

REQUEST = {"output_bucket": OUTPUT_BUCKET, "output_prefix": OUTPUT_PREFIX}
ITEM = {"key": INPUT_PREFIX + "fixture", "version_id": "1", "size_bytes": 3, "sha256": digest(b"abc")}
INVENTORY = Path(__file__).resolve().parents[2] / "docs/evidence/transformer-development-input-inventory-20260928.jsonl"


class Store:
    def __init__(self):
        self.objects, self.puts, self.gets = {}, [], []
        self.version, self.fail_name = "1", None

    def list_objects_v2(self, **kw):
        assert kw == {"Bucket": OUTPUT_BUCKET, "Prefix": OUTPUT_PREFIX, "MaxKeys": 1}
        return {"KeyCount": int(bool(self.objects))}

    def put_object(self, **kw):
        assert kw["IfNoneMatch"] == "*"
        self.puts.append(kw)
        if kw["Key"] in self.objects:
            raise OSError("conditional conflict")
        self.objects[kw["Key"]] = kw["Body"]
        if kw["Key"].endswith("/" + str(self.fail_name)):
            raise OSError("response lost after write")
        return {"VersionId": self.version}

    def get_object(self, **kw):
        self.gets.append(kw)
        return self.response


@pytest.mark.parametrize("change", ["version", "size", "checksum", "extra", "short"])
def test_input_corruption_closes_stream_and_never_retries(change):
    store = Store()
    body = io.BytesIO({"checksum": b"xyz", "extra": b"abcd", "short": b"ab"}.get(change, b"abc"))
    store.response = {"Body": body, "VersionId": "2" if change == "version" else "1",
                      "ContentLength": 4 if change == "size" else 3}
    with pytest.raises(ValueError):
        read_version(store, ITEM, Budget())
    assert body.closed and len(store.gets) == 1
    assert store.gets[0] == {"Bucket": INPUT_BUCKET, "Key": ITEM["key"], "VersionId": "1"}


def test_frozen_inventory_and_one_attempt_download(tmp_path):
    items = load_inventory(INVENTORY, INVENTORY_SHA)
    store = Store()
    store.response = {"Body": io.BytesIO(b""), "VersionId": "wrong", "ContentLength": 0}
    with pytest.raises(ValueError, match="version or size"):
        download(store, items, tmp_path / "inputs")
    assert len(store.gets) == 1
    items[-1]["key"] += "-changed"
    with pytest.raises(ValueError, match="frozen 185"):
        download(store, items, tmp_path / "changed")
    assert len(store.gets) == 1 and not (tmp_path / "changed").exists()
    with pytest.raises(ValueError, match="budget"):
        read_version(store, ITEM, Budget(attempts=MAX_GET_ATTEMPTS))
    assert len(store.gets) == 1


def test_claim_is_exclusive_and_request_scoped():
    store = Store()
    claim(store, REQUEST)
    with pytest.raises(ValueError, match="already contains"):
        claim(store, REQUEST)
    with pytest.raises(ValueError, match="identity"):
        claim(store, {**REQUEST, "output_prefix": "somewhere-else/"})
    assert len(store.puts) == 1


@pytest.mark.parametrize("version", [None, "", "null", " "])
def test_missing_versions_are_uncertain_publication(version):
    store = Store()
    store.version = version
    with pytest.raises(PublicationUncertain):
        put_new(store, REQUEST, "fixture.json", b"{}")
    assert len(store.puts) == 1


def test_success_last_binds_manifest_version_and_ambiguous_write_has_no_retry():
    store = Store()
    publish(store, REQUEST, {"fixture.json": b"{}"})
    assert [p["Key"].removeprefix(OUTPUT_PREFIX) for p in store.puts] == ["fixture.json", "checksums.json", "SUCCESS"]
    success = json.loads(store.puts[-1]["Body"])
    assert success["checksums_version_id"] == "1"
    assert success["checksums_sha256"] == digest(store.puts[-2]["Body"])
    assert success["request_sha256"] == digest(canonical(REQUEST))
    uncertain = Store()
    uncertain.fail_name = "SUCCESS"
    with pytest.raises(PublicationUncertain):
        publish(uncertain, REQUEST, {"fixture.json": b"{}"})
    assert len(uncertain.puts) == 3 and uncertain.puts[-1]["Key"].endswith("/SUCCESS")
    assert not any(p["Key"].endswith("/FAILED") for p in uncertain.puts)


@pytest.mark.parametrize("version,metadata", [("null", digest(b"abc")), ("2", digest(b"abc")), ("1", "wrong")])
def test_readback_refuses_unversioned_changed_or_unbound_bytes(version, metadata):
    store = Store()
    body = io.BytesIO(b"abc")
    store.response = {"Body": body, "VersionId": version, "ContentLength": 3, "Metadata": {"sha256": metadata}}
    with pytest.raises(ValueError):
        read_result(store, REQUEST, "fixture.json", 3, "1")
    assert body.closed


def test_real_sdk_stubber_uses_conditional_put_and_versioned_get():
    if os.environ.get("REQUIRE_REAL_METADATA_SDK") == "1":
        import botocore.session  # noqa: F401 - mandatory SDK parity must fail if absent
    session = pytest.importorskip("botocore.session")
    Stubber = pytest.importorskip("botocore.stub").Stubber
    from botocore.response import StreamingBody
    s3 = session.get_session().create_client("s3", region_name="eu-north1",
        aws_access_key_id="inert", aws_secret_access_key="inert")
    with Stubber(s3) as stub:
        stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"abc"), 3),
            "VersionId": "1", "ContentLength": 3},
            {"Bucket": INPUT_BUCKET, "Key": ITEM["key"], "VersionId": "1"})
        assert read_version(s3, ITEM, Budget()) == b"abc"
        stub.add_response("put_object", {"VersionId": "2"}, {"Bucket": OUTPUT_BUCKET,
            "Key": OUTPUT_PREFIX + "fixture.json", "Body": b"{}", "IfNoneMatch": "*",
            "ContentType": "application/json", "Metadata": {"sha256": digest(b"{}")}})
        assert put_new(s3, REQUEST, "fixture.json", b"{}")["version_id"] == "2"
        stub.assert_no_pending_responses()
