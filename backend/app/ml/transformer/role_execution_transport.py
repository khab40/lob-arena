"""One-attempt, version-bound S3 IO for the dedicated CPU role audit."""
from dataclasses import dataclass
import re

from .role_deadline import deadline
from .role_execution_spec import (
    ENDPOINT, INPUT_BUCKET, INPUT_PREFIX, INVENTORY_SHA, MAX_GET_ATTEMPTS,
    MAX_INPUT, MAX_OBJECT, MAX_OUTPUT, OUTPUT_BUCKET, OUTPUT_PREFIX, canonical, digest,
)


class PublicationUncertain(RuntimeError):
    """A conditional PUT may exist; retain the attempt and resolve by readback."""


def client():
    import botocore.session
    from botocore.config import Config
    return botocore.session.get_session().create_client("s3", endpoint_url=ENDPOINT,
        region_name="eu-north1", config=Config(connect_timeout=5, read_timeout=5,
            retries={"total_max_attempts": 1}, s3={"addressing_style": "path"},
            request_checksum_calculation="when_required", response_checksum_validation="when_required"))


@dataclass
class Budget:
    attempts: int = 0
    response_bytes: int = 0

    def start(self):
        if self.attempts >= MAX_GET_ATTEMPTS:
            raise ValueError("GET request budget exhausted")
        self.attempts += 1


def _version(value):
    if not isinstance(value, str) or not value or value.strip() != value or value == "null":
        raise ValueError("versioned object response required")
    return value


def _body(response, limit, expected_version=None, budget=None):
    body = response["Body"]
    try:
        version = _version(response.get("VersionId"))
        size = response.get("ContentLength")
        if (expected_version is not None and version != expected_version
                or type(size) is not int or not 0 <= size <= limit):
            raise ValueError("S3 version or size differs from approved envelope")
        chunks, total = [], 0
        while True:
            chunk = body.read(min(65536, size + 1 - total))
            total += len(chunk)
            if budget is not None:
                budget.response_bytes += len(chunk)
                if budget.response_bytes > MAX_INPUT:
                    raise ValueError("response-byte budget exhausted")
            if total > size:
                raise ValueError("S3 body exceeds declared size")
            if not chunk:
                break
            chunks.append(chunk)
        if total != size:
            raise ValueError("S3 body length mismatch")
        payload = b"".join(chunks)
        return payload, {"sha256": digest(payload), "size_bytes": size, "version_id": version}
    finally:
        body.close()


def read_version(s3, item, budget):
    if (type(item["size_bytes"]) is not int or not 0 < item["size_bytes"] <= MAX_OBJECT
            or not item["key"].startswith(INPUT_PREFIX)):
        raise ValueError("input object leaves approved envelope")
    budget.start()
    response = s3.get_object(Bucket=INPUT_BUCKET, Key=item["key"], VersionId=item["version_id"])
    payload, receipt = _body(response, item["size_bytes"], item["version_id"], budget)
    if receipt != {key: item[key] for key in ("sha256", "size_bytes", "version_id")}:
        raise ValueError("S3 body checksum or length mismatch")
    return payload


def download(s3, items, directory):
    # Authenticate the whole reviewed inventory before any payload GET or directory creation.
    encoded = b"".join(canonical(item) + b"\n" for item in items)
    if len(items) != MAX_GET_ATTEMPTS or digest(encoded) != INVENTORY_SHA:
        raise ValueError("download inventory differs from frozen 185-object inventory")
    directory.mkdir(parents=True, exist_ok=False)
    budget = Budget()
    with deadline(300):
        for item in items:
            payload = read_version(s3, item, budget)
            path = directory / item["key"].removeprefix(INPUT_PREFIX)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(payload)
    return {"get_attempts": budget.attempts, "response_bytes": budget.response_bytes}


def _key(request, name):
    if (request["output_bucket"] != OUTPUT_BUCKET or request["output_prefix"] != OUTPUT_PREFIX
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)):
        raise ValueError("invalid role-audit output identity")
    return request["output_prefix"] + name


def require_empty(s3, request):
    _key(request, "INTENT")
    response = s3.list_objects_v2(Bucket=request["output_bucket"],
                                Prefix=request["output_prefix"], MaxKeys=1)
    if response.get("KeyCount", 0) or response.get("Contents") or response.get("IsTruncated"):
        raise ValueError("output prefix already contains objects")


def put_new(s3, request, name, payload):
    key = _key(request, name)
    if not isinstance(payload, bytes) or len(payload) > MAX_OUTPUT:
        raise ValueError("invalid result object bytes")
    try:
        response = s3.put_object(Bucket=request["output_bucket"], Key=key, Body=payload,
            IfNoneMatch="*", ContentType="application/json", Metadata={"sha256": digest(payload)})
        version = _version(response.get("VersionId"))
    except Exception as error:
        raise PublicationUncertain("conditional publication requires independent readback") from error
    return {"sha256": digest(payload), "size_bytes": len(payload), "version_id": version}


def verify_sha_metadata(response, expected_sha):
    """SDK metadata casing varies; require one unambiguous byte checksum."""
    metadata = response.get("Metadata")
    values = [value for key, value in metadata.items() if isinstance(key, str) and key.lower() == "sha256"] \
        if isinstance(metadata, dict) else []
    if len(values) != 1 or values[0] != expected_sha:
        raise ValueError("result object SHA metadata mismatch")


def read_result(s3, request, name, limit, version_id=None):
    if type(limit) is not int or not 0 < limit <= MAX_OUTPUT:
        raise ValueError("invalid result read bound")
    args = {"Bucket": request["output_bucket"], "Key": _key(request, name)}
    if version_id is not None:
        args["VersionId"] = _version(version_id)
    response = s3.get_object(**args)
    payload, receipt = _body(response, limit, version_id)
    verify_sha_metadata(response, receipt["sha256"])
    return payload, receipt


def claim(s3, request):
    with deadline(30):
        require_empty(s3, request)
        return put_new(s3, request, "INTENT", canonical(request))


def publish(s3, request, artifacts):
    reserved = {"INTENT", "SUCCESS", "FAILED", "checksums.json", "execution-context.json"}
    if (not artifacts or len(artifacts) > 8 or set(artifacts) & reserved
            or any(not isinstance(value, bytes) for value in artifacts.values())
            or sum(map(len, artifacts.values())) > MAX_OUTPUT - 65536):
        raise ValueError("result envelope exceeds limits or includes reserved names")
    for name in artifacts:
        _key(request, name)
    with deadline(300):
        inventory = {name: put_new(s3, request, name, value) for name, value in sorted(artifacts.items())}
        inventory_payload = canonical(inventory)
        checksums = put_new(s3, request, "checksums.json", inventory_payload)
        return put_new(s3, request, "SUCCESS", canonical({"request_sha256": digest(canonical(request)),
            "checksums_sha256": digest(inventory_payload), "checksums_version_id": checksums["version_id"],
            "files": len(inventory)}))
