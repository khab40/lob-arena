"""Index a hash-anchored G7 copy without importing the model runtime or using a network."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightgbm_inventory_io import (  # noqa: E402
    canonical, digest, load_json, require, safe_file, verify_ref, verify_result, write_new,
)


def build_inventory(root, freeze_sha256):
    root = Path(root).absolute()
    require(root.resolve() == root, 'Canonical freeze directory required')
    freeze_path = safe_file(root, 'g7-candidate-freeze.json')
    require(digest(freeze_path) == freeze_sha256, 'Freeze differs from external trust anchor')
    freeze = load_json(freeze_path)
    require(freeze['schema_version'] == 'lightgbm_wave1_g7_candidate_freeze_v1', 'Unknown freeze schema')
    require(freeze['test_fold_accessed'] is False, 'Freeze did not preserve development isolation')
    evidence = {name: load_json(verify_ref(root, freeze[name]))
                for name in ('g6_comparison', 'selected_collection', 'selected_monitor', 'candidate')}
    candidate_path = verify_ref(root, freeze['candidate'])
    result_root = candidate_path.parent
    entries = verify_result(result_root, freeze['source_result_inventory_sha256'])
    inventory = {entry['path']: entry for entry in entries}

    def member(name):
        require(name in inventory, 'Required result metadata missing from inventory')
        return load_json(safe_file(result_root, name))

    def artifact(ref):
        name = 'artifacts/' + ref['uri']
        require(name in inventory, 'Candidate artifact missing from result inventory')
        require(all(ref[key] == inventory[name][key] for key in ('sha256', 'size_bytes')),
                'Candidate artifact reference differs')
        return name

    candidate = evidence['candidate']
    require(candidate['schema_version'] == 'lightgbm_wave1_candidate_v1', 'Unknown candidate schema')
    require(candidate['test_fold_accessed'] is False, 'Candidate includes test access')
    require(freeze['candidate_hash'] == freeze['candidate']['sha256'] == digest(candidate_path),
            'Candidate identity differs')
    roles = {key: artifact(candidate[key]) for key in (
        'training_manifest', 'calibration_manifest', 'validation_metrics', 'feature_importance',
        'feature_schema', 'reliability_bins', 'reliability_diagram')}
    training = member(roles['training_manifest'])
    calibration = member(roles['calibration_manifest'])
    schema = member(roles['feature_schema'])
    roles['model'] = artifact(training['model_artifact'])
    roles['validation_predictions'] = artifact(calibration['input_predictions'])
    if training['preprocessing']['transformer'] is not None:
        roles['preprocessor'] = artifact(training['preprocessing']['transformer'])
    require(training['model_artifact']['sha256'] == freeze['model_sha256'], 'Frozen model differs')
    require(training['data_policy']['test_fold_accessed'] is False
            and calibration['test_fold_accessed'] is False and calibration['fit_fold'] == 'validation',
            'Training/calibration isolation differs')
    require(training['binding'] == calibration['binding'], 'Training/calibration bindings differ')
    require([f['name'] for f in schema['ordered_features']] == training['ordered_feature_columns'],
            'Feature order differs')
    require(schema['feature_config_hash'] == training['binding']['feature_config_hash'],
            'Feature config binding differs')
    require({feature['fold'] for feature in training['input_features']} == {'train', 'validation'},
            'Both development input folds are required')
    for feature in training['input_features']:
        require(feature['fold'] in {'train', 'validation'}, 'Unexpected feature fold')
        artifact(feature['artifact'])

    request, run, environment = (member(name) for name in ('request.json', 'cloud-run.json', 'environment.json'))
    comparison, collection, monitor = (evidence[k] for k in ('g6_comparison', 'selected_collection', 'selected_monitor'))
    require(request['mode'] == run['mode'] == 'development' and run['status'] == 'succeeded',
            'Selected run is not successful development')
    require(comparison['status'] == 'passed' and comparison['gates']
            and all(value is True for value in comparison['gates'].values()), 'G6 did not pass')
    require(collection['verified'] is True and monitor['status'] == 'COMPLETED', 'Collection did not pass')
    require(collection['nebius_job_id'] == monitor['job_id'], 'Job identities differ')
    require(request['run_id'] == run['run_id'] == collection['run_id'], 'Run identities differ')
    require(collection['request_sha256'] == run['request_sha256'] == monitor['request_sha256']
            == inventory['request.json']['sha256'], 'Request identities differ')
    require(all(value == freeze['image'] for value in (
        request['image'], run['image'], environment['image'], collection['actual_job_context']['image'])),
        'Image identities differ')
    require(all(value == freeze['campaign_id'] for value in (
        candidate['campaign_id'], request['campaign_id'], run['campaign_id'], comparison['campaign_id'])),
        'Campaign identities differ')
    require(comparison['selected_candidate_hash'] == run['candidate_hash'] == freeze['candidate_hash'],
            'Selected candidate differs')
    require(comparison['selected_trial_id'] == freeze['selected_trial_id'], 'Selected trial differs')
    require(comparison['selected_reproducibility_hash'] == candidate['reproducibility_hash']
            == run['reproducibility_hash'] == freeze['reproducibility_hash'], 'Reproducibility identity differs')
    require(request['experiment'] == candidate['experiment'], 'Experiment config differs')
    require(hashlib.sha256(canonical(candidate['experiment'])).hexdigest() == freeze['experiment_hash'],
            'Experiment identity differs')
    require(training['hyperparameters'] == candidate['experiment']['hyperparameters']
            and training['training_seed'] == request['random_seed'], 'Resolved training config differs')
    points = [p for p in calibration['operating_points'] if p['mode'] == freeze['operating_mode']]
    require(len(points) == 1 and points[0]['threshold'] == freeze['threshold'], 'Frozen threshold differs')
    require(candidate['experiment']['operating_mode'] == freeze['operating_mode']
            and candidate['experiment']['calibration_method'] == calibration['parameters']['method']
            == freeze['calibration_method'], 'Frozen operating config differs')
    selected = [r for r in comparison['calibration_ranking'] if r['trial_id'] == freeze['selected_trial_id']]
    require(len(selected) == 1 and selected[0]['mlflow_run_id'] == run['mlflow_run_id']
            == collection['mlflow_run_id'], 'Selected MLflow lineage differs')
    require(selected[0]['input_identity_hash'] == freeze['input_identity_hash'], 'Input identity differs')
    location = urlsplit(request['result_uri'])
    require(location.scheme == 's3' and location.netloc and not location.username
            and not location.query and not location.fragment, 'Expected credential-free S3 result URI')
    remote = request['result_uri'].rstrip('/')
    objects = [{**entry, 'uri': remote + '/' + quote(entry['path'], safe='/')} for entry in entries]
    for name in ('SUCCESS', 'checksums.sha256'):
        path = safe_file(result_root, name)
        objects.append({'path': name, 'sha256': digest(path), 'size_bytes': path.stat().st_size,
                        'uri': remote + '/' + name})
    return {
        'schema_version': 'lightgbm_candidate_inventory_v1',
        'scope': 'local_frozen_development_bytes_and_metadata_only',
        'freeze_sha256': freeze_sha256, 'candidate_sha256': freeze['candidate_hash'],
        'model_sha256': freeze['model_sha256'], 'experiment_sha256': freeze['experiment_hash'],
        'verification': {'result_objects_verified': len(objects), 'model_loaded': False,
                         'rows_parsed': False, 'live_mlflow_verified': False,
                         'remote_storage_verified': False, 'final_evaluation_authorized': False},
        'selection': {k: freeze[k] for k in ('campaign_id', 'selected_trial_id', 'reproducibility_hash')},
        'configuration': {'experiment': candidate['experiment'], 'training_seed': training['training_seed'],
                          'ordered_features': training['ordered_feature_columns'],
                          'class_weights': training['class_weights'], 'data_policy': training['data_policy'],
                          'preprocessing': training['preprocessing'], 'early_stopping': training['early_stopping'],
                          'calibration': calibration['parameters'], 'operating_points': calibration['operating_points']},
        'lineage': {'binding': training['binding'], 'input_identity_hash': freeze['input_identity_hash'],
                    'input_references': request['input'], 'input_release_uri': request['input_release_uri'],
                    'feature_inputs': training['input_features'], 'request_git_commit': request['git_commit'],
                    'training_git_commit': training['git_commit'], 'image': freeze['image'],
                    'environment': environment, 'nebius_job_id': collection['nebius_job_id'],
                    'run_id': run['run_id'], 'mlflow_run_id': run['mlflow_run_id'],
                    'mlflow_tracking_uri': request['mlflow_tracking_uri']},
        'evidence_references': {k: freeze[k] for k in ('g6_comparison', 'selected_collection', 'selected_monitor')},
        'artifact_roles': roles, 'result_uri': remote, 'result_objects': objects,
        'remaining': ['Verify exact remote objects and live MLflow evidence independently',
                      'Verify external input metadata referenced by the request',
                      'Complete separately authorized G8 evaluation and G9 disposition'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze-root', type=Path, required=True)
    parser.add_argument('--freeze-sha256', required=True, help='Trusted digest from outside the supplied directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_inventory(args.freeze_root, args.freeze_sha256)
    write_new(args.output, report, args.freeze_root.resolve())
    print(f"Verified {report['verification']['result_objects_verified']} local objects; wrote metadata inventory")


if __name__ == '__main__':
    main()
