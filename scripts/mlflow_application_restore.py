"""Execute the approved metadata-only restore probe on the existing MLflow VM.

Requires the operator's outer 600-second VM watchdog; this probe is capped at
240 seconds including cleanup. Never run on a developer
machine. Credentials remain in process memory and the isolated app's tmpfs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

import mlflow_metadata_recovery as recovery

BACKUP_SHA256 = "a5272943981769a1c0c62ca6021f50f2d92049fc894c4879e0f3d3ba88aba110"
BACKUP = Path("/opt/aimada/mlflow/recovery-20260928/metadata.dump")
SOURCE_DB = "lob-arena-mlflow-nebius-mlflow-postgres-1"
SOURCE_APP = "lob-arena-mlflow-nebius-mlflow-1"
FROZEN_RUN = "1bd94569914748db8bbde21b13e83d05"
RECEIVE = """import os,sys; p='/tmp/context.part'; b=sys.stdin.buffer.read(65537)
assert len(b)<=65536
f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(f,'wb') as h: h.write(b); h.flush(); os.fsync(h.fileno())
os.rename(p,'/tmp/context.json')
"""
BOOT = """import configparser,json,os,time
from pathlib import Path
p=Path('/tmp/context.json')
for _ in range(300):
    if p.exists(): break
    time.sleep(.1)
else: raise RuntimeError('private context missing')
v=json.loads(p.read_text()); os.environ.clear()
os.environ.update(PATH='/usr/local/bin:/usr/bin:/bin',HOME='/tmp',
 MLFLOW_FLASK_SERVER_SECRET_KEY=v['MLFLOW_FLASK_SERVER_SECRET_KEY'],
 MLFLOW_AUTH_CONFIG_PATH='/tmp/mlflow-auth.ini',MLFLOW_ENABLE_WORKSPACES='false',
 MLFLOW_TRACKING_INSECURE_TLS='false',MLFLOW_DISABLE_TELEMETRY='true')
uri='postgresql+psycopg2://mlflow@/mlflow?host=/restore-socket'
c=configparser.ConfigParser(interpolation=None)
c['mlflow']={'database_uri':uri,'default_permission':'NO_PERMISSIONS',
 'grant_default_workspace_access':'false','admin_username':v['MLFLOW_ADMIN_USERNAME'],
 'admin_password':v['MLFLOW_ADMIN_PASSWORD'],
 'authorization_function':'mlflow.server.auth:authenticate_request_basic_auth'}
with open('/tmp/mlflow-auth.ini','x') as f: os.chmod(f.name,0o600); c.write(f)
os.execvp('mlflow',['mlflow','server','--host','0.0.0.0','--port','5000',
 '--workers','1','--backend-store-uri',uri,'--no-serve-artifacts',
 '--default-artifact-root','file:///restore-readiness/inert-metadata-only',
 '--allowed-hosts','mlflow-restored:5000,127.0.0.1:5000,localhost:5000',
 '--app-name','basic-auth'])
"""
PROBE = """import configparser,json,os,sys,secrets
baseline=json.load(sys.stdin); os.environ.clear()
os.environ.update(PATH='/usr/local/bin:/usr/bin:/bin',HOME='/tmp',
 MLFLOW_HTTP_REQUEST_MAX_RETRIES='0',MLFLOW_HTTP_REQUEST_TIMEOUT='10',
 MLFLOW_ENABLE_ASYNC_LOGGING='false',MLFLOW_DISABLE_TELEMETRY='true')
c=configparser.ConfigParser(interpolation=None); c.read('/tmp/mlflow-auth.ini')
os.environ['MLFLOW_TRACKING_USERNAME']=c['mlflow']['admin_username']
os.environ['MLFLOW_TRACKING_PASSWORD']=c['mlflow']['admin_password']
import mlflow
from mlflow import MlflowClient
from mlflow.server.auth.client import AuthServiceClient
sys.path.insert(0,'/reviewed-helper')
from readiness_recovery import RESTORED_URI,verify_application
assert mlflow.__version__=='3.13.0' and mlflow.get_active_model_id() is None
client=MlflowClient(tracking_uri=RESTORED_URI,registry_uri=RESTORED_URI)
result=verify_application(client,AuthServiceClient(RESTORED_URI),baseline,
 admin_username=c['mlflow']['admin_username'],probe_password=secrets.token_urlsafe(32))
