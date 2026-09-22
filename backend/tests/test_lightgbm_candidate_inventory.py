"""Inventory behavior with inert bytes; frozen evaluation is never executed."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/build_lightgbm_candidate_inventory.py'
MODULE = runpy.run_path(str(SCRIPT))
FIXTURE = runpy.run_path(str(Path(__file__).with_name('lightgbm_inventory_fixture.py')))
build = MODULE['build_inventory']


def test_inventory_is_portable_complete_and_explicit_about_limits(tmp_path):
    left, right = tmp_path / 'left', tmp_path / 'right'
    anchor = FIXTURE['make_freeze'](left)
    assert FIXTURE['make_freeze'](right) == anchor
    report = build(left, anchor)
    assert report == build(right, anchor)
    assert report['configuration']['ordered_features'] == ['rate']
    assert report['lineage']['mlflow_run_id'] == 'mlflow-selected'
    assert report['verification'] == {
        'result_objects_verified': 17, 'model_loaded': False, 'rows_parsed': False,
        'live_mlflow_verified': False, 'remote_storage_verified': False,
        'final_evaluation_authorized': False,
    }
    assert all(item['uri'].startswith('s3://fixture/result/') for item in report['result_objects'])
    assert {item['path'] for item in report['result_objects']} == {
        p.relative_to(left / 'candidate').as_posix()
        for p in (left / 'candidate').rglob('*') if p.is_file()
    }


@pytest.mark.parametrize('case', ['anchor', 'missing', 'model', 'extra', 'checksum', 'symlink'])
def test_rejects_incomplete_or_changed_release(tmp_path, case):
    root = tmp_path / 'freeze'
    anchor = FIXTURE['make_freeze'](root)
    model = root / 'candidate/artifacts/training/model.txt'
    if case == 'anchor':
        anchor = '0' * 64
    elif case == 'missing':
        model.unlink()
    elif case == 'model':
        model.write_bytes(b'tampered model')
    elif case == 'extra':
        (root / 'candidate/unlisted').write_bytes(b'extra')
    elif case == 'checksum':
        (root / 'candidate/checksums.sha256').write_bytes(b'incorrect')
    else:
        outside = tmp_path / 'outside'
        outside.write_bytes(model.read_bytes())
        model.unlink()
        model.symlink_to(outside)
    with pytest.raises((ValueError, FileNotFoundError)):
        build(root, anchor)


@pytest.mark.parametrize('case', ['order', 'binding', 'seed', 'threshold', 'test_fold', 'mlflow_request'])
def test_rejects_contradictory_anchored_metadata(tmp_path, case):
    def change(training, calibration, schema, request):
        if case == 'order':
            schema['ordered_features'][0]['name'] = 'different'
        elif case == 'binding':
            calibration['binding']['feature_config_hash'] = 'f' * 64
        elif case == 'seed':
            request['random_seed'] = 7
        elif case == 'threshold':
            calibration['operating_points'][0]['threshold'] = 0.9
        elif case == 'test_fold':
            training['input_features'][0]['fold'] = 'test'
        else:
            request['run_id'] = 'different-run'
    root = tmp_path / 'freeze'
    anchor = FIXTURE['make_freeze'](root, change)
    with pytest.raises(ValueError):
        build(root, anchor)


@pytest.mark.parametrize('name', ['../outside', '/tmp/outside', 'candidate/../outside', 'candidate//x'])
def test_rejects_noncanonical_reference_paths(tmp_path, name):
    with pytest.raises(ValueError):
        MODULE['safe_file'](tmp_path, name)


def test_rejects_duplicate_inventory_entries(tmp_path):
    root = tmp_path / 'freeze'
    FIXTURE['make_freeze'](root)
    path = root / 'candidate/SUCCESS'
    content = json.loads(path.read_bytes())
    content['files'].append(content['files'][0])
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match='Duplicate inventory path'):
        MODULE['verify_result'](root / 'candidate', hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize('flags', [[], ['-O'], ['-OO']])
def test_cli_needs_no_ml_dependencies_and_never_overwrites_evidence(tmp_path, flags):
    root = tmp_path / 'freeze'
    anchor = FIXTURE['make_freeze'](root)
    output = tmp_path / 'inventory.json'
    command = [sys.executable, '-S', *flags, str(SCRIPT), '--freeze-root', str(root),
               '--freeze-sha256', anchor, '--output', str(output)]
    passed = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert passed.returncode == 0, passed.stderr
    before = output.read_bytes()
    duplicate = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert duplicate.returncode != 0 and output.read_bytes() == before
    command[-1] = str(root / 'new-index.json')
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert rejected.returncode != 0 and not (root / 'new-index.json').exists()
