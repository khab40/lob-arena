"""Run approved metadata readiness inside the existing MLflow VM.

An external 600-second VM watchdog must already be armed. This host-side wrapper
caps work plus temporary-container cleanup at 420 seconds. It never starts a VM.
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
    actual = set()
    for index, path in enumerate(directory.rglob("*")):
        if index >= 100 or path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("package contains unreviewed paths")
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
            "--network", "host", "--read-only", "--user", "0:0", "--cpus", "1",
            "--memory", "512m", "--pids-limit", "128", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:size=64m,mode=1777",
            "-v", f"{source}:/work:ro", "-v", f"{inputs}:/inputs:ro",
            "-v", f"{journal}:/journal:rw", "-e", "PYTHONPATH=/work",
            *[part for key in (*CREDENTIAL_KEYS, *TRANSPORT) for part in ("-e", key)],
            "--entrypoint", "python", image, "-B", "/work/deployments/mlflow/readiness_live.py",
            "--input-dir", "/inputs", "--journal", "/journal", "--proposal-sha256", proposal_sha,
            "--source-commit", commit]
