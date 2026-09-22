"""Injected audit launcher: bound the child even before its native file opens."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def report(stage, **fields):
    print(json.dumps({'schema_version': 'g8_audit_supervisor_v1',
                      'stage': stage, **fields}), flush=True)


def supervise(command, seconds):
    # A fresh process group lets the watchdog terminate descendants as well.
    child = subprocess.Popen(command, start_new_session=True)
    try:
        code = child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        report('deadline', audit_passed=False)
        return 124
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
    report('worker_exit', return_code=code)
    return 0 if code == 0 else 1


def main():
    # This injected file is independent of the native mount. Emit before mount I/O.
    report('launcher_started')
    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if digest != os.environ.get('G8_AUDIT_SUPERVISOR_SHA256'):
        raise ValueError('Unapproved supervisor')
    if len(sys.argv) != 2 or sys.argv[1] != 'g8-comparison-audit-r5-20260922':
        raise ValueError('Unapproved audit path')
    base = '/g8-package/comparison-audits/' + sys.argv[1]
    return supervise([sys.executable, '-u', base + '/worker.py', base + '/proposal.json'], 3000)


if __name__ == '__main__':
    try:
        status = main()
    except BaseException as error:
        report('launcher_failure', audit_passed=False, error_type=type(error).__name__)
        status = 1
    sys.exit(status)
