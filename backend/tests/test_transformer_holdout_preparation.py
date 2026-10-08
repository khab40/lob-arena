from io import BytesIO
from pathlib import Path

import pytest

from app.ml.transformer import holdout_preparation as prep

ROOT = Path(__file__).resolve().parents[2]


class Missing(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self, *, exists=False, version="1", changed=False):
        self.exists, self.version, self.changed = exists, version, changed
        self.calls = []

    def head_object(self, **args):
        self.calls.append(("HEAD", args))
        if not self.exists:
            raise Missing()
        return {}

    def put_object(self, **args):
        self.calls.append(("PUT", args))
        self.raw = args["Body"]
        return {"VersionId": self.version}

    def get_object(self, **args):
        self.calls.append(("GET", args))
        raw = self.raw + b"x" if self.changed else self.raw
        return {"VersionId": self.version, "ContentLength": len(self.raw),
                "Metadata": {"sha256": prep.REFERENCE_SHA}, "Body": BytesIO(raw)}


def fixture_reference(monkeypatch):
    raw = b'[{"target_id":"fixture","logit":0}]'
    monkeypatch.setattr(prep, "REFERENCE_SHA", prep.digest(raw))
    monkeypatch.setattr(prep, "REFERENCE_SIZE", len(raw))
    return raw


def test_conditional_reference_publication_has_versioned_exact_readback(monkeypatch):
    raw = fixture_reference(monkeypatch)
    s3 = FakeS3()
    ref = prep.publish_reference(s3, raw)
    assert ref.version_id == "1" and ref.sha256 == prep.digest(raw)
    assert [c[0] for c in s3.calls] == ["HEAD", "PUT", "GET"]
    assert s3.calls[1][1]["IfNoneMatch"] == "*"
    assert s3.calls[-1][1]["VersionId"] == "1"


@pytest.mark.parametrize("defect", ["bytes", "exists", "version", "readback"])
def test_reference_failure_never_retries_or_overwrites(monkeypatch, defect):
    raw = fixture_reference(monkeypatch)
    s3 = FakeS3(exists=defect == "exists", version="null" if defect == "version" else "1",
                changed=defect == "readback")
    with pytest.raises(ValueError):
        prep.publish_reference(s3, raw + b"x" if defect == "bytes" else raw)
    assert sum(method == "PUT" for method, _ in s3.calls) <= 1
    if defect in {"bytes", "exists"}:
        assert all(method != "PUT" for method, _ in s3.calls)


def test_changed_audit_inventory_is_rejected_before_emitting_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "load_inventory", lambda *args: [])
    changed = tmp_path / "audit.json"
    changed.write_bytes(b"[]")
    with pytest.raises(ValueError, match="inventory changed"):
        prep.audited_inputs(tmp_path / "development.jsonl", changed)


def test_prepared_inventory_matches_manifest_relative_shard_paths(tmp_path, monkeypatch):
    items = [{"key": prep.INPUT_PREFIX + f"artifacts/{kind}/train/run-{i}.parquet",
              "sha256": "1" * 64, "size_bytes": 100, "version_id": "1"}
             for kind in ("tabular", "sequence") for i in range(90)]
    items += [{"key": prep.INPUT_PREFIX + name, "sha256": "2" * 64,
               "size_bytes": 100, "version_id": "1"}
              for name in ("SUCCESS", "checksums.sha256", "manifests/frozen-root.json",
                           "manifests/tabular-projection.json", "manifests/sequence-projection.json")]
    monkeypatch.setattr(prep, "load_inventory", lambda *args: items)
    audited = ROOT / "docs/evidence/transformer-holdout-object-inventory-20261006.json"
    inputs = prep.audited_inputs(tmp_path / "development.jsonl", audited)
    assert len(inputs) == 248
    assert sum(i.scope == "final_test" for i in inputs) == 63
    paths = {i.path for i in inputs}
    assert {"development-tabular.json", "development-sequences.json",
            "manifests/tabular-projection.json", "manifests/sequence-projection.json",
            "baseline/predictions.parquet"} <= paths
    for item in inputs:
        if "/staging/artifacts/" in item.reference.uri:
            assert item.path == item.reference.uri.split("/staging/artifacts/", 1)[1]
            assert not item.path.startswith("artifacts/")


@pytest.mark.parametrize("metadata,ok", [({"Sha256": "expected"}, True),
    ({"SHA256": "expected"}, True), ({"sha256": "expected", "SHA256": "expected"}, False),
    ({"Sha256": "wrong"}, False), ({}, False)])
def test_reference_readback_accepts_sdk_casing_but_rejects_ambiguity(monkeypatch, metadata, ok):
    raw = fixture_reference(monkeypatch)
    s3 = FakeS3()
    original = s3.get_object
    def response(**args):
        observed = original(**args)
        observed["Metadata"] = {k: prep.REFERENCE_SHA if v == "expected" else v
                                for k, v in metadata.items()}
        return observed
    s3.get_object = response
    if ok:
        assert prep.publish_reference(s3, raw).sha256 == prep.REFERENCE_SHA
    else:
        with pytest.raises(ValueError):
            prep.publish_reference(s3, raw)
    assert sum(method == "PUT" for method, _ in s3.calls) == 1
