"""Bounded, read-only guest readiness with normalized diagnostics (Bug #280)."""
import json
import subprocess
import time

STATES = {"unknown", "created", "restarting", "running", "removing", "paused", "exited", "dead"}
PROBE = r'''
import json,subprocess
value={'ssh_reachable':True,'sudo_status':'unknown','docker_status':'unknown',
       'app_status':'unknown','app_running':False,'db_status':'unknown','db_running':False}
def emit(): print(json.dumps(value,sort_keys=True),flush=True)
def call(args):
    try:
        result=subprocess.run(args,capture_output=True,timeout=2,check=False)
        return result.returncode,result.stdout
    except subprocess.TimeoutExpired: return None,b''
emit()
code,_=call(['sudo','-n','true'])
value['sudo_status']='allowed' if code==0 else 'timed_out' if code is None else 'denied'; emit()
if code==0:
    code,_=call(['sudo','-n','docker','info','--format','{{.ServerVersion}}'])
    value['docker_status']='available' if code==0 else 'timed_out' if code is None else 'unavailable'; emit()
    if code==0:
        code,raw=call(['sudo','-n','docker','inspect','--format','{{json .State}}',
                      'lob-arena-mlflow-nebius-mlflow-1','lob-arena-mlflow-nebius-mlflow-postgres-1'])
        if code==0:
            try:
                rows=[json.loads(line) for line in raw.splitlines()]
                assert len(rows)==2
                for name,row in zip(('app','db'),rows):
                    status=row['Status']
                    if status in {'created','restarting','running','removing','paused','exited','dead'}:
                        value[name+'_status']=status
                        value[name+'_running']=row['Running'] is True
            except (ValueError,KeyError,TypeError,AssertionError): pass
        emit()
'''


class ReadinessError(RuntimeError):
    def __init__(self, code):
        self.failure_code = code
        super().__init__(code)


def normalized(raw, *, partial=False):
    """Accept only the probe's fixed schema; never retain raw transport output."""
    if len(raw) > 65536:
        raise ReadinessError("readiness_response_excess")
    if partial and raw and not raw.endswith(b"\n"):
        raw = raw.rsplit(b"\n", 1)[0] if b"\n" in raw else b""
    result = {"ssh_reachable": False, "sudo_status": "unknown", "docker_status": "unknown",
              "app_status": "unknown", "app_running": False, "db_status": "unknown", "db_running": False}
    for line in raw.splitlines():
        value = json.loads(line)
        if (set(value) != set(result) or type(value["ssh_reachable"]) is not bool
                or value["sudo_status"] not in {"unknown", "allowed", "denied", "timed_out"}
                or value["docker_status"] not in {"unknown", "available", "unavailable", "timed_out"}
                or any(value[name + "_status"] not in STATES or type(value[name + "_running"]) is not bool
                       for name in ("app", "db"))):
            raise ReadinessError("invalid_readiness_response")
        result = value
    return result


def wait_for_guest(ssh, *, expires, record, now=time.monotonic, sleep=time.sleep, run=subprocess.run):
    """Poll at most 90s, preserving 435s of the already-armed 600s VM window."""
    start = now()
    deadline = min(start + 90, expires - 435)
    for number in range(1, 92):
        remaining = deadline - now()
        if remaining <= 0:
            code = "guest_reserve_exhausted" if deadline == expires - 435 else "guest_readiness_timeout"
            record({"event": "deadline", "failure_code": code, "elapsed_seconds": now()-start,
                    "remaining_vm_seconds": expires-now()})
            raise ReadinessError(code)
        raw, stderr, returncode, timed_out = b"", b"", None, False
        try:
            response = run([*ssh, "python3 -B -"], input=PROBE.encode(), capture_output=True,
                           timeout=min(10, remaining), check=False)
            raw, stderr, returncode = response.stdout, response.stderr, response.returncode
        except subprocess.TimeoutExpired as error:
            raw, stderr, timed_out = error.stdout or b"", error.stderr or b"", True
        except OSError:
            record({"event": "poll", "poll": number, "failure_code": "ssh_process_unavailable",
                    "elapsed_seconds": now()-start, "remaining_vm_seconds": expires-now()})
            raise ReadinessError("ssh_process_unavailable") from None
        failure = None
        lowered = stderr[:65536].lower()
        if b"host key verification failed" in lowered or b"remote host identification has changed" in lowered:
            failure = "ssh_host_key_failed"
        elif b"permission denied (" in lowered or b"no supported authentication methods" in lowered:
            failure = "ssh_authentication_failed"
        try:
            observed = normalized(raw, partial=timed_out)
        except (ValueError, TypeError, ReadinessError):
            observed = normalized(b"")
            failure = failure or "invalid_readiness_response"
        if returncode == 0 and not observed["ssh_reachable"]:
            failure = failure or "invalid_readiness_response"
        if returncode not in (None, 0, 255):
            failure = failure or "guest_probe_failed"
        if observed["sudo_status"] == "denied":
            failure = failure or "guest_sudo_denied"
        ready = returncode == 0 and observed["ssh_reachable"] and observed["sudo_status"] == "allowed" and observed["docker_status"] == "available" and all(
            observed[name + "_running"] and observed[name + "_status"] == "running" for name in ("app", "db"))
        result = {"event": "poll", "poll": number, **observed, "ssh_returncode": returncode,
                  "poll_timed_out": timed_out, "failure_code": failure,
                  "elapsed_seconds": now()-start, "remaining_vm_seconds": expires-now(), "ready": ready}
        record(result)
        if failure:
            raise ReadinessError(failure)
        if ready and now() <= deadline and expires-now() >= 435:
            return result
        sleep(min(1, max(0, deadline-now())))
    raise ReadinessError("guest_poll_limit")
