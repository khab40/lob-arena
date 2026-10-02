"""Run approved metadata readiness inside the existing MLflow VM.

An external 600-second VM watchdog must already be armed. This host-side wrapper
caps work plus temporary-container cleanup at 350 seconds. It never starts a VM.
The unbenchmarked maximum restore and live durations cannot both fit this window;
successful restore alone does not authorize starting a live phase without its reserve.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

APP = "lob-arena-mlflow-nebius-mlflow-1"
DB = "lob-arena-mlflow-nebius-mlflow-postgres-1"
INIT = "lob-arena-mlflow-nebius-mlflow-exporter-init-1"
CLIENT = "mlflow-readiness-client-20261002"
URI = "http://10.4.0.54:5500"
CREDENTIAL_KEYS = tuple("MLFLOW_" + role + "_" + suffix
                        for role in ("ADMIN", "WRITER", "EXPORTER")
                        for suffix in ("USERNAME", "PASSWORD"))
TRANSPORT = {"MLFLOW_TRACKING_URI": URI, "MLFLOW_REGISTRY_URI": URI,
             "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0", "MLFLOW_HTTP_REQUEST_TIMEOUT": "10",
             "MLFLOW_ENABLE_ASYNC_LOGGING": "false", "MLFLOW_DISABLE_TELEMETRY": "true",
             "PYTHONDONTWRITEBYTECODE": "1"}
LABEL = "lob-arena.readiness-attempt"
HOST_WORK_SECONDS = 330
RESTORE_ADMISSION_SECONDS = 260
CLIENT_WORK_SECONDS = 180
CLIENT_CLEANUP_SECONDS = 20
PRESERVATION_SECONDS = 20
LIVE_ADMISSION_SECONDS = CLIENT_WORK_SECONDS + CLIENT_CLEANUP_SECONDS + PRESERVATION_SECONDS


@contextmanager
def budget(seconds):
    def expired(*_):
        raise TimeoutError("readiness phase deadline")
    previous, timer, start = signal.getsignal(signal.SIGALRM), signal.getitimer(signal.ITIMER_REAL), time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if timer[0]:
            remaining = timer[0] - (time.monotonic() - start)
            if remaining <= 0:
                raise TimeoutError("outer readiness deadline")
            signal.setitimer(signal.ITIMER_REAL, remaining, timer[1])


def checked_files(directory, manifest, extras=()):
    if directory.stat().st_uid != os.geteuid():
        raise ValueError("staged directory must belong to the current operator")
    actual = set()
    for index, path in enumerate(directory.rglob("*")):
        if index >= 100 or path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("package contains unreviewed paths")
        if path.stat().st_uid != os.geteuid():
            raise ValueError("staged files and directories must belong to the current operator")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(manifest) | set(extras):
        raise ValueError("exact reviewed file set required")
    for name, digest in manifest.items():
        path = directory / name
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or path.stat().st_size > 1024 * 1024
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("reviewed package bytes differ")


def cleanup_client(attempt, call):
    matches = call(["docker", "ps", "-aq", "--no-trunc", "--filter", "name=^/" + CLIENT + "$"])
    if not matches.strip():
        return {"client_absent": True}
    template = '{"id":{{json .Id}},"labels":{{json .Config.Labels}}}'
    observed = json.loads(call(["docker", "inspect", "--format", template, CLIENT]))
    identity = observed.get("id", "")
    if not re.fullmatch(r"[a-f0-9]{64}", identity) or (observed.get("labels") or {}).get(LABEL) != attempt:
        raise ValueError("client cleanup ownership differs; foreign container retained")
    try:
        call(["docker", "rm", "--force", identity])  # Never remove a replacement by name.
    except RuntimeError:
        pass  # --rm may have won the race; absence must still be independently verified.
    if call(["docker", "ps", "-aq", "--filter", "id=" + identity]).strip():
        raise RuntimeError("owned client cleanup unverified")
    return {"client_absent": True, "removed_owned_id": identity}


def client_command(source, inputs, journal, image, proposal_sha, commit, attempt):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("immutable deployed image required")
    return ["docker", "run", "--rm", "--pull", "never", "--name", CLIENT,
            "--label", LABEL + "=" + attempt,
            "--network", "host", "--read-only", "--user", f"{os.geteuid()}:{os.getegid()}", "--cpus", "1",
            "--memory", "512m", "--pids-limit", "128", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:size=64m,mode=1777",
            "-v", f"{source}:/work:ro", "-v", f"{inputs}:/inputs:ro",
            "-v", f"{journal}:/journal:rw", "-e", "PYTHONPATH=/work", "-e", "HOME=/tmp",
            *[part for key in (*CREDENTIAL_KEYS, *TRANSPORT) for part in ("-e", key)],
            "--entrypoint", "python", image, "-B", "/work/deployments/mlflow/readiness_live.py",
            "--input-dir", "/inputs", "--journal", "/journal", "--proposal-sha256", proposal_sha,
            "--source-commit", commit]


def _run(source, inputs, output, env_file, proposal_sha, commit):
    start = time.monotonic()
    deadline = start + HOST_WORK_SECONDS
    def command(args, *, data=None, env=None, timeout=30, phase=None, validate=None):
        remaining = min(timeout, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("readiness deadline")
        try:
            result = subprocess.run(args, input=data, env=env, capture_output=True,
                                    timeout=remaining, check=False)
        except subprocess.TimeoutExpired as error:
            if phase:
                persist(output / (phase + ".json"), {"phase": phase, "status": "timeout"})
            error.readiness_phase = phase
            raise
        semantic_failure = False
        if result.returncode == 0 and validate is not None:
            try:
                semantic_failure = not validate(result.stdout)
            except (ValueError, TypeError, KeyError):
                semantic_failure = True
        if phase:
            receipt = {"phase": phase, "status": "passed" if result.returncode == 0 else "failed",
                       "returncode": result.returncode}
            if semantic_failure:
                receipt.update(status="failed", failed_check="auth_defaults_semantics")
            if result.returncode:
                # Keep fixed identifiers only; stdout/stderr may contain private users/config.
                if phase in {"runtime_preflight", "defaults_before", "defaults_after"}:
                    try:
                        value = json.loads(result.stdout) if len(result.stdout) <= 4096 else {}
                        for key in ("failed_check", "error_type"):
                            item = value.get(key)
                            allowed = DIAGNOSTIC_CHECKS | {"auth_defaults_read"} if key == "failed_check" else {
                                "ValueError", "TypeError", "AttributeError", "KeyError", "ImportError",
                                "ModuleNotFoundError", "PermissionError", "FileNotFoundError", "OSError", "RuntimeError"}
                            if isinstance(item, str) and item in allowed:
                                receipt[key] = item
                    except (ValueError, AttributeError):
                        pass
                match = re.search(rb"(?:ERROR|FATAL):\s+([0-9A-Z]{5})\b", getattr(result, "stderr", b"")[:4096])
                if phase in {"users_before", "users_after"} and match:
                    receipt["sqlstate"] = match.group(1).decode("ascii")
            persist(output / (phase + ".json"), receipt)
        if semantic_failure:
            error = ValueError("unexpected authentication defaults; values redacted")
            error.readiness_phase = phase
            raise error
        if result.returncode:
            error = RuntimeError("readiness subprocess failed; output redacted")
            error.readiness_phase = phase
            raise error
        return result.stdout
    def users(phase):
        return command(database(DB, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1"),
            data=b"\\set VERBOSITY sqlstate\nBEGIN READ ONLY; SELECT row_to_json(t)::text FROM users t ORDER BY id; COMMIT;\n", phase=phase)
    def defaults(phase):
        code = """import configparser,json
