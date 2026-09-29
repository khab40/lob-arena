"""Deterministic scope for separate operator approval; contains no access credentials."""
import json

from .lineage_inventory import MAX_OBJECT, PHASE_SECONDS, phase_keys
from .lineage_policy import GROUP
from .verification_spec import INPUT_BUCKET, digest

BUCKET_ID = "storagebucket-e001935725601413893009"


def proposal():
    return {"schema_version": "transformer_lineage_access_proposal_v1", "date": "2026-09-29",
        "story": "https://github.com/khab40/lob-arena/issues/24",
        "project": "https://github.com/users/khab40/projects/3",
        "bucket_id": BUCKET_ID, "bucket_name": INPUT_BUCKET, "group_id": GROUP,
        "role": "storage.viewer", "approval_required": True,
        "anchor_bundle_sha256": "697f29587002e8cb46f30c8942ebd1a3ac0e78701ed51e69f8aeb330431e83f3",
        "previous_access": "removed at bucket resource version 134",
        "phases": [{"phase": phase, "keys": phase_keys(phase),
            "temporary_rules": 6, "max_access_seconds": 3600,
            "max_get_attempts": len(phase_keys(phase)), "deadline_seconds": PHASE_SECONDS}
            for phase in (1, 2)],
        "phase_one_content": "1 C3 request, 27 SUCCESS checksum inventories, 30 feature metadata JSON files",
        "phase_two_content": "30 replay manifest JSON files, 27 ground-truth JSONL label-window metadata files",
        "max_object_bytes": MAX_OBJECT, "max_get_attempts": 115, "sdk_retries": 0,
        "max_response_bytes_including_overflow_probes": 115 * (MAX_OBJECT + 1),
        "max_total_access_seconds": 7200, "provider_max_rules": 10, "provider_max_paths_per_rule": 10,
        "transitions": ["grant phase 1", "replace phase 1 with phase 2", "remove phase 2"],
        "abort": "stop on first failure and remove the active phase; no automatic retry",
        "handoff": "operator applies and removes exact rules using fresh resource versions; agent verifies readback",
        "retention": "local metadata bytes, object versions, checksums, bounded measurements and sanitized failures",
        "cost_policy": "existing operator-managed policy; metadata GETs only, no compute allocation",
        "excluded": ["events", "snapshots", "Parquet or sequence payloads", "final-test data",
            "Jobs", "GPU training", "G8 evaluation", "MLflow writes", "PR merge", "Git cleanup"],
        "source_separation_verified": False, "gpu_ready": False, "execution_authorized": False}


def proposal_bytes():
    return (json.dumps(proposal(), indent=2) + "\n").encode()


def require_proposal(approved_sha256):
    if approved_sha256 != digest(proposal_bytes()):
        raise ValueError("lineage scope differs from the supplied approval digest")
