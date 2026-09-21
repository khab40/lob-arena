"""Operator-gated, read-only comparison audit; run only on the frozen Nebius image."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

PROGRESS = {'stage': 'approval', 'inventoried_files_rehashed': 0,
            'checkpoints_verified': 0, 'canonical_replays_exhausted': 0}


def failure_result(error):
    # Fixed stage names and aggregate counts only; never serialize exception data.
    return {'audit_passed': False, 'error_type': type(error).__name__, **PROGRESS}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition):
    if not condition:
        raise ValueError("Comparison audit check failed")


def audit():
    # This digest is an operator approval assertion, not final-evaluation authority.
    scope_path = Path(sys.argv[1])
    require(sha(scope_path) == os.environ.get('G8_SEMANTIC_APPROVED_PROPOSAL_SHA256'))
    scope = json.loads(scope_path.read_bytes())
    require(sha(Path(__file__)) == scope['worker_sha256'])
    PROGRESS['stage'] = 'package_integrity'
    signal.alarm(scope['internal_timeout_seconds'])
    require(not any(os.environ.get(k) for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                                              'AWS_SESSION_TOKEN', 'MLFLOW_TRACKING_PASSWORD')))
    mount = Path('/g8-package')
    require(os.statvfs(mount).f_flag & os.ST_RDONLY)
    manifest_path = mount / 'transport-probes/g8-production-probe-20260921/manifest.json'
    require(sha(manifest_path) == scope['transport_manifest_sha256'])
    manifest = json.loads(manifest_path.read_bytes())
    package = manifest_path.parent / 'unsigned-production'
    for name, ref in manifest['files'].items():
        path = package / name
        require(path.resolve() == path.absolute() and path.stat().st_size == ref['size_bytes'])
        require(sha(path) == ref['sha256'] and os.statvfs(path).f_flag & os.ST_RDONLY)
    inventory_path = scope_path.parent / 'expected-inventory.json'
    require(sha(inventory_path) == scope['inventory_sha256'])
    inventory = json.loads(inventory_path.read_bytes())
    comparison = mount / scope['comparison_relative_root']
    require(len(inventory) == 377)
    PROGRESS['stage'] = 'comparison_integrity'
    allowed = set()
    for ref in inventory:
        path = comparison / ref['path']
        require(comparison in path.parents and path.resolve() == path.absolute())
        require(path.stat().st_size == ref['size_bytes'] and sha(path) == ref['sha256'])
        require(os.statvfs(path).f_flag & os.ST_RDONLY)
        allowed.add(str(path))
    PROGRESS['inventoried_files_rehashed'] = len(inventory)

    def guard(event, args):
        if event == 'socket.connect':
            raise PermissionError('Network access is outside this audit')
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            if name.startswith(str(comparison) + '/') and name not in allowed:
                raise PermissionError('Uninventoried comparison file')

    sys.addaudithook(guard)
    PROGRESS['stage'] = 'runtime_bootstrap'
    spec = importlib.util.spec_from_file_location('reviewed_bootstrap', package / 'g8_native_bootstrap.py')
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    for i in range(3):
        os.environ[f'G8_NATIVE_CODE_{i}_SHA256'] = manifest['files'][f'native-code-{i}.zip']['sha256']
    bootstrap.install(package)
    from app.market_data.projections import FrozenPublicSampleRoot
    from app.ml.lightgbm.c4_replay_evidence import verified_replay_paths
    from app.evaluation.canonical_bundle import open_canonical_evaluation_stream

    PROGRESS['stage'] = 'frozen_root_metadata'
    root = FrozenPublicSampleRoot.model_validate_json((package / 'frozen-root.json').read_bytes())
    PROGRESS['stage'] = 'checkpoint_metadata'
    paths = verified_replay_paths(comparison / 'comparison.json', root=root)
    PROGRESS['checkpoints_verified'] = 27
    PROGRESS['stage'] = 'projection_metadata'
    shards = {s['run_id']: s for s in json.loads((package / 'projection.json').read_bytes())['shards']}
    require(len(paths) == len(shards) == 30 and set(paths) == set(shards))
    for run_id, path in sorted(paths.items()):
        PROGRESS['stage'] = 'canonical_bundle'
        stream = open_canonical_evaluation_stream(path)
        expected = shards[run_id]
        require(stream.manifest.run_id == run_id)
        require(stream.manifest.base_session_id == expected['base_session_id'])
        require(stream.manifest.campaign_id == expected['campaign_id'])
        require(stream.manifest.canonical_event_stream_hash == expected['replay_manifest_sha256'])
        alert_ticks = set()
        for alert in stream.alerts:
            require(type(alert.get('tick')) is int and alert['tick'] >= 0)
            require(isinstance(alert.get('detector'), str) and alert['detector'])
            alert_ticks.add(alert['tick'])
        count = 0
        PROGRESS['stage'] = 'canonical_events'
        for event in stream.iter_events():
            count += 1
            alert_ticks.discard(event.tick)
        require(not alert_ticks and count == stream.manifest.event_count)
        PROGRESS['canonical_replays_exhausted'] += 1
    print(json.dumps({'schema_version': 'g8_comparison_semantics_result_v1',
                      'proposal_sha256': sha(scope_path), 'checkpoints_verified': 27,
                      'canonical_replays_exhausted': 30, 'inventoried_files_rehashed': 377,
                      'protected_comparison_rows_parsed': True, 'model_execution': False,
                      'final_bucket_access': False, 'prediction_join_verified': False,
                      'snapshot_validation': 'sha256_and_parquet_footer_row_count_only',
                      'snapshot_rows_parsed': False, 'snapshot_event_consistency_verified': False,
                      'replacement_execution_authorized': False}), flush=True)


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        audit()
    except BaseException as error:
        # Never put protected records or validation-error payloads into operator logs.
        print(json.dumps(failure_result(error)), flush=True)
        sys.exit(1)
