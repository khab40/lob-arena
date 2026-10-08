"""Metadata preparation and one conditional development-reference publication."""
import json

from .holdout_spec import InputObject, OUTPUT_BUCKET
from .settings_schema import Artifact
from .role_execution_transport import verify_sha_metadata
from .verification_spec import INPUT_BUCKET, INPUT_PREFIX, INVENTORY_SHA, digest, load_inventory

AUDIT_SHA = "57522beed715d63b28e02d0e21530fc3060f158b09ebfcd65dba9e0b066edb3f"
REFERENCE_SHA = "220a2cf373290c846e1da29252ed149156b3f74d6598d2da4e9863bfbca364a5"
REFERENCE_SIZE = 7544
REFERENCE_KEY = "campaigns/wave1-research-20260816/development/transformer-holdout-reference-20261006/reference-logits.json"


def audited_inputs(development_inventory, audited_inventory):
    """Build exact metadata inputs; never fetch payloads or authorize execution."""
    development = load_inventory(development_inventory, INVENTORY_SHA)
    raw = audited_inventory.read_bytes()
    if digest(raw) != AUDIT_SHA:
        raise ValueError("reviewed holdout inventory changed")
    audited = json.loads(raw)
    result = []
    for item in development:
        path = item["key"].removeprefix(INPUT_PREFIX).removeprefix("artifacts/")
        path = {"manifests/tabular-projection.json": "development-tabular.json",
                "manifests/sequence-projection.json": "development-sequences.json"}.get(path, path)
        result.append(InputObject(path=path, scope="development", reference=Artifact(
            uri="s3://" + INPUT_BUCKET + "/" + item["key"],
            **{k: item[k] for k in ("sha256", "size_bytes", "version_id")})))
    for item in audited:
        if item["key"].endswith(("/frozen-root.json", "/prediction-manifest.json")):
            continue  # Authenticated metadata; not consumed by the inference worker.
        path = (item["key"].removeprefix(INPUT_PREFIX).removeprefix("artifacts/") if item["bucket"] != OUTPUT_BUCKET
                else "baseline/predictions.parquet")
        result.append(InputObject(path=path, scope="final_test", reference=Artifact(
            uri="s3://" + item["bucket"] + "/" + item["key"],
            **{k: item[k] for k in ("sha256", "size_bytes", "version_id")})))
    if (len(result) != 248 or len({i.path for i in result}) != len(result)
            or len({i.reference.uri for i in result}) != len(result)):
        raise ValueError("prepared inventory is incomplete or duplicates identities")
    return tuple(result)


def publish_reference(s3, raw):
    """Publish only the reviewed saved logits; never overwrite or retry a PUT."""
    if type(raw) is not bytes or len(raw) != REFERENCE_SIZE or digest(raw) != REFERENCE_SHA:
        raise ValueError("saved reference bytes differ")
    location = {"Bucket": OUTPUT_BUCKET, "Key": REFERENCE_KEY}
    try:
        s3.head_object(**location)
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
            raise
    else:
        raise ValueError("reference already exists; reconcile rather than republish")
    response = s3.put_object(**location, Body=raw, IfNoneMatch="*",
        Metadata={"sha256": REFERENCE_SHA}, ContentType="application/json")
    version = response.get("VersionId")
    if not isinstance(version, str) or version in ("", "null"):
        raise ValueError("reference PUT has no immutable version; reconcile")
    observed = s3.get_object(**location, VersionId=version)
    body = observed["Body"]
    try:
        saved = body.read(REFERENCE_SIZE + 1)
    finally:
        body.close()
    if (saved != raw or observed.get("VersionId") != version
            or observed.get("ContentLength") != REFERENCE_SIZE):
        raise ValueError("reference publication readback differs; reconcile")
    verify_sha_metadata(observed, REFERENCE_SHA)
    return Artifact(uri="s3://" + OUTPUT_BUCKET + "/" + REFERENCE_KEY,
        sha256=REFERENCE_SHA, size_bytes=REFERENCE_SIZE, version_id=version)
