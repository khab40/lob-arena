import time

import pytest

pytest.importorskip("numpy")

from app.ml.transformer.holdout_readback import verify_result  # noqa: E402
from app.ml.transformer.holdout_readback_store import (  # noqa: E402
    OfflineReadbackStore, RetainingReadbackStore, input_name,
)
from app.ml.transformer.holdout_spec import object_location  # noqa: E402
from app.ml.transformer.settings_release import ArtifactRead  # noqa: E402
from app.ml.transformer.verification_spec import canonical, digest  # noqa: E402
from transformer_holdout_fixtures import FakeS3, final_inputs  # noqa: E402


def setup(tmp_path):
    request, gate, _, _, _ = final_inputs(tmp_path / "fixture")
    s3 = FakeS3()
    for item in request.inputs:
        path = tmp_path / "fixture" / item.path
        if path.is_file():
            s3.objects[object_location(item.reference)] = path.read_bytes()
    store = RetainingReadbackStore(s3, request, expires=time.monotonic() + 60,
                                   destination=tmp_path / "retained")
    return store, gate


def test_failed_verification_retains_exact_three_inputs_and_outputs(tmp_path, monkeypatch):
    from test_transformer_holdout_readback import publication
    source, settings, result = publication(tmp_path / "fixture", monkeypatch)
    result["comparison"]["modes"]["balanced"]["transformer"]["fp"] += 1
    success = source.finish(result)
    store = RetainingReadbackStore(source.s3, source.request, expires=time.monotonic() + 60,
                                   destination=tmp_path / "retained")
    args = dict(approved_request_sha256=source.request.sha256(),
                trusted_public_key=source.request.context_public_key, settings_reader=lambda ref: ArtifactRead(b"", "1"))
    with pytest.raises(ValueError, match="saved holdout metrics"):
        verify_result(store, success, settings, **args)
    assert len(store.results) == 7 and len(store.inputs) == 3
    calls = len(source.s3.calls)
    source.s3.get_object = lambda **kwargs: pytest.fail("offline read attempted cloud")
    replay = OfflineReadbackStore(source.request, store.destination)
    with pytest.raises(ValueError, match="saved holdout metrics"):
        verify_result(replay, success, settings, **args)
    assert replay.calls == 0 and len(source.s3.calls) == calls


@pytest.mark.parametrize("defect", ["gate", "scope", "version", "bytes", "symlink", "parent_symlink"])
def test_input_identity_and_path_fail_closed(tmp_path, defect):
    store, gate = setup(tmp_path)
    item = store.request.input("tabular.json")
    if defect in {"gate", "scope"}:
        if defect == "scope":
            item = store.request.input("sequence.json")
        with pytest.raises(ValueError):
            store.input(item, None if defect == "gate" else gate)
        assert not store.s3.calls
        return
    value = store.input(item, gate)
    base = store.destination / "inputs"
    path = base / (input_name(item) + (".json" if defect == "version" else ".bin"))
    if defect == "version":
        raw = item.model_dump(mode="json")
        raw["reference"]["version_id"] = "2"
        path.write_bytes(canonical(raw))
    elif defect == "bytes":
        path.write_bytes(b"x" * len(value.data))
    elif defect == "symlink":
        external = tmp_path / "external"
        external.write_bytes(value.data)
        path.unlink()
        path.symlink_to(external)
    else:
        base.rename(store.destination / "original-inputs")
        base.symlink_to(store.destination / "original-inputs", target_is_directory=True)
    replay = OfflineReadbackStore(store.request, store.destination)
    with pytest.raises(ValueError):
        replay.input(item, gate)


def test_cached_inputs_still_require_gate_and_results_keep_receipt(tmp_path):
    store, gate = setup(tmp_path)
    item = store.request.input("tabular.json")
    assert store.input(item, gate) == store.input(item, gate)
    assert store.calls == 1
    with pytest.raises(ValueError):
        store.input(item)
    raw = b"declared publication"
    expected = {"size_bytes": len(raw), "sha256": digest(raw), "version_id": "1"}
    store.s3.objects[(store.request.output_bucket, store.key("result.json"))] = raw
    assert store.read("result.json", expected) == raw
    replay = OfflineReadbackStore(store.request, store.destination)
    assert replay.read("result.json", expected) == raw
    with pytest.raises(ValueError, match="checksum differs"):
        replay.read("result.json", {**expected, "version_id": "2"})
    with pytest.raises(ValueError, match="receipt changed"):
        store.read("result.json", {**expected, "version_id": "2"})
    for method in (store.put, store.claim):
        with pytest.raises(ValueError):
            method()
    store.calls = 40
    with pytest.raises(ValueError, match="call budget"):
        store.start()


def test_offline_store_has_no_cloud_or_write_operations(tmp_path):
    store, _ = setup(tmp_path)
    replay = OfflineReadbackStore(store.request, store.destination)
    for method in (replay.get, replay.put, replay.claim):
        with pytest.raises(ValueError):
            method()
    with pytest.raises(ValueError):
        replay.read("../outside", {"sha256": "a" * 64, "size_bytes": 1, "version_id": "1"})
    with pytest.raises(FileExistsError):
        RetainingReadbackStore(store.s3, store.request, expires=time.monotonic() + 60,
                               destination=store.destination)


def test_changed_retention_directory_cannot_write_outside(tmp_path):
    store, gate = setup(tmp_path)
    external = tmp_path / "outside"
    external.mkdir()
    base = store.destination / "inputs"
    base.rmdir()
    base.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="directory changed"):
        store.input(store.request.input("tabular.json"), gate)
    assert list(external.iterdir()) == []
