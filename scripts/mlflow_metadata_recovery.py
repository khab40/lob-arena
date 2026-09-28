"""Retain a private PostgreSQL dump and verify an isolated metadata restore.

Run on the MLflow VM under the operator's bounded maintenance window.
Never prints database contents, credentials, or subprocess error output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import select
import subprocess
import time
import uuid


def command(args, *, data=None, output=subprocess.PIPE, timeout=90):
    result = subprocess.run(args, input=data, stdout=output, stderr=subprocess.DEVNULL,
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"Recovery command failed (exit {result.returncode}); output redacted")
    return result.stdout


def database(container, program, *args):
    return ["docker", "exec", "-i", container, "sh", "-c",
            'exec "$@" -U "$POSTGRES_USER" -d "$POSTGRES_DB"', "sh", program, *args]


def sql(container, query, snapshot=None):
    prefix = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
    if snapshot:
        if not re.fullmatch(r"[0-9A-Fa-f-]+", snapshot):
            raise ValueError("Invalid snapshot identifier")
        prefix += f"SET TRANSACTION SNAPSHOT '{snapshot}';\n"
    return command(database(container, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1"),
                   data=(prefix + query + "\nCOMMIT;\n").encode())


def inventory(container, snapshot=None):
    tables = json.loads(sql(container, """
SELECT coalesce(json_agg(tablename ORDER BY tablename), '[]')
FROM pg_tables WHERE schemaname='public';
""", snapshot))
    if not {"runs", "experiments", "registered_models", "users"} <= set(tables):
        raise ValueError("Missing MLflow tracking, registry or authentication tables")
    result = {}
    for table in tables:
        identifier = '"' + table.replace('"', '""') + '"'
        # JSON escapes embedded newlines; one sorted COPY line per logical row.
        rows = sql(container, f"""COPY (
SELECT row_to_json(t)::text FROM public.{identifier} t
ORDER BY row_to_json(t)::text COLLATE "C") TO STDOUT;""", snapshot)
        result[table] = {"rows": rows.count(b"\n"), "sha256": hashlib.sha256(rows).hexdigest()}
    return result


def compare(source, restored):
    if not source or source != restored:
        raise ValueError("Restored table inventory or contents differ from the backup snapshot")


def dump_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**3, 1024**3))


def recover(source, directory):
    if directory.is_symlink() or directory.absolute() != directory.resolve():
        raise ValueError("Canonical private output directory required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    image = command(["docker", "inspect", "--format", "{{.Image}}", source]).decode().strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("Immutable source image ID required")
    session = subprocess.Popen(database(source, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1"),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    target = "mlflow-restore-" + uuid.uuid4().hex
    started = False
    try:
        session.stdin.write(b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
                            b"SELECT pg_export_snapshot();\n")
        session.stdin.flush()
        if not select.select([session.stdout], [], [], 30)[0]:
            raise TimeoutError("Snapshot export timed out")
        snapshot = session.stdout.readline().decode().strip()
        if not re.fullmatch(r"[0-9A-Fa-f-]+", snapshot):
            raise ValueError("Snapshot export failed")
        before = inventory(source, snapshot)
        backup = directory / "metadata.dump"
        with backup.open("xb") as stream:
            os.chmod(backup, 0o600)
            result = subprocess.run(database(source, "pg_dump", "--format=custom",
                                            "--snapshot=" + snapshot), stdout=stream,
                                    stderr=subprocess.DEVNULL, timeout=120,
                                    preexec_fn=dump_limit, check=False)
        if result.returncode or not backup.stat().st_size:
            raise RuntimeError("Metadata dump failed; no recovery claim")
        session.stdin.write(b"ROLLBACK;\n\\q\n")
        session.stdin.flush()
        session.wait(timeout=10)
        command(["docker", "run", "--detach", "--rm", "--name", target,
                 "--network", "none", "--memory", "1g", "--cpus", "1", "--pids-limit", "128",
                 "--tmpfs", "/var/lib/postgresql/data:rw,size=536870912",
                 "--tmpfs", "/var/run/postgresql:rw,size=16777216",
                 "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_USER=mlflow",
                 "-e", "POSTGRES_DB=mlflow", image], timeout=30)
        started = True
        for attempt in range(30):
            try:
                if sql(target, "SELECT 1;").strip() == b"1":
                    break
            except RuntimeError:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("Isolated PostgreSQL did not become ready")
        with backup.open("rb") as stream:
            result = subprocess.run(database(target, "pg_restore", "--single-transaction",
                                            "--exit-on-error", "--no-owner", "--no-privileges"),
                                    stdin=stream, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=120, check=False)
        if result.returncode:
            raise RuntimeError("Restore failed; no recovery claim")
        restored = inventory(target)
        compare(before, restored)
        with backup.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        receipt = {"schema_version": 1, "status": "verified", "source_container": source,
                   "postgres_image_id": image, "restore_container": target,
                   "backup_sha256": digest, "backup_bytes": backup.stat().st_size,
                   "tables": restored, "scope": "public_table_data_including_mlflow_auth",
                   "model_jobs": 0, "production_database_replaced": False}
    finally:
        if session.poll() is None:
            session.terminate()
            session.wait(timeout=10)
        if started:
            command(["docker", "stop", "--time", "10", target], timeout=20)
    receipt["restore_container_stopped"] = True
    (directory / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-container", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    recover(args.source_container, args.output)
    print("Metadata recovery verified; private backup and redacted receipt retained.")
