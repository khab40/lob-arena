"""Native pre-access gates. No cloud calls, dataset loading, or model execution."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from .g8_native_contract import CODE_PATHS, MAX_INJECTION, NativePlan, canonical, environment, injections
    from .g8_native_archive import read_code
    from .g8_native_readback import verify_readback, verify_previous_job, verify_registry
    from .g8_native_source_capsule import verify as verify_capsule
else:
    from g8_native_contract import CODE_PATHS, MAX_INJECTION, NativePlan, canonical, environment, injections
    from g8_native_archive import read_code
    from g8_native_readback import verify_readback, verify_previous_job, verify_registry
    from g8_native_source_capsule import verify as verify_capsule


def bounded(path, maximum=65536):
    if path.absolute() != path.resolve() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("bounded canonical regular file required: " + path.name)
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise ValueError("file grew beyond its bound")
    return raw


def signed(raw, signature, public, trusted):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if hashlib.sha256(public).hexdigest() != trusted:
        raise ValueError("reviewer key differs from injected trust anchor")
    key = load_pem_public_key(public)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Ed25519 reviewer required")
    key.verify(signature, raw)


def verify_filesystem(filesystem, expected_id):
    """Validate the unmodified Compute API enum, size oneof and ready capacity."""
    spec, status = filesystem["spec"], filesystem["status"]
    units = {"size_bytes": 1, "size_kibibytes": 1024, "size_mebibytes": 1024**2, "size_gibibytes": 1024**3}
    sizes = [(spec[k], factor) for k, factor in units.items() if k in spec]
    if len(sizes) != 1:
        raise ValueError("filesystem must carry exactly one configured size")
    value, factor = sizes[0]
    if (type(value) not in (int, str) or not str(value).isdigit()
            or int(value) * factor != 10 * 1024**3
            or filesystem["metadata"]["id"] != expected_id
            or filesystem["metadata"]["parent_id"] != "project-e00g6zvxpr00waz8t3y51k"
            or spec.get("type") != "NETWORK_SSD" or status.get("state") != "READY"
            or status.get("reconciling", False) is not False
            or status.get("size_bytes") not in (10 * 1024**3, str(10 * 1024**3))):
        raise ValueError("filesystem identity, type or ready 10 GiB capacity differs")


def verify_package(package, *, phase, trusted, now=None):
    raw = bounded(package / "native-plan.json", MAX_INJECTION)
    signed(raw, bounded(package / "native-plan.sig", 64), bounded(package / "reviewer-public.pem"), trusted)
    plan = NativePlan.model_validate_json(raw)
    if raw != canonical(plan):
        raise ValueError("canonical signed plan required")
    expected = (set(plan.files) - set(CODE_PATHS)) | {"native-plan.json", "native-plan.sig"}
    if any(p.is_symlink() for p in package.rglob("*")) or {
        p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()
    } != expected:
        raise ValueError("package has missing, linked or unexpected files")
    # Authenticate archive bytes before interpreting member metadata/content.
    for name in sorted(plan.files, key=lambda name: name in CODE_PATHS):
        ref = plan.files[name]
        content = read_code(package, name) if name in CODE_PATHS else bounded(package / name, MAX_INJECTION)
        if len(content) != ref.size_bytes or hashlib.sha256(content).hexdigest() != ref.sha256:
            raise ValueError("package bytes differ: " + name)
    verify_capsule(package / "source-capsule")
    filesystem = json.loads(bounded(package / "filesystem.json"))
    verify_filesystem(filesystem, plan.filesystem_id)
    current = now or datetime.now(UTC)
    if phase not in {"score", "recover"} or plan.verified_at > current:
        raise ValueError("invalid native phase or future verification timestamp")
    return plan


def native_mount(plan, mountinfo=None):
    lines = (Path("/proc/self/mountinfo").read_text() if mountinfo is None else mountinfo).splitlines()
    found = []
    for line in lines:
        before, after = line.split(" - ", 1)
        fields, fs = before.split(), after.split()
        if fields[4].startswith(plan.mount_path + "/"):
            raise ValueError("nested durable mounts are forbidden")
        if fields[4] == plan.mount_path:
            if fs[0] != "virtiofs" or "rw" not in fields[5].split(",") or "rw" not in fs[2].split(","):
                raise ValueError("writable native virtiofs required")
            found.append({"kernel_identity": fields[:4], "source": fs[1], "type": fs[0]})
    if len(found) != 1:
        raise ValueError("exactly one durable native mount required")
    return {"filesystem_id": plan.filesystem_id, **found[0]}


def actual_runtime(plan, package):
    for path, name in injections(plan).items():
        path = Path(path)
        if bounded(path) != bounded(package / name) or not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError("runtime injection must match reviewed bytes and be read-only: " + name)
    for key, value in environment(plan).items():
        if os.environ.get(key) != value:
            raise ValueError("actual Job environment differs: " + key)
    if any(not os.environ.get(k) for k in plan.secret_selectors):
        raise ValueError("required Job credentials missing")
    if any(os.environ.get(k) for k in ("AWS_SESSION_TOKEN", "AWS_PROFILE", "MLFLOW_TRACKING_TOKEN", "MLFLOW_ALLOW_FILE_STORE")):
        raise ValueError("unreviewed credential or tracking fallback")
    return {"injected_file_bytes_verified": True, "runtime_environment_verified": True}


def observed_context(plan, package, *, phase, trusted):
    """Operator stages signed normal API readback on the approved native mount."""
    path = Path(plan.mount_path) / "contexts" / (phase + ".json")
    sig = path.with_suffix(".sig")
    deadline = time.monotonic() + 300
    while not (path.is_file() and sig.is_file()):
        if time.monotonic() >= deadline:
            raise ValueError("signed native Job context unavailable before deadline")
        time.sleep(1)
    raw = bounded(path)
    signature = bounded(sig, 64)
    public = bounded(package / "reviewer-public.pem")
    signed(raw, signature, public, trusted)
    context = json.loads(raw)
    if (raw != canonical(context)
            or set(context) != {"execution_package_sha256", "phase", "job_id", "readback", "previous_terminal", "registry_verification"}
            or context["execution_package_sha256"] != plan.identity() or context["phase"] != phase):
        raise ValueError("signed native Job context differs from package/phase")
    receipt = verify_readback(plan, context["readback"], phase=phase, expected_job_id=context["job_id"])
    # The signer requires a fresh lookup after create; recovery children reuse
    # that signed observation during recovery, without a new lookup.
    verify_registry(context["registry_verification"], created_at=context["readback"]["metadata"]["created_at"], fresh=False)
    if phase == "score" and context["previous_terminal"] is not None:
        raise ValueError("score context cannot carry another Job")
    if phase == "recover":
        original_path = Path(plan.mount_path) / "native-evidence/score-context.json"
        original_raw = bounded(original_path)
        signed(original_raw, bounded(original_path.with_suffix(".sig"), 64), public, trusted)
        original = json.loads(original_raw)
        verify_previous_job(plan, original, context["previous_terminal"], recovery_job_id=context["job_id"])
    return context, receipt, signature
