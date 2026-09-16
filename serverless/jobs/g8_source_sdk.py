"""Single-client synthetic staging transport; no per-object AWS CLI processes."""
from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from pathlib import Path

from app.ml.lightgbm import g8_publication_recovery as transport


@contextmanager
def session_deadline(seconds: int):
    """Bound the entire main-thread operation, including slow streaming responses."""
    if not 1 <= seconds <= 1800 or signal.getitimer(signal.ITIMER_REAL)[0]:
        raise ValueError("staging requires an unused timer and a 1..1800 second deadline")

    def expired(*_):
        # BaseException bypasses SDK network-error wrapping and PUT reconciliation.
        raise SystemExit("synthetic staging session expired; preserve partial objects")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class SourceSDK:
    def __init__(self):
        import awscli  # noqa: F401 - registers its vendored botocore in the frozen image
        import botocore.session
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError

        key, secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not key or not secret:
            raise ValueError("explicit AWS environment credentials required")
        self.errors = (BotoCoreError, ClientError)
        self.client_error = ClientError
        self.client = botocore.session.get_session().create_client(
            "s3", endpoint_url=transport.ENDPOINT, region_name="eu-north1",
            aws_access_key_id=key, aws_secret_access_key=secret,
            aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
            config=Config(connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1},
                          signature_version="s3v4", s3={"addressing_style": "path"},
                          request_checksum_calculation="when_required", response_checksum_validation="when_required"),
        )

    def _aws_json(self, endpoint, *args):
        if endpoint != transport.ENDPOINT or args[0] != "s3api":
            raise ValueError("unexpected staging endpoint or service")
        operation = args[1]
        names = {"--bucket": "Bucket", "--key": "Key", "--prefix": "Prefix",
                 "--max-keys": "MaxKeys", "--continuation-token": "ContinuationToken",
                 "--if-none-match": "IfNoneMatch", "--metadata": "Metadata"}
        options, target, i = {}, None, 2
        while i < len(args):
            flag = args[i]
            if flag == "--no-paginate":
                i += 1
                continue
            if flag == "--body":
                target, i = Path(args[i + 1]), i + 2
                continue
            if flag not in names:
                if operation != "get-object" or i != len(args) - 1 or flag.startswith("--"):
                    raise ValueError("unsupported staging argument")
                target, i = Path(flag), i + 1
                continue
            value = args[i + 1]
            options[names[flag]] = (int(value) if flag == "--max-keys" else
                                   dict([value.split("=", 1)]) if flag == "--metadata" else value)
            i += 2
        try:
            if operation == "put-object" and target is not None and options.get("IfNoneMatch") == "*":
                with target.open("rb") as body:
                    return self.client.put_object(**options, Body=body)
            if operation == "get-object" and target is not None:
                response = self.client.get_object(**options)
                with response["Body"] as body, target.open("xb") as output:
                    # A malicious/changed remote object cannot fill the local disk.
                    remaining = self.download_limit
                    while chunk := body.read(min(65536, remaining + 1)):
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise ValueError("source download exceeds its sealed size")
                        output.write(chunk)
                return {}
            if operation == "head-object":
                return self.client.head_object(**options)
            if operation == "list-objects-v2":
                return self.client.list_objects_v2(**options)
        except self.errors:
            # SDK errors may contain request details; expose neither credentials
            # nor signed headers. The caller resolves ambiguous PUTs by readback.
            raise RuntimeError("synthetic source S3 operation failed") from None
        raise ValueError("unsupported staging operation or nonconditional upload")

    def _transfer_json(self, size, *args):
        transport._transfer_timeout(size)
        self.download_limit = size
        return self._aws_json(transport.ENDPOINT, *args)

    def _listed_keys(self, bucket, prefix, allowed):
        return transport._listed_keys(bucket, prefix, allowed, aws_json=self._aws_json)

    def _readback(self, bucket, key, **kwargs):
        return transport._readback(bucket, key, **kwargs, aws_json=self._aws_json, transfer_json=self._transfer_json)

    def production_head_denied(self, bucket, key):
        try:
            self.client.head_object(Bucket=bucket, Key=key)
        except self.client_error as exc:
            error = exc.response
            if (error.get("ResponseMetadata", {}).get("HTTPStatusCode") == 403
                    and error.get("Error", {}).get("Code") in {"403", "AccessDenied", "Forbidden"}):
                return
        except self.errors:
            pass
        raise ValueError("production HEAD did not return an explicit access denial")
