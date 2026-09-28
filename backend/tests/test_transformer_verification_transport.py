import io
import json
from pathlib import Path
import time

import pytest

from app.ml.transformer.verification_spec import INPUT_PREFIX, INVENTORY_SHA, canonical, digest, load_inventory
from app.ml.transformer.verification_transport import Budget, claim, deadline, download, publish, read_version

INVENTORY = Path(__file__).resolve().parents[2] / "docs/evidence/transformer-development-input-inventory-20260928.jsonl"


class Store:
    def __init__(self):
        self.objects = {}
        self.puts = []
        self.gets = []
        self.fail_put = 0
        self.response = {}

    def list_objects_v2(self, **kw):
        assert kw["MaxKeys"] == 1
        return {"KeyCount": int(any(k.startswith(kw["Prefix"]) for k in self.objects))}

    def put_object(self, **kw):
        assert kw["IfNoneMatch"] == "*"
        if kw["Key"] in self.objects or len(self.puts) + 1 == self.fail_put:
            raise ValueError("conditional write rejected")
        self.puts.append(kw)
        self.objects[kw["Key"]] = kw["Body"]
        return {"VersionId": "1"}

    def get_object(self, **kw):
        self.gets.append(kw)
        return self.response


def test_approved_inventory_and_scope(tmp_path):
    assert len(load_inventory(INVENTORY, INVENTORY_SHA)) == 185
    with pytest.raises(ValueError, match="checksum"):
        load_inventory(INVENTORY, "0" * 64)
    items = [json.loads(s) for s in INVENTORY.read_text().splitlines()]
    items[-1]["key"] = INPUT_PREFIX + "artifacts/sequence/test/forbidden.parquet"
    path = tmp_path / "inventory.jsonl"
    path.write_bytes(b"\n".join(canonical(s) for s in items))
    with pytest.raises(ValueError, match="path"):
        load_inventory(path, digest(path.read_bytes()))


@pytest.mark.parametrize("change", ["version", "size", "checksum", "extra", "short"])
def test_changed_s3_input_fails_closed_and_closes_stream(change):
    s3 = Store()
    item = {"key": INPUT_PREFIX + "object", "version_id": "1", "size_bytes": 3, "sha256": digest(b"abc")}
    body = io.BytesIO({"checksum": b"xyz", "extra": b"abcd", "short": b"ab"}.get(change, b"abc"))
    s3.response = {"Body": body, "VersionId": "2" if change == "version" else "1",
                   "ContentLength": 4 if change == "size" else 3}
    with pytest.raises(ValueError):
        read_version(s3, item, Budget())
    assert body.closed
    assert s3.gets[0]["VersionId"] == "1"


def test_download_is_version_specific_and_never_overwrites_local_files(tmp_path):
    s3 = Store()
    s3.response = {"Body": io.BytesIO(b"abc"), "VersionId": "1", "ContentLength": 3}
    item = {"key": INPUT_PREFIX + "manifests/root.json", "version_id": "1",
            "size_bytes": 3, "sha256": digest(b"abc")}
    directory = tmp_path / "inputs"
    receipt = download(s3, [item], directory)
    assert (directory / "manifests/root.json").read_bytes() == b"abc"
    assert receipt == {"get_attempts": 1, "response_bytes": 3}
    with pytest.raises(FileExistsError):
        download(s3, [item], directory)
    assert len(s3.gets) == 1


def test_retry_budget_counts_failed_attempts(tmp_path, monkeypatch):
    import app.ml.transformer.verification_transport as transport
    calls = []
    def transient(s3, item, budget):
        budget.start()
        calls.append(1)
        raise OSError("fixture transport failure")
    monkeypatch.setattr(transport, "read_version", transient)
    monkeypatch.setattr(transport, "retryable", lambda e: True)
    monkeypatch.setattr(transport.time, "sleep", lambda _: None)
    with pytest.raises(OSError):
        download(Store(), [{"key": INPUT_PREFIX + "object"}], tmp_path / "inputs")
    assert len(calls) == 3


def test_existing_output_refuses_claim_without_writing():
    s3 = Store()
    claim(s3, {"fixture": True})
    before = dict(s3.objects)
    with pytest.raises(ValueError, match="already contains"):
        claim(s3, {"fixture": False})
    assert s3.objects == before


def test_success_is_last_and_partial_publication_never_marks_success():
    s3 = Store()
    publish(s3, {"normalization.json": b"{}", "configuration.json": b"{}"}, "0" * 64)
    assert s3.puts[-1]["Key"].endswith("/SUCCESS")
    assert s3.puts[-2]["Key"].endswith("/checksums.json")
    failed = Store()
    failed.fail_put = 2
    with pytest.raises(ValueError):
        publish(failed, {"normalization.json": b"{}", "configuration.json": b"{}"}, "0" * 64)
    assert not any(k.endswith("/SUCCESS") for k in failed.objects)


def test_budget_and_deadline_enforced():
    with pytest.raises(ValueError, match="budget"):
        Budget(attempts=555).start()
    with pytest.raises(TimeoutError, match="deadline"):
        with deadline(0.01):
            time.sleep(0.05)
