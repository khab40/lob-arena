"""Static signature/mount checks; native execution is deliberately not exercised locally."""
import hashlib
from types import SimpleNamespace

import pytest
pytest.importorskip("cryptography")
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption  # noqa: E402

from serverless.jobs import g8_native_contract as contract, g8_native_runtime as runtime  # noqa: E402
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
    for name in plan_data["files"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reviewed fixture bytes for " + name.encode())
    (root / "reviewer-public.pem").write_bytes(public)
    (root / "filesystem.json").write_bytes(contract.canonical({
        "metadata": {"id": plan_data["filesystem_id"], "parent_id": contract.PROJECT},
        "spec": {"type": "network_ssd", "size_bytes": str(10 * 1024**3)}}))
    (root / "billing.json").write_bytes(contract.canonical({
        "observed_at": plan_data["verified_at"].isoformat(), "campaign_spend_usd": 33.49,
        "lag_allowance_usd": 0.51, "provider_reference": "synthetic-static-billing-fixture"}))
    plan_data["files"] = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                                "size_bytes": (root / name).stat().st_size} for name in plan_data["files"]}
    plan_data["billing_receipt_sha256"] = plan_data["files"]["billing.json"]["sha256"]
    reviewed = contract.NativePlan.model_validate(plan_data)
    raw = contract.canonical(reviewed)
    (root / "native-plan.json").write_bytes(raw)
    (root / "native-plan.sig").write_bytes(key.sign(raw))
    return root, hashlib.sha256(public).hexdigest(), reviewed


def verify(package):
    root, trusted, _ = package
    return runtime.verify_package(root, phase="score", trusted=trusted, now=NOW)


def test_signed_package_and_current_window_required(package):
    assert verify(package).identity() == package[2].identity()
    with pytest.raises(ValueError, match="window"):
        runtime.verify_package(package[0], phase="score", trusted=package[1], now=package[2].expires_at)


@pytest.mark.parametrize("name", ["native-plan.json", "native-plan.sig", "g8_native_lifecycle.py"])
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
    overlay.write_bytes((root / "g8_native_lifecycle.py").read_bytes())
    monkeypatch.setattr(runtime, "injections", lambda _: {str(overlay): "g8_native_lifecycle.py"})
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
    overlay.write_bytes((root / "g8_native_lifecycle.py").read_bytes())
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
