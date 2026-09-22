"""Byte-only synthetic receipts. No training, scoring or runtime imports."""
import hashlib
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else canonical(value))
    return {'uri': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size_bytes': path.stat().st_size}


def make_freeze(root, change=None):
    root.mkdir()
    result = root / 'candidate'
    artifacts = result / 'artifacts'
    image = 'registry.invalid/jobs@sha256:' + 'a' * 64
    model = write(artifacts, 'training/model.txt', b'inert model bytes')
    prediction = write(artifacts, 'calibration/predictions.parquet', b'inert prediction bytes')
    features = [{'fold': fold, 'row_count': 1, 'artifact': write(
        artifacts, f'{fold}.parquet', b'inert feature bytes')} for fold in ('train', 'validation')]
    training = {
        'model_artifact': model, 'preprocessing': {'mode': 'none', 'transformer': None},
        'data_policy': {'test_fold_accessed': False}, 'binding': {'feature_config_hash': 'b' * 64},
        'ordered_feature_columns': ['rate'], 'input_features': features,
        'hyperparameters': {'num_leaves': 8}, 'training_seed': 42, 'git_commit': 'c' * 40,
        'feature_release_id': 'fixture-release', 'feature_release_sha256': 'f' * 64,
        'class_weights': {'negative': 1, 'positive': 2}, 'early_stopping': {'best_iteration': 2},
    }
    calibration = {
        'input_predictions': prediction, 'test_fold_accessed': False, 'fit_fold': 'validation',
        'binding': dict(training['binding']), 'parameters': {'method': 'isotonic'},
        'operating_points': [{'mode': 'balanced', 'threshold': 0.5}],
    }
    experiment = {'hyperparameters': {'num_leaves': 8}, 'operating_mode': 'balanced',
                  'calibration_method': 'isotonic'}
    schema = {'ordered_features': [{'name': 'rate'}], 'feature_config_hash': 'b' * 64}
    request = {
        'mode': 'development', 'campaign_id': 'campaign', 'run_id': 'selected', 'image': image,
        'experiment': experiment, 'random_seed': 42, 'git_commit': 'c' * 40,
        'input': {'kind': 'tabular-projection'}, 'input_release_uri': 's3://fixture/development',
        'mlflow_tracking_uri': 'https://tracking.invalid', 'result_uri': 's3://fixture/result',
    }
    if change:
        change(training, calibration, schema, request)
    candidate = {
        'schema_version': 'lightgbm_wave1_candidate_v1', 'test_fold_accessed': False,
        'campaign_id': 'campaign', 'reproducibility_hash': 'd' * 64, 'experiment': experiment,
        'training_manifest': write(artifacts, 'training/training-run.json', training),
        'calibration_manifest': write(artifacts, 'calibration/calibration-manifest.json', calibration),
        'feature_schema': write(artifacts, 'calibration/feature-schema.json', schema),
    }
    for name in ('validation_metrics', 'feature_importance', 'reliability_bins', 'reliability_diagram'):
        candidate[name] = write(artifacts, f'calibration/{name}.json', {})
    candidate_ref = write(root, 'candidate/candidate.json', candidate)
    request_ref = write(result, 'request.json', request)
    run = {
        'mode': 'development', 'status': 'succeeded', 'run_id': 'selected', 'campaign_id': 'campaign',
        'request_sha256': request_ref['sha256'], 'image': image, 'candidate_hash': candidate_ref['sha256'],
        'reproducibility_hash': 'd' * 64, 'mlflow_run_id': 'mlflow-selected',
    }
    write(result, 'cloud-run.json', run)
    write(result, 'environment.json', {'image': image, 'python': 'inert-fixture'})
    files = [{'path': p.relative_to(result).as_posix(), 'size_bytes': p.stat().st_size,
              'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(result.rglob('*')) if p.is_file()]
    success = write(result, 'SUCCESS', {'schema_version': 'lightgbm_wave1_input_inventory_v1', 'files': files})
    write(result, 'checksums.sha256', ''.join(f"{f['sha256']}  {f['path']}\n" for f in files).encode())
    comparison = {
        'status': 'passed', 'gates': {'inert_gate': True}, 'selected_trial_id': 'isotonic',
        'campaign_id': 'campaign', 'selected_candidate_hash': candidate_ref['sha256'],
        'selected_reproducibility_hash': 'd' * 64,
        'calibration_ranking': [{'trial_id': 'isotonic', 'mlflow_run_id': 'mlflow-selected',
                                'input_identity_hash': 'e' * 64}],
    }
    collection = {
        'verified': True, 'nebius_job_id': 'job-selected', 'run_id': 'selected',
        'mlflow_run_id': 'mlflow-selected', 'request_sha256': request_ref['sha256'],
        'actual_job_context': {'image': image},
    }
    monitor = {'status': 'COMPLETED', 'job_id': 'job-selected', 'request_sha256': request_ref['sha256']}
    freeze = {
        'schema_version': 'lightgbm_wave1_g7_candidate_freeze_v1', 'test_fold_accessed': False,
        'candidate': candidate_ref, 'candidate_hash': candidate_ref['sha256'], 'model_sha256': model['sha256'],
        'source_result_inventory_sha256': success['sha256'], 'image': image, 'campaign_id': 'campaign',
        'reproducibility_hash': 'd' * 64, 'experiment_hash': hashlib.sha256(canonical(experiment)).hexdigest(),
        'input_identity_hash': 'e' * 64, 'operating_mode': 'balanced', 'threshold': 0.5,
        'calibration_method': 'isotonic', 'selected_trial_id': 'isotonic',
        'g6_comparison': write(root, 'evidence/comparison.json', comparison),
        'selected_collection': write(root, 'evidence/collection.json', collection),
        'selected_monitor': write(root, 'evidence/monitor.json', monitor),
    }
    return write(root, 'g7-candidate-freeze.json', freeze)['sha256']
