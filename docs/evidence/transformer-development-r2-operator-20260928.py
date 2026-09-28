"""Approved orchestration only: metadata, signed context, result-artifact readback."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CODE = ROOT / '.worktrees/transformer-input-contract'
sys.path.insert(0, str(CODE / 'backend'))
from app.ml.transformer.verification_spec import (
    INVENTORY_SHA, INPUT_BUCKET, RUN_ID, canonical, digest, load_inventory,
)
from app.ml.transformer.verification_context import validate_request, verify_context
from app.ml.transformer.verification_transport import client, deadline, put_new, require_empty
from app.ml.transformer.verification_readback import collect, read
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from botocore.exceptions import ClientError


def authenticated_client():
    selectors = {
        'AWS_ACCESS_KEY_ID': ('mbsec-e00arhndyprqr8egjw', 'mbsecver-e00rjzerny1pf9qhna'),
        'AWS_SECRET_ACCESS_KEY': ('mbsec-e00s7qtjj5n9ghacnh', 'mbsecver-e00yfn5w54jc1ybkwv'),
    }
    for name, (secret, version) in selectors.items():
        result = subprocess.run(['rtk', 'proxy', 'nebius', 'mysterybox', 'payload', 'get',
            '--secret-id', secret, '--version-id', version, '--format', 'json'],
            capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError('Pinned development credential lookup failed')
        entries = [item['string_value'] for item in json.loads(result.stdout)['data']
            if item.get('string_value') and (name != 'AWS_SECRET_ACCESS_KEY' or item.get('key') == 'secret')]
        if len(entries) != 1:
            raise ValueError('Ambiguous credential selector')
        os.environ[name] = entries[0]
    if hashlib.sha256(os.environ['AWS_ACCESS_KEY_ID'].encode()).hexdigest() != '4f129534101211604ce259cd5ded383065384b86797e8f7b407a810750062d5d':
        raise ValueError('Wrong development reader identity')
    os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
    return client()


def main():
    action = sys.argv[1]
    if action == 'prepare':
        key = Ed25519PrivateKey.generate()
        request = {'schema_version': 'transformer_input_execution_v1', 'run_id': RUN_ID,
            'source_commit': sys.argv[2], 'image_digest': sys.argv[3],
            'inventory_sha256': INVENTORY_SHA, 'context_public_key': key.public_key().public_bytes_raw().hex(),
            'nonce': secrets.token_hex(16)}
        validate_request(request, sys.argv[2])
        with (HERE / 'context-private.key').open('xb') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(key.private_bytes_raw())
        with (HERE / 'request.json').open('xb') as stream:
            stream.write(canonical(request))
        print(json.dumps({'request_sha256': digest(canonical(request))}))
        return
    s3 = authenticated_client()
    if action == 'publisher-preflight':
        from app.ml.transformer.verification_publisher import provider_job
        require_empty(s3)
        if provider_job() is not None:
            raise ValueError('Replacement Job already exists')
        print(json.dumps({'publisher_cli_absence_check': 'passed', 'output_empty': True,
            'context_writes': 0, 'job_creates': 0}))
        return
    if action == 'diagnostics':
        from app.ml.transformer.verification_spec import OUTPUT_BUCKET, OUTPUT_PREFIX
        result = {}
        with deadline(60):
            for name in ('INTENT', 'execution-context.json', 'FAILED', 'SUCCESS'):
                try:
                    response = s3.get_object(Bucket=OUTPUT_BUCKET, Key=OUTPUT_PREFIX + name)
                except ClientError as error:
                    result[name] = {'error_code': error.response.get('Error', {}).get('Code')}
                    continue
                body = response['Body']
                try:
                    if response['ContentLength'] > 4096:
                        raise ValueError('Unexpected diagnostic length')
                    raw = body.read(4097)
                    result[name] = {'last_modified': response['LastModified'].isoformat(),
                        'version_id': response.get('VersionId'), 'sha256': digest(raw),
                        'content': json.loads(raw)}
                finally:
                    body.close()
        (HERE / 'diagnostics.json').write_bytes(canonical(result))
        print(json.dumps(result))
        return
    if action == 'preflight':
        items = load_inventory(CODE / 'docs/evidence/transformer-development-input-inventory-20260928.jsonl', INVENTORY_SHA)
        with deadline(300):
            require_empty(s3)
            for item in items:
                response = s3.head_object(Bucket=INPUT_BUCKET, Key=item['key'], VersionId=item['version_id'])
                if response['ContentLength'] != item['size_bytes'] or str(response.get('VersionId')) != item['version_id']:
                    raise ValueError('Live input metadata differs')
        receipt = {'status': 'passed', 'objects': len(items), 'payload_bytes_read': 0,
            'input_bytes': sum(i['size_bytes'] for i in items), 'output_prefix_empty': True,
            'inventory_sha256': INVENTORY_SHA, 'checked_at_unix': time.time()}
        (HERE / 'preflight.json').write_bytes(canonical(receipt))
        print(json.dumps(receipt))
        return
    request = json.loads((HERE / 'request.json').read_bytes())
    if action == 'arm':
        from app.ml.transformer.verification_publisher import main as publish_context
        sys.argv = ['verification_publisher', str(HERE / 'request.json'),
            str(HERE / 'context-private.key'), str(HERE / 'publisher-receipt.json')]
        publish_context()
        return
    if action == 'collect':
        print(json.dumps(collect(s3, request, sys.argv[2], sys.argv[3], HERE / 'readback')))
        return
    raise ValueError('Unknown action')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        sys.exit(1)