try:
    c=configparser.ConfigParser(interpolation=None); c.read('/tmp/mlflow-auth.ini')
    print(json.dumps({k:c['mlflow'][k] for k in ('default_permission','grant_default_workspace_access')}))
except Exception as error:
    print(json.dumps({'failed_check':'auth_defaults_read','error_type':type(error).__name__}))
    raise SystemExit(1) from None
"""
        expected = {"default_permission": "NO_PERMISSIONS", "grant_default_workspace_access": "false"}
        return json.loads(command(["docker", "exec", APP, "python", "-c", code], phase=phase,
                                  validate=lambda raw: json.loads(raw) == expected))
    for path in (source, inputs, output.parent, env_file):
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError("canonical existing paths required")
    if (not sys.dont_write_bytecode or os.environ.get("PYTHONPATH") != str(source)
            or not output.is_absolute() or output.resolve() != output):
        raise ValueError("launch reviewed source with python -B and exact PYTHONPATH")
    env_stat = env_file.stat()
    if (not stat.S_ISREG(env_stat.st_mode) or stat.S_IMODE(env_stat.st_mode) != 0o600
            or env_stat.st_uid != os.geteuid() or env_stat.st_size > 1024 * 1024):
        raise ValueError("owned regular private 0600 env required before mutations")
    if (not re.fullmatch(r"[a-f0-9]{64}", proposal_sha) or not re.fullmatch(r"[a-f0-9]{40}", commit)
            or not (inputs / "proposal.json").is_file() or (inputs / "proposal.json").stat().st_size > 65536):
        raise ValueError("bounded immutable proposal required")
    proposal_raw = (inputs / "proposal.json").read_bytes()
    if hashlib.sha256(proposal_raw).hexdigest() != proposal_sha:
        raise ValueError("proposal anchor mismatch")
    proposal = json.loads(proposal_raw)
    if (proposal["implementation_source_commit"] != commit or proposal["output_directory"] != str(output)
            or proposal["env_file"] != "existing-compose-environment-file"
            or output.is_relative_to(source) or output.is_relative_to(inputs)):
        raise ValueError("source binding mismatch")
    checked_files(source, proposal["package_files_sha256"])
    checked_files(inputs, proposal["input_files_sha256"], ("proposal.json",))
    from scripts.mlflow_readiness_preflight import DIAGNOSTIC_CHECKS
    from deployments.mlflow.readiness_config import append_allowlists, update_allowlists
    from deployments.mlflow.readiness_tracking import persist
    from scripts.mlflow_metadata_recovery import database
    inspected = json.loads(command(["docker", "inspect", APP, INIT]))
    if (len(inspected) != 2 or not inspected[0]["State"]["Running"]
            or inspected[0]["Config"].get("Labels", {}).get("com.docker.compose.project.environment_file") != str(env_file)):
        raise ValueError("existing live application and exact Compose env label required")
    # Validate config before any new container or API mutation, retain only in memory.
    before_env = env_file.read_bytes()
    expected_env = append_allowlists(before_env)
    output.mkdir(mode=0o700, exist_ok=False)
    persist(output / "window-intent.json", {"proposal_sha256": proposal_sha, "source_commit": commit})
    before_users = users("users_before")
    before_defaults = defaults("defaults_before")
    if before_defaults != {"default_permission": "NO_PERMISSIONS",
                           "grant_default_workspace_access": "false"}:
        raise ValueError("unexpected live authentication defaults")
    image = inspected[0]["Image"]
    runtime = json.loads(command(["docker", "exec", "-i", *[part for key, value in TRANSPORT.items()
        for part in ("-e", key + "=" + value)], APP, "python", "-B", "-"],
        data=(source / "scripts/mlflow_readiness_preflight.py").read_bytes(), phase="runtime_preflight"))
    if runtime.get("status") != "verified" or runtime.get("mlflow_version") != "3.13.0":
        raise ValueError("deployed runtime preflight failed")
    values = dict(entry.split("=", 1) for entry in inspected[1]["Config"]["Env"])
    if any(not values.get(k) for k in CREDENTIAL_KEYS):
        raise ValueError("existing service credentials required")
    client_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **TRANSPORT,
                  **{k: values[k] for k in CREDENTIAL_KEYS}}
    journal = output / "live"
    journal.mkdir(mode=0o700)
    # Restore completes before the live phase; it owns its two temporary containers.
    if deadline - time.monotonic() < RESTORE_ADMISSION_SECONDS:
        raise TimeoutError("insufficient bounded restore and cleanup reserve")
    command([sys.executable, "-B", str(source / "scripts/mlflow_application_restore.py"),
             "--source-root", str(source), "--output", str(output / "restore"),
             "--expected-receipt", str(inputs / "restore-receipt.json")], timeout=250)
    cleanup = json.loads((output / "restore/cleanup.json").read_bytes())
    restored = json.loads((output / "restore/application-receipt.json").read_bytes())
    expected_restore = json.loads((inputs / "restore-receipt.json").read_bytes())
    if (cleanup.get("failed") != [] or len(cleanup.get("attempted", [])) != 2
            or restored.get("status") != "verified" or restored.get("runtime_version") != "3.13.0"
            or restored.get("network_mode") != "none" or restored.get("startup_preserved_all_tables") is not True
            or restored.get("backup_sha256") != expected_restore["backup_sha256"]
            or restored.get("images") != [expected_restore["postgres_image_id"], image]):
        raise ValueError("restored application or cleanup receipt incomplete")
    if json.loads(command(["docker", "inspect", APP]))[0]["Image"] != image:
        raise ValueError("deployed image changed during restore")
    # Refuse a pre-existing container rather than removing another attempt's work.
    matches = command(["docker", "ps", "-aq", "--filter", "name=^/" + CLIENT + "$"])
    if matches.strip():
        raise ValueError("client container name is already in use")
    if deadline - time.monotonic() < LIVE_ADMISSION_SECONDS:
        raise TimeoutError("insufficient live, cleanup and preservation reserve after restore")
    attempted = False
    attempt = hashlib.sha256((proposal_sha + "\n" + str(output)).encode()).hexdigest()
    try:
        attempted = True
        command(client_command(source, inputs, journal, image, proposal_sha, commit, attempt),
                env=client_env, timeout=CLIENT_WORK_SECONDS)
    finally:
        if attempted:
            def cleanup_call(args):
                result = subprocess.run(args, capture_output=True, timeout=5, check=False)
                if result.returncode:
                    raise RuntimeError("client cleanup subprocess failed; output redacted")
                return result.stdout
            with budget(CLIENT_CLEANUP_SECONDS):
                persist(output / "client-cleanup.json", cleanup_client(attempt, cleanup_call))
    if users("users_after") != before_users or defaults("defaults_after") != before_defaults:
        raise ValueError("live credentials, identities or defaults changed")
    if env_file.read_bytes() != before_env:
        raise ValueError("live env changed concurrently")
    live_raw = (journal / "live-receipt.json").read_bytes()
    live = json.loads(live_raw)
    if (live.get("schema_version") != "mlflow_live_readiness_phase_v1" or live.get("binding") != {
            "proposal_sha256": proposal_sha, "source_commit": commit, "purpose": "mlflow-readiness-20261002"}):
        raise ValueError("live phase receipt binding differs")
    config = update_allowlists(env_file)
    if env_file.read_bytes() != expected_env:
        raise ValueError("allowlist readback differs")
    receipt = {"status": "application_verified_pending_independent_readback_and_vm_stop",
               "source_commit": commit, "proposal_sha256": proposal_sha, "image_id": image,
               "live_users_and_credentials_unchanged": True, "defaults_unchanged": True,
               "allowlists": config, "runtime": runtime, "seconds": time.monotonic() - start,
               "live_receipt_sha256": hashlib.sha256(live_raw).hexdigest(),
               "model_jobs": 0, "final_access": False}
    persist(output / "application-receipt.json", receipt)
    return receipt


def run(source, inputs, output, env_file, proposal_sha, commit):
    with budget(HOST_WORK_SECONDS):
        return _run(source, inputs, output, env_file, proposal_sha, commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "inputs", "output", "env-file"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    try:
        run(args.source, args.inputs, args.output, args.env_file,
            args.proposal_sha256, args.source_commit)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "phase": getattr(exc, "readiness_phase", None)}), flush=True)
        raise SystemExit(1) from None
    print("Application checks completed; independent readback and VM stop still required.")
