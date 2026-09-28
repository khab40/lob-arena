"""Bounded, version-specific reads and conditional result writes using S3 SDK."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import signal
import time

from .verification_spec import (
    ENDPOINT, INPUT_BUCKET, INPUT_PREFIX, MAX_OUTPUT, MAX_RESPONSE,
    OUTPUT_BUCKET, OUTPUT_PREFIX, canonical, digest,
)


def client():
    # Import lazily: inert unit tests need no credentials or network SDK.
    import botocore.session
    from botocore.config import Config
    return botocore.session.get_session().create_client("s3", endpoint_url=ENDPOINT,
        region_name="eu-north1", config=Config(connect_timeout=5, read_timeout=5,
            retries={"total_max_attempts": 1}, s3={"addressing_style": "path"},
            request_checksum_calculation="when_required", response_checksum_validation="when_required"))


@contextmanager
def deadline(seconds):
    def expired(*_):
        raise TimeoutError("verification phase exceeded its deadline")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@dataclass
class Budget:
    attempts: int = 0
    response_bytes: int = 0

    def start(self):
        self.attempts += 1
        if self.attempts > 555:
            raise ValueError("GET request budget exhausted")


def read_version(s3, item, budget):
    budget.start()
    response = s3.get_object(Bucket=INPUT_BUCKET, Key=item["key"], VersionId=item["version_id"])
    body = response["Body"]
    try:
        if (str(response.get("VersionId")) != item["version_id"]
                or response.get("ContentLength") != item["size_bytes"]):
            raise ValueError("S3 version or size differs from approved inventory")
        chunks, total = [], 0
        while True:
            remaining = MAX_RESPONSE - budget.response_bytes
            if remaining <= 0:
                raise ValueError("response-byte budget exhausted")
            chunk = body.read(min(65536, item["size_bytes"] + 1 - total, remaining))
            budget.response_bytes += len(chunk)
            total += len(chunk)
            if total > item["size_bytes"]:
                raise ValueError("S3 body exceeds declared size")
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        if total != item["size_bytes"] or digest(payload) != item["sha256"]:
            raise ValueError("S3 body checksum or length mismatch")
        return payload
    finally:
        body.close()


def retryable(error):
    # Retry only transport failures and explicit transient service errors.
    if isinstance(error, (ValueError, TimeoutError)):
        return False
    from botocore.exceptions import ClientError, ConnectionError, HTTPClientError
    if isinstance(error, (ConnectionError, HTTPClientError)):
        return True
    return isinstance(error, ClientError) and error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (429, 500, 502, 503, 504)


def download(s3, items, directory):
    directory.mkdir(parents=True, exist_ok=False)
    budget = Budget()
    with deadline(300):
        for item in items:
            for attempt in range(3):
                try:
                    payload = read_version(s3, item, budget)
                    break
                except Exception as error:
                    if attempt == 2 or not retryable(error):
                        raise
                    time.sleep(0.25 * (attempt + 1))
            path = directory / item["key"].removeprefix(INPUT_PREFIX)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(payload)
    return {"get_attempts": budget.attempts, "response_bytes": budget.response_bytes}


def require_empty(s3):
    result = s3.list_objects_v2(Bucket=OUTPUT_BUCKET, Prefix=OUTPUT_PREFIX, MaxKeys=1)
    if result.get("KeyCount", 0) or result.get("Contents") or result.get("IsTruncated"):
        raise ValueError("output prefix already contains objects")


def put_new(s3, name, payload):
    if "/" in name or name in (".", "..") or not name or len(payload) > MAX_OUTPUT:
        raise ValueError("invalid result object")
    response = s3.put_object(Bucket=OUTPUT_BUCKET, Key=OUTPUT_PREFIX + name, Body=payload,
        IfNoneMatch="*", ContentType="application/json", Metadata={"sha256": digest(payload)})
    return {"sha256": digest(payload), "size_bytes": len(payload), "version_id": str(response.get("VersionId", ""))}


def claim(s3, request):
    with deadline(30):
        require_empty(s3)
        return put_new(s3, "INTENT", canonical(request))


def publish(s3, artifacts, request_sha256):
    if (not artifacts or len(artifacts) > 8 or sum(map(len, artifacts.values())) > MAX_OUTPUT - 65536
            or any(n in ("INTENT", "SUCCESS", "FAILED", "checksums.json") for n in artifacts)):
        raise ValueError("result envelope exceeds limits or includes reserved names")
    with deadline(300):
        inventory = {name: put_new(s3, name, value) for name, value in sorted(artifacts.items())}
        inventory_payload = canonical(inventory)
        put_new(s3, "checksums.json", inventory_payload)
        # An uncertain final write is resolved by independent readback, never an automatic rerun.
        return put_new(s3, "SUCCESS", canonical({"request_sha256": request_sha256,
            "checksums_sha256": digest(inventory_payload), "files": len(inventory)}))
