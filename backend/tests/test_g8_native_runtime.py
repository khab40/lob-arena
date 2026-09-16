"""Static signature/mount checks; native execution is deliberately not exercised locally."""
import hashlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
pytest.importorskip("cryptography")
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption  # noqa: E402

from serverless.jobs import g8_native_contract as contract, g8_native_runtime as runtime  # noqa: E402
from serverless.jobs.g8_native_archive import build, read_code  # noqa: E402
import test_g8_native_readback as fixtures  # noqa: E402
from serverless.jobs import run_g8_native_rehearsal as entrypoint  # noqa: E402

NOW = fixtures.NOW
plan_data, plan = fixtures.plan_data, fixtures.plan


@pytest.fixture
def package(tmp_path, plan_data, monkeypatch):
    # Capsule byte integrity has its own tests. This fixture targets package
    # signing and file binding, using no synthetic model/data generation.
    monkeypatch.setattr(runtime, "verify_capsule", lambda _: None)
    root = tmp_path / "package"
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "reviewer.pem"
    private.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    private.chmod(0o600)
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    code = {name: b"reviewed fixture bytes for " + name.encode() for name in contract.CODE_PATHS}
    for name in set(plan_data["files"]) - set(contract.CODE_PATHS):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reviewed fixture bytes for " + name.encode())
    for name, content in build(code).items():
        (root / name).write_bytes(content)
    (root / "reviewer-public.pem").write_bytes(public)
    (root / "filesystem.json").write_bytes(contract.canonical({
        "metadata": {"id": plan_data["filesystem_id"], "parent_id": contract.PROJECT},
        "spec": {"type": "NETWORK_SSD", "size_gibibytes": "10"},
        "status": {"state": "READY", "size_bytes": str(10 * 1024**3)}}))
    contents = {name: read_code(root, name) if name in contract.CODE_PATHS else (root / name).read_bytes()
                for name in plan_data["files"]}
    plan_data["files"] = {name: {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                          for name, raw in contents.items()}
    reviewed = contract.NativePlan.model_validate(plan_data)
    raw = contract.canonical(reviewed)
    (root / "native-plan.json").write_bytes(raw)
    (root / "native-plan.sig").write_bytes(key.sign(raw))
    return root, hashlib.sha256(public).hexdigest(), reviewed


def verify(package):
    root, trusted, _ = package
    return runtime.verify_package(root, phase="score", trusted=trusted, now=NOW)


@pytest.mark.parametrize("phase", ["score", "recover"])
def test_signed_package_survives_approval_delay_without_billing(package, phase):
    root, trusted, plan = package
    assert not (root / "billing.json").exists()
    assert runtime.verify_package(root, phase=phase, trusted=trusted,
                                  now=NOW + timedelta(days=7)).identity() == plan.identity()
    with pytest.raises(ValueError, match="future"):
        runtime.verify_package(root, phase=phase, trusted=trusted, now=plan.verified_at - timedelta(seconds=1))
    (root / "native-code-0.zip").write_bytes(b"tampered after waiting")
    with pytest.raises(ValueError):
        runtime.verify_package(root, phase=phase, trusted=trusted, now=NOW + timedelta(days=7))


def test_operator_alerts_do_not_require_repeated_billing_refresh(package):
    assert verify(package).spend_monitoring == "operator_managed_alerts"


@pytest.mark.parametrize("unit,amount", [("size_bytes", 10 * 1024**3), ("size_kibibytes", 10 * 1024**2),
                                       ("size_mebibytes", 10240), ("size_gibibytes", "10")])
def test_filesystem_accepts_api_size_oneof(package, unit, amount):
    import json
    filesystem = json.loads((package[0] / "filesystem.json").read_bytes())
    filesystem["spec"] = {"type": "NETWORK_SSD", unit: amount}
    runtime.verify_filesystem(filesystem, package[2].filesystem_id)


@pytest.mark.parametrize("section,key,value", [
    ("spec", "type", "NETWORK_HDD"), ("spec", "type", "network_ssd"),
    ("spec", "size_gibibytes", 100), ("spec", "size_gibibytes", True), ("spec", "size_gibibytes", 10.0),
    ("spec", "size_bytes", 10 * 1024**3), ("status", "state", "CREATING"),
    ("status", "size_bytes", "0"), ("status", "reconciling", True),
])
def test_filesystem_rejects_unready_or_ambiguous_capacity(package, section, key, value):
    import json
    filesystem = json.loads((package[0] / "filesystem.json").read_bytes())
    filesystem[section][key] = value
    with pytest.raises(ValueError, match="filesystem"):
        runtime.verify_filesystem(filesystem, package[2].filesystem_id)


@pytest.mark.parametrize("name", ["native-plan.json", "native-plan.sig", "native-code-0.zip", "g8_native_bootstrap.py"])
def test_signed_or_injected_bytes_cannot_change(package, name):
    path = package[0] / name
    content = path.read_bytes()
    path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    with pytest.raises((ValueError, InvalidSignature)):
        verify(package)


def test_untrusted_key_or_unreviewed_file_rejected(package):
    with pytest.raises(ValueError, match="trust anchor"):
        runtime.verify_package(package[0], phase="score", trusted="f" * 64, now=NOW)
    (package[0] / "unreviewed.py").write_bytes(b"no")
    with pytest.raises(ValueError, match="unexpected"):
        verify(package)


def test_runtime_rechecks_the_actual_overlay_and_environment(package, monkeypatch, tmp_path):
    root, _, plan = package
    overlay = tmp_path / "actual-overlay.py"
    overlay.write_bytes((root / "native-code-0.zip").read_bytes())
    monkeypatch.setattr(runtime, "injections", lambda _: {str(overlay): "native-code-0.zip"})
    monkeypatch.setattr(runtime.os, "statvfs", lambda _: SimpleNamespace(f_flag=runtime.os.ST_RDONLY))
    for key, value in contract.environment(plan).items():
        monkeypatch.setenv(key, value)
    for key in plan.secret_selectors:
        monkeypatch.setenv(key, "synthetic-not-a-credential")
    for key in ("AWS_SESSION_TOKEN", "AWS_PROFILE", "MLFLOW_TRACKING_TOKEN", "MLFLOW_ALLOW_FILE_STORE"):
        monkeypatch.delenv(key, raising=False)
    assert runtime.actual_runtime(plan, root)["injected_file_bytes_verified"]
    overlay.write_bytes(b"old runtime")
    with pytest.raises(ValueError, match="reviewed bytes"):
        runtime.actual_runtime(plan, root)
    overlay.write_bytes((root / "native-code-0.zip").read_bytes())
    monkeypatch.setattr(runtime.os, "statvfs", lambda _: SimpleNamespace(f_flag=0))
    with pytest.raises(ValueError, match="read-only"):
        runtime.actual_runtime(plan, root)


def test_native_mount_requires_writable_virtiofs_without_nested_mounts(plan):
    text = "41 1 0:30 / /g8-durable rw,relatime - virtiofs fs0 rw\n"
    observed = runtime.native_mount(plan, text)
    assert observed["filesystem_id"] == plan.filesystem_id
    for changed in (text.replace("virtiofs", "fuse.s3fs"), text.replace("rw,relatime", "ro,relatime"),
                    text + "42 41 0:31 / /g8-durable/sub rw - tmpfs tmpfs rw\n", text + text):
        with pytest.raises(ValueError):
            runtime.native_mount(plan, changed)


def test_recovery_workers_share_deadline_including_preflight(monkeypatch):
    clock = iter((600, 1500))  # Preflight and the interrupted worker consume time.
    calls = []
    monkeypatch.setattr(entrypoint.time, "monotonic", lambda: next(clock))

    def child(command, *, check, timeout):
        calls.append((command[-1], timeout))
        return SimpleNamespace(returncode=74 if command[-1] == "artifact-loss" else 0)

    monkeypatch.setattr(entrypoint.subprocess, "run", child)
    entrypoint.recovery_workers(3300)
    assert calls == [("artifact-loss", 900), ("finish", 1800)]


@pytest.mark.parametrize("clock_values", [(3300,), (3200, 3301)])
def test_expired_budget_does_not_start_another_worker(monkeypatch, clock_values):
    clock = iter(clock_values)
    calls = []
    monkeypatch.setattr(entrypoint.time, "monotonic", lambda: next(clock))

    def child(command, *, check, timeout):
        calls.append((command[-1], timeout))
        return SimpleNamespace(returncode=74)

    monkeypatch.setattr(entrypoint.subprocess, "run", child)
    with pytest.raises(TimeoutError, match="budget exhausted"):
        entrypoint.recovery_workers(3300)
    assert calls == ([] if len(clock_values) == 1 else [("artifact-loss", 100)])
