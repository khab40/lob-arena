"""Synthetic metadata only; no protected rows or frozen-runtime execution."""
import hashlib
import json
from pathlib import Path
import runpy

import pytest


REVISION = runpy.run_path(str(Path(__file__).resolve().parents[2]
                             / 'scripts/prepare_g8_comparison_audit_revision.py'))


def fixture():
    manifest = {'schema_version': 'g8_c4_comparison_package_v1',
                'preparation': {'uri': 'preparation.json', 'sha256': 'a' * 64, 'size_bytes': 1},
                'checkpoints': [{'source_uri': f's3://fixture/{i}', 'relative_root': str(i)}
                                for i in range(27)]}
    raw = REVISION['encode'](manifest)
    inventory = [{'path': 'comparison.json', 'size_bytes': len(raw),
                  'sha256': hashlib.sha256(raw).hexdigest()}]
    inventory += [{'path': f'fixture/{i}', 'size_bytes': 1, 'sha256': 'b' * 64}
                  for i in range(376)]
    return raw, inventory


def test_revision_changes_only_required_metadata_and_its_inventory_entry():
    raw, inventory = fixture()
    fixed, new_inventory = REVISION['correct_metadata'](raw, REVISION['encode'](inventory))
    corrected = json.loads(fixed)
    assert corrected['preparation'].pop('logical_name') == 'preparation'
    assert corrected == json.loads(raw)
    new_inventory = json.loads(new_inventory)
    assert new_inventory[1:] == inventory[1:]
    assert new_inventory[0] == {'path': 'comparison.json', 'size_bytes': len(fixed),
                                'sha256': hashlib.sha256(fixed).hexdigest()}


@pytest.mark.parametrize('case', ['hash', 'size', 'duplicate', 'already_corrected'])
def test_revision_rejects_drift(case):
    raw, inventory = fixture()
    if case == 'hash':
        inventory[0]['sha256'] = 'c' * 64
    elif case == 'size':
        inventory[0]['size_bytes'] += 1
    elif case == 'duplicate':
        inventory[-1] = inventory[-2]
    else:
        raw, encoded = REVISION['correct_metadata'](raw, REVISION['encode'](inventory))
        inventory = json.loads(encoded)
    with pytest.raises(ValueError):
        REVISION['correct_metadata'](raw, REVISION['encode'](inventory))
