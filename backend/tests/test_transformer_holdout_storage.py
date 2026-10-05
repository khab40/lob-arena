import time

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.holdout_storage import HoldoutStore  # noqa: E402
from app.ml.transformer.role_execution_transport import PublicationUncertain  # noqa: E402
from app.ml.transformer.holdout_spec import object_location  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402
from transformer_holdout_fixtures import FakeS3, final_inputs  # noqa: E402


def setup(tmp_path):
    req, gate, _, _, _ = final_inputs(tmp_path)
    s3 = FakeS3()
    for item in req.inputs:
        if (tmp_path / item.path).is_file():
            s3.objects[object_location(item.reference)] = (tmp_path / item.path).read_bytes()
    return HoldoutStore(s3, req, expires=time.monotonic() + 60), gate


def test_final_gate_before_any_s3_get(tmp_path):
    store, gate = setup(tmp_path)
    item = store.request.input("tabular.json")
    with pytest.raises(ValueError, match="requires reference parity"):
        store.input(item)
    assert store.s3.calls == []
    assert store.input(item, gate).version_id == "1"


def test_conditional_success_last_and_full_versioned_readback(tmp_path):
    store, _ = setup(tmp_path)
    store.claim()
    store.put("predictions.json", canonical([{"declared": 1}]))
    success = store.finish({"request_sha256": store.request.sha256()})
    writes = [args for kind, args in store.s3.calls if kind == "put"]
    assert all(args["IfNoneMatch"] == "*" for args in writes)
    assert writes[-1]["Key"].endswith("/SUCCESS")
    assert writes[-2]["Key"].endswith("/checksums.json")
    files, inventory = store.reconcile(success)
    assert set(files) == {"predictions.json", "result.json"}
    assert all(item["version_id"] == "1" for item in inventory.values())
    with pytest.raises(ValueError, match="already has evidence"):
        store.claim()


def test_ambiguous_put_never_retries_or_writes_success(tmp_path):
    store, _ = setup(tmp_path)
    store.s3.fail_put = True
    with pytest.raises(PublicationUncertain):
        store.put("predictions.json", b"partial")
    assert [kind for kind, _ in store.s3.calls] == ["put"]
    assert not any(key.endswith("/SUCCESS") for _, key in store.s3.objects)


@pytest.mark.parametrize("defect", ["bytes", "version", "deadline", "calls", "byte_budget"])
def test_read_faults_fail_closed(tmp_path, defect):
    store, gate = setup(tmp_path)
    item = store.request.input("tabular.json")
    if defect == "bytes":
        store.s3.objects[object_location(item.reference)] = b"changed"
    elif defect == "version":
        original = store.s3.get_object
        def changed(**args):
            return {**original(**args), "VersionId": "2"}
        store.s3.get_object = changed
    elif defect == "deadline":
        store.expires = time.monotonic() - 1
    elif defect == "calls":
        store.calls = 10000
    else:
        from app.ml.transformer.holdout_spec import MAX_READ
        store.read_bytes = MAX_READ
    with pytest.raises((ValueError, TimeoutError)):
        store.input(item, gate)


def test_changed_published_bytes_rejected_even_with_same_version(tmp_path):
    store, _ = setup(tmp_path)
    store.put("predictions.json", b"original")
    success = store.finish({"status": "complete"})
    store.s3.objects[(store.request.output_bucket, store.key("predictions.json"))] = b"tampered"
    with pytest.raises(ValueError):
        store.reconcile(success)
