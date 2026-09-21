"""Inert Python children only; no model, protected rows or frozen SDK imports."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
SUPERVISOR = SCRIPTS / 'g8_audit_supervisor.py'
WORKER = SCRIPTS / 'g8_comparison_semantics_probe.py'


@pytest.mark.parametrize('exit_code', [0, 7])
def test_supervisor_preserves_success_and_failure(exit_code, capsys):
    module = runpy.run_path(str(SUPERVISOR))
    result = module['supervise']([sys.executable, '-c', f'raise SystemExit({exit_code})'], 5)
    assert result == (0 if exit_code == 0 else 1)
    assert json.loads(capsys.readouterr().out) == {
        'schema_version': 'g8_audit_supervisor_v1',
        'stage': 'worker_exit', 'return_code': exit_code,
    }


def test_supervisor_stops_silent_child_and_reaps_it(tmp_path, capsys):
    pid_file = tmp_path / 'pid'
    code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(30)"
    module = runpy.run_path(str(SUPERVISOR))
    assert module['supervise']([sys.executable, '-c', code, str(pid_file)], 1) == 124
    assert json.loads(capsys.readouterr().out)['stage'] == 'deadline'
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_launcher_reports_start_before_native_mount_access():
    env = dict(os.environ)
    env.pop('G8_AUDIT_SUPERVISOR_SHA256', None)
    result = subprocess.run([sys.executable, '-O', str(SUPERVISOR)], env=env,
                            capture_output=True, text=True, timeout=5)
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 1 and not result.stderr
    assert [r['stage'] for r in records] == ['launcher_started', 'launcher_failure']
    assert records[-1]['error_type'] == 'ValueError'


def test_worker_alarm_produces_redacted_progress():
    code = '''
import json,runpy,signal,sys,time
m=runpy.run_path(sys.argv[1])
m['PROGRESS'].update(stage='canonical_events', canonical_replays_exhausted=3)
signal.signal(signal.SIGALRM,m['deadline'])
try:
    signal.setitimer(signal.ITIMER_REAL,0.01)
    time.sleep(2)
except TimeoutError as error:
    print(json.dumps(m['failure_result'](error)))
'''
    result = subprocess.run([sys.executable, '-OO', '-c', code, str(WORKER)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and not result.stderr
    record = json.loads(result.stdout)
    assert record['error_type'] == 'TimeoutError' and record['audit_passed'] is False
    assert record['stage'] == 'canonical_events' and record['canonical_replays_exhausted'] == 3
    assert 'Comparison audit deadline' not in result.stdout
