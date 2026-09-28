"""Independent artifact inspection; never reprocess input rows or run a model."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import InputContract, Normalization
from .verification_context import verify_context
from .verification_spec import (
    FOLD_ROWS, INVENTORY_SHA, MAX_OUTPUT, OUTPUT_BUCKET, OUTPUT_PREFIX,
    ROOT_IDENTITY_SHA, SEQUENCE_SHA, TABULAR_SHA, canonical, digest,
)
from .verification_transport import deadline

REQUIRED = {"configuration.json", "normalization.json", "input-contract.json",
            "measurements.json", "inventory-reference.json", "lineage.json"}


def read(s3, name, limit, version=None):
    args = {"Bucket": OUTPUT_BUCKET, "Key": OUTPUT_PREFIX + name}
    if version:
        args["VersionId"] = version
    response = s3.get_object(**args)
    body = response["Body"]
    try:
        if (not 0 < response["ContentLength"] <= limit
                or version and str(response.get("VersionId")) != version):
            raise ValueError("published object version or size changed")
        payload = body.read(limit + 1)
        if len(payload) != response["ContentLength"]:
            raise ValueError("published object length differs")
        return payload
    finally:
        body.close()


def verify_artifacts(artifacts, request, context, expected_job_id):
    if set(artifacts) != REQUIRED:
        raise ValueError("result artifact set differs")
    if artifacts["configuration.json"] != canonical(request) or context["job_id"] != expected_job_id:
        raise ValueError("result request or provider Job identity differs")
    contract = InputContract.model_validate_json(artifacts["input-contract.json"])
    norm = Normalization.model_validate_json(artifacts["normalization.json"])
    records = json.loads(artifacts["measurements.json"])
    if (contract.tabular_manifest_sha256 != TABULAR_SHA or contract.sequence_manifest_sha256 != SEQUENCE_SHA
            or norm.training_binding_sha256 != contract.training_binding()
            or norm.fitting_rows != FOLD_ROWS["train"] or len(records) != 3
            or [r["batch_size"] for r in records] != [16, 64, 256]):
        raise ValueError("published preprocessing lineage differs")
    if contract.root.canonical_hash() != ROOT_IDENTITY_SHA:
        raise ValueError("published frozen root differs")
    for record in records:
        if (record["fold_rows"] != FOLD_ROWS or record["normalization_sha256"] != norm.sha256()
                or record["contract_sha256"] != contract.sha256()
                or record["fold_identity_sha256"]["train"] != norm.fitting_row_sha256
                or record["logical_output_sha256"] != records[0]["logical_output_sha256"]
                or record["fold_identity_sha256"] != records[0]["fold_identity_sha256"]):
            raise ValueError("published measurement parity differs")
    if json.loads(artifacts["inventory-reference.json"]) != {"sha256": INVENTORY_SHA, "objects": 185}:
        raise ValueError("published inventory differs")
    lineage = json.loads(artifacts["lineage.json"])
    if (lineage["context"] != context or lineage["source_commit"] != request["source_commit"]
            or lineage["model_runs"] != 0 or lineage["scope"] != "development_input_preparation_only"):
        raise ValueError("published execution lineage differs")
    return {"job_id": expected_job_id, "fold_rows": FOLD_ROWS,
            "normalization_sha256": norm.sha256(), "contract_sha256": contract.sha256(),
            "logical_output_sha256": records[0]["logical_output_sha256"]}


def collect(s3, request, expected_job_id, expected_success_sha256, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    with deadline(300):
        success = read(s3, "SUCCESS", 4096)
        if digest(success) != expected_success_sha256:
            raise ValueError("SUCCESS differs from the independent provider Job log")
        terminal = json.loads(success)
        if terminal["request_sha256"] != digest(canonical(request)):
            raise ValueError("terminal request binding differs")
        envelope = read(s3, "execution-context.json", 4096)
        context = verify_context(json.loads(envelope), request)
        if read(s3, "INTENT", 4096) != canonical(request):
            raise ValueError("execution intent differs")
        checksums = read(s3, "checksums.json", 65536)
        if digest(checksums) != terminal["checksums_sha256"]:
            raise ValueError("terminal checksum binding differs")
        inventory = json.loads(checksums)
        if set(inventory) != REQUIRED or terminal["files"] != len(REQUIRED):
            raise ValueError("published artifact inventory differs")
        if sum(i["size_bytes"] for i in inventory.values()) > MAX_OUTPUT - 65536:
            raise ValueError("published result exceeds byte budget")
        artifacts = {}
        for name, item in inventory.items():
            if not item["version_id"]:
                raise ValueError("published object version absent")
            raw = read(s3, name, item["size_bytes"], item["version_id"])
            if len(raw) != item["size_bytes"] or digest(raw) != item["sha256"]:
                raise ValueError("published artifact checksum differs")
            artifacts[name] = raw
        verified = verify_artifacts(artifacts, request, context, expected_job_id)
        for name, payload in {**artifacts, "SUCCESS": success, "checksums.json": checksums,
                              "execution-context.json": envelope}.items():
            (output / name).write_bytes(payload)
        (output / "verification.json").write_bytes(canonical(verified))
    return verified
