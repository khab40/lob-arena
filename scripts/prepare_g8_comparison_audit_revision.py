"""Prepare an unsigned metadata-only correction; never run the frozen runtime."""
import argparse
import hashlib
import json
from pathlib import Path


def require(value):
    if not value:
        raise ValueError('Comparison revision binding failed')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def correct_metadata(manifest_raw, inventory_raw):
    manifest = json.loads(manifest_raw)
    inventory = json.loads(inventory_raw)
    require(len(inventory) == 377 and len({r['path'] for r in inventory}) == 377)
    ref = next(r for r in inventory if r['path'] == 'comparison.json')
    require(ref['sha256'] == digest(manifest_raw) and ref['size_bytes'] == len(manifest_raw))
    require(set(manifest) == {'schema_version', 'preparation', 'checkpoints'})
    require(manifest['schema_version'] == 'g8_c4_comparison_package_v1')
    require(len(manifest['checkpoints']) == 27)
    require(set(manifest['preparation']) == {'uri', 'sha256', 'size_bytes'})
    require(manifest['preparation']['uri'] == 'preparation.json')
    manifest['preparation']['logical_name'] = 'preparation'
    corrected = encode(manifest)
    ref.update(sha256=digest(corrected), size_bytes=len(corrected))
    return corrected, encode(inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old_proposal = args.proposal.read_bytes()
    scope = json.loads(old_proposal)
    inventory_raw = args.inventory.read_bytes()
    require(digest(inventory_raw) == scope['inventory_sha256'])
    corrected, inventory = correct_metadata(args.comparison.read_bytes(), inventory_raw)
    worker = args.worker.read_bytes()
    original_root = scope['comparison_relative_root']
    scope.update(
        status='awaiting_operator_approval_not_executable_authority',
        run_name='g8-comparison-audit-r2-20260921',
        prior_job_id='aijob-e00ezdakxbj7m0xxfy',
        prior_proposal_sha256=digest(old_proposal),
        original_comparison_relative_root=original_root,
        comparison_relative_root=original_root + '-audit-r2',
        inventory_sha256=digest(inventory), worker_sha256=digest(worker),
        metadata_correction='Add required preparation.logical_name=preparation only',
        staging='Create a separate native tree; copy and rehash the 376 unchanged files; '
                'write corrected comparison.json; preserve original tree and every prior receipt',
        diagnostic_output='Fixed stage name and completed aggregate counts; no exception '
                          'text, validation details, paths, identities or row values',
        production_review_requires_rebinding=True,
        retry_authorized=False,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    proposal = (json.dumps(scope, sort_keys=True, indent=2) + '\n').encode()
    for name, raw in {'comparison.json': corrected, 'expected-inventory.json': inventory,
                      'worker.py': worker, 'proposal.json': proposal}.items():
        (args.output / name).write_bytes(raw)
    print(json.dumps({'proposal_sha256': digest(proposal),
                      'worker_sha256': digest(worker), 'jobs_submitted': 0}))


if __name__ == '__main__':
    main()
