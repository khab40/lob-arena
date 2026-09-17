"""Inert byte publication tests; no cloud, model imports or runtime execution."""
import hashlib
import json

import pytest

from scripts import publish_g8_native_package as publisher


@pytest.fixture
def staging(tmp_path, monkeypatch):
    mount = tmp_path / "native"
    mount.mkdir()
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested/inert.txt").write_bytes(b"frozen bytes")
    inventory = tmp_path / "inventory.json"
    values = {"files": {"nested/inert.txt": {
        "sha256": hashlib.sha256(b"frozen bytes").hexdigest(), "size_bytes": 12}}}
    inventory.write_text(json.dumps(values))
    monkeypatch.setattr(publisher, "MOUNT", mount)
    monkeypatch.setattr(publisher, "check_mount", lambda: None)
    return source, inventory, mount


def publish(staging):
    source, inventory, _ = staging
    return publisher.publish(source, inventory, hashlib.sha256(inventory.read_bytes()).hexdigest())


def test_publish_verifies_native_bytes_and_never_replaces(staging):
    receipt = publish(staging)
    destination = staging[2] / "package/nested/inert.txt"
    assert destination.read_bytes() == b"frozen bytes"
    assert destination.stat().st_mode & 0o777 == 0o400
    assert receipt["native_package_bytes_verified"]
    assert not receipt["job_read_only_mount_verified"]
    with pytest.raises(FileExistsError):
        publish(staging)
    assert destination.read_bytes() == b"frozen bytes"


def test_production_staging_preserves_rehearsal_package(staging):
    source, inventory, mount = staging
    publish(staging)
    receipt = publisher.publish(source, inventory, hashlib.sha256(inventory.read_bytes()).hexdigest(),
                                destination_name="production")
    assert receipt["native_package_bytes_verified"]
    assert (mount / "package/nested/inert.txt").read_bytes() == b"frozen bytes"
    assert (mount / "production/nested/inert.txt").read_bytes() == b"frozen bytes"
    with pytest.raises(FileExistsError):
        publisher.publish(source, inventory, hashlib.sha256(inventory.read_bytes()).hexdigest(),
                          destination_name="production")
    with pytest.raises(ValueError, match="destination"):
        publisher.publish(source, inventory, "0" * 64, destination_name="../elsewhere")


@pytest.mark.parametrize("fault", ["tamper", "link", "extra", "path", "oversize", "inventory-hash"])
def test_invalid_input_fails_before_native_writes(staging, fault):
    source, inventory, mount = staging
    path = source / "nested/inert.txt"
    if fault == "tamper":
        path.write_bytes(b"changed data")
    elif fault == "link":
        path.rename(source / "real.txt")
        path.symlink_to(source / "real.txt")
    elif fault == "extra":
        (source / "extra").write_bytes(b"extra")
    elif fault in {"path", "oversize"}:
        data = json.loads(inventory.read_text())
        ref = data["files"].pop("nested/inert.txt")
        if fault == "oversize":
            ref["size_bytes"] = 40961
        data["files"]["../escape" if fault == "path" else "nested/inert.txt"] = ref
        inventory.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        if fault == "inventory-hash":
            publisher.publish(source, inventory, "0" * 64)
        else:
            publish(staging)
    assert not list(mount.iterdir())