print(json.dumps(result,sort_keys=True))
"""
PREFLIGHT = """import inspect,mlflow,psycopg2
from mlflow import MlflowClient
from mlflow.server.auth.client import AuthServiceClient
from mlflow.cli import server
assert mlflow.__version__=='3.13.0'
for method in (MlflowClient.log_param,MlflowClient.log_metric,MlflowClient.set_tag):
 assert 'synchronous' in inspect.signature(method).parameters
flags={o for p in server.params for o in (*p.opts,*p.secondary_opts)}
assert {'--no-serve-artifacts','--allowed-hosts','--app-name','--default-artifact-root'}<=flags
assert AuthServiceClient('http://mlflow-restored:5000').tracking_uri=='http://mlflow-restored:5000'
print('runtime-compatible')
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def record(path, value):
    with path.open("x", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def baseline(container):
    query = f"""SELECT json_build_object(
 'experiment_max_id',(SELECT max(experiment_id) FROM experiments),
 'user_max_id',(SELECT max(id) FROM users), 'frozen_run',json_build_object(
 'run_id',r.run_uuid,'experiment_id',r.experiment_id::text,'status',r.status,
 'params',coalesce((SELECT json_object_agg(key,value) FROM params WHERE run_uuid=r.run_uuid),'{{}}'),
 'metrics',coalesce((SELECT json_object_agg(key,value) FROM latest_metrics WHERE run_uuid=r.run_uuid),'{{}}'),
 'tags',coalesce((SELECT json_object_agg(key,value) FROM tags WHERE run_uuid=r.run_uuid),'{{}}')))
 FROM runs r WHERE run_uuid='{FROZEN_RUN}';"""
    return {"backup_sha256": BACKUP_SHA256, **json.loads(recovery.sql(container, query))}


def run(directory, receipt, helper, *, backup=BACKUP, source_db=SOURCE_DB, source_app=SOURCE_APP):
    """One attempt; cleanup is limited to this attempt's two named containers."""
    require(directory.absolute() == directory.resolve() and not directory.is_symlink(),
            "canonical new private directory required")
    require(backup.is_file() and not backup.is_symlink() and backup.stat().st_size == 380475,
            "retained backup size or path differs")
    require(hashlib.sha256(backup.read_bytes()).hexdigest() == BACKUP_SHA256, "backup digest differs")
    require(receipt["backup_sha256"] == BACKUP_SHA256 and len(receipt["tables"]) == 60,
            "retained receipt differs")
    require(helper.name == "readiness_recovery.py" and helper.is_file(), "reviewed helper required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    original_command = recovery.command
    deadline = time.monotonic() + 210
    cleanup = False
    def bounded(args, **kwargs):
        remaining = deadline + (30 if cleanup else 0) - time.monotonic()
        require(remaining > 0, "restore deadline exceeded")
        kwargs["timeout"] = min(kwargs.get("timeout", 90), 5 if cleanup else remaining, remaining)
        return original_command(args, **kwargs)
    recovery.command = bounded
    attempt_id = uuid.uuid4().hex
    names = ["mlflow-app-restore-db-" + attempt_id, "mlflow-app-restore-app-" + attempt_id]
    attempted = []
    try:
        info = [json.loads(bounded(["docker", "inspect", name]))[0] for name in (source_db, source_app)]
        images = [item["Image"] for item in info]
        require(all(re.fullmatch(r"sha256:[a-f0-9]{64}", image) for image in images), "immutable image IDs required")
        require(images[0] == receipt["postgres_image_id"], "backup PostgreSQL image differs")
        require(bounded(["docker", "exec", source_app, "python", "-c", PREFLIGHT]).strip()
                == b"runtime-compatible", "deployed runtime preflight failed")
        live_env = dict(item.split("=", 1) for item in info[1]["Config"]["Env"])
        private = {key: live_env[key] for key in (
            "MLFLOW_ADMIN_USERNAME", "MLFLOW_ADMIN_PASSWORD", "MLFLOW_FLASK_SERVER_SECRET_KEY")}
        require(len(private["MLFLOW_ADMIN_PASSWORD"]) >= 16 and len(private["MLFLOW_FLASK_SERVER_SECRET_KEY"]) >= 32,
                "existing authentication configuration incomplete")
        socket = directory / "socket"
        socket.mkdir(mode=0o777)
        socket.chmod(0o777)  # Parent is 0700; PostgreSQL's UID needs this mounted socket directory.
        record(directory / "attempt.json", {"containers": names, "images": images,
               "backup_sha256": BACKUP_SHA256, "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest()})
        common = ["docker", "run", "--detach", "--pull", "never", "--network", "none",
                  "--label", "lob-arena.restore-attempt=" + attempt_id,
                  "--cpus", "1", "--pids-limit", "128", "--security-opt", "no-new-privileges:true"]
        attempted.append(names[0])
        bounded([*common, "--name", names[0], "--memory", "1g", "--tmpfs",
                 "/var/lib/postgresql/data:rw,size=536870912", "--mount",
                 f"type=bind,src={socket},dst=/var/run/postgresql", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                 "-e", "POSTGRES_USER=mlflow", "-e", "POSTGRES_DB=mlflow", images[0]], timeout=30)
        for _ in range(30):
            try:
                if recovery.sql(names[0], "SELECT 1;").strip() == b"1":
                    break
            except RuntimeError:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("isolated database not ready")
        bounded(recovery.database(names[0], "pg_restore", "--single-transaction", "--exit-on-error",
                                  "--no-owner", "--no-privileges"), data=backup.read_bytes(), timeout=120)
        recovery.compare(receipt["tables"], recovery.inventory(names[0]))
        before = baseline(names[0])
        attempted.append(names[1])
        bounded([*common, "--name", names[1], "--memory", "2g", "--user", "0:0", "--read-only", "--cap-drop", "ALL",
                 "--tmpfs", "/tmp:rw,size=268435456,mode=1777", "--add-host", "mlflow-restored:127.0.0.1",
                 "--mount", f"type=bind,src={socket},dst=/restore-socket,readonly",
                 "--mount", f"type=bind,src={helper.parent.resolve()},dst=/reviewed-helper,readonly",
                 "--entrypoint", "python", images[1], "-c", BOOT], timeout=30)
        bounded(["docker", "exec", "-i", names[1], "python", "-c", RECEIVE], data=json.dumps(private).encode())
        health = "import urllib.request; urllib.request.urlopen('http://mlflow-restored:5000/health',timeout=2).read()"
        for _ in range(30):
            try:
                bounded(["docker", "exec", names[1], "python", "-c", health], timeout=5)
                break
            except RuntimeError:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("isolated app not ready")
        recovery.compare(receipt["tables"], recovery.inventory(names[0]))
        result = json.loads(bounded(["docker", "exec", "-i", names[1], "python", "-c", PROBE],
                                    data=json.dumps(before).encode(), timeout=90))
        require(result.get("status") == "verified", "application verification failed")
        record(directory / "application-receipt.json", {**result, "images": images, "runtime_version": "3.13.0",
               "startup_preserved_all_tables": True, "network_mode": "none"})
    finally:
        cleanup = True
        errors = []
        for name in reversed(attempted):
            try:
                template = '{"id":{{json .Id}},"labels":{{json .Config.Labels}}}'
                observed = json.loads(bounded(["docker", "inspect", "--format", template, name]))
                identity = observed.get("id", "")
                require(re.fullmatch(r"[a-f0-9]{64}", identity)
                        and (observed.get("labels") or {}).get("lob-arena.restore-attempt") == attempt_id,
                        "cleanup ownership mismatch")
                bounded(["docker", "rm", "--force", identity], timeout=20)
                require(not bounded(["docker", "ps", "-aq", "--filter", "id=" + identity]).strip(),
                        "temporary container remains")
            except Exception:
                errors.append(name)
        recovery.command = original_command
        record(directory / "cleanup.json", {"attempted": attempted, "failed": errors})
        require(not errors, "temporary container cleanup incomplete")
    return result


def run_restore(source_root: Path, output: Path, backup: Path, expected_receipt: Path):
    return run(output, json.loads(expected_receipt.read_bytes()),
               source_root / "deployments/mlflow/readiness_recovery.py", backup=backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--expected-receipt", required=True, type=Path)
    parser.add_argument("--backup", type=Path, default=BACKUP)
    args = parser.parse_args()
    try:
        run_restore(args.source_root, args.output, args.backup, args.expected_receipt)
    except Exception:
        raise SystemExit("Application restore failed; details redacted. Inspect private receipts.") from None
    print("Isolated application restore verified; private evidence retained.")


if __name__ == "__main__":
    main()
