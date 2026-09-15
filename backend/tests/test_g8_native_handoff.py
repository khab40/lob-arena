"""Static operator transport checks; no cloud calls or model imports."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import g8_native_handoff as handoff
from scripts import publish_g8_native_context as publisher


@pytest.fixture
def before():
    return {"metadata": {"id": handoff.VM, "parent_id": handoff.PROJECT,
                         "name": "aimada-wave1-mlflow", "resource_version": "40"},
            "spec": {"stopped": True, "boot_disk": {"managed_disk": {"name": "preserve-me"}},
                     "service_account_id": "preserve-service-account", "network_interfaces": [{"name": "eth0"}]},
            "status": {"state": "STOPPED", "network_interfaces": [{"private_ip": "10.4.0.54"}]}}


@pytest.fixture
def filesystem():
    return {"metadata": {"id": "computefilesystem-example", "parent_id": handoff.PROJECT},
            "spec": {"type": "NETWORK_SSD", "size_gibibytes": "10"},
            "status": {"state": "READY", "size_bytes": str(10 * 1024**3)}}


def attached(before, filesystem):
    current = deepcopy(before)
    current["metadata"]["resource_version"] = "41"
    current["spec"]["filesystems"] = [handoff.attachment(filesystem["metadata"]["id"])]
    return current


def test_attach_and_restore_use_current_resource_version(before, filesystem):
    command = handoff.render(before, before, filesystem, filesystem_id="computefilesystem-example")["command"]
    assert "--patch" in command and command[command.index("--resource-version") + 1] == "40"
    assert command[command.index("--parent-id") + 1] == handoff.PROJECT
    current = attached(before, filesystem)
    receipt = handoff.verify_vm(before, current, filesystem["metadata"]["id"], attached=True)
    assert not receipt["context_delivery_verified"] and not receipt["native_mount_verified"]
    filesystem["status"]["read_write_attachments"] = [handoff.VM]
    command = handoff.render(before, current, filesystem, filesystem_id="computefilesystem-example", detach=True)["command"]
    assert command[command.index("--resource-version") + 1] == "41"
    assert command[-2:] == ["--clear-mask", "spec.filesystems"]
    restored = deepcopy(before)
    restored["metadata"]["resource_version"] = "44"
    assert not handoff.verify_vm(before, restored, filesystem["metadata"]["id"], attached=False)["attached"]


@pytest.mark.parametrize("section,key,value", [
    ("metadata", "id", "computeinstance-other"), ("metadata", "resource_version", "0"),
    ("metadata", "resource_version", "39"), ("spec", "service_account_id", "changed"),
    ("spec", "boot_disk", {}), ("spec", "network_interfaces", []),
    ("spec", "filesystems", []), ("spec", "stopped", False),
    ("status", "network_interfaces", []), ("status", "state", "RUNNING"),
])
def test_unrelated_vm_drift_rejected(before, filesystem, section, key, value):
    current = attached(before, filesystem)
    current[section][key] = value
    with pytest.raises(ValueError):
        handoff.verify_vm(before, current, filesystem["metadata"]["id"], attached=True)


def test_existing_filesystem_owner_and_unstopped_baseline_rejected(before, filesystem):
    filesystem["status"]["read_write_attachments"] = ["computeinstance-other"]
    with pytest.raises(ValueError, match="owners"):
        handoff.render(before, before, filesystem, filesystem_id="computefilesystem-example")
    before["status"]["state"] = "RUNNING"
    with pytest.raises(ValueError, match="stopped"):
        handoff.render(before, before, filesystem, filesystem_id="computefilesystem-example")


def test_other_valid_filesystem_and_stale_restoration_are_rejected(before, filesystem):
    with pytest.raises(ValueError, match="filesystem identity"):
        handoff.render(before, before, filesystem, filesystem_id="computefilesystem-approved-other")
    with pytest.raises(ValueError, match="newer than the baseline"):
        handoff.verify_vm(before, before, filesystem["metadata"]["id"], attached=False)


def test_context_publish_is_immutable_and_safe_to_repeat(tmp_path):
    path = tmp_path / "score.json"
    publisher.immutable_write(path, b"complete signed context")
    publisher.immutable_write(path, b"complete signed context")
    with pytest.raises(ValueError, match="replacement forbidden"):
        publisher.immutable_write(path, b"different context")
    assert path.read_bytes() == b"complete signed context"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["score.json"]


def test_context_symlink_is_never_followed(tmp_path):
    target = tmp_path / "preserved"
    target.write_bytes(b"preserved")
    link = tmp_path / "score.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="replacement forbidden"):
        publisher.immutable_write(link, b"preserved")
    assert target.read_bytes() == b"preserved"


@pytest.mark.parametrize("variant", ["valid", "wrong-tag", "s3", "nested", "duplicate", "read-only"])
def test_native_transport_requires_exact_mount(monkeypatch, tmp_path, variant):
    monkeypatch.setattr(publisher, "MOUNT", tmp_path)
    line = f"41 1 0:30 / {tmp_path} rw - virtiofs {publisher.TAG} rw\n"
    if variant == "wrong-tag":
        line = line.replace(publisher.TAG, "other")
    elif variant == "s3":
        line = line.replace("virtiofs", "fuse.s3fs")
    elif variant == "nested":
        line += f"42 41 0:31 / {tmp_path}/sub rw - tmpfs tmpfs rw\n"
    elif variant == "duplicate":
        line += line
    elif variant == "read-only":
        line = line.replace(" rw", " ro")
    monkeypatch.setattr(publisher.os, "geteuid", lambda: 0)
    monkeypatch.setattr(publisher.Path, "read_text", lambda _: line)
    monkeypatch.setattr(publisher.os, "statvfs", lambda _: SimpleNamespace(f_blocks=10 * 1024**3, f_frsize=1))
    if variant == "valid":
        publisher.check_mount()
    else:
        with pytest.raises(ValueError):
            publisher.check_mount()
