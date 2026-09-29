"""Render a policy file from fresh readback; the operator performs the cloud update."""
import json
from pathlib import Path
import sys

from .lineage_policy import transition
from .lineage_proposal import BUCKET_ID, require_proposal
from .role_audit_bundle import read_bounded
from .verification_spec import INPUT_BUCKET, canonical, digest


def render(snapshot, output, proposal_sha, before, after):
    require_proposal(proposal_sha)
    bucket = json.loads(read_bounded(snapshot, 1024 * 1024))
    metadata = bucket["metadata"]
    version = metadata.get("resource_version")
    if (metadata.get("id") != BUCKET_ID or metadata.get("name") != INPUT_BUCKET
            or not isinstance(version, str) or not version.isdecimal()
            or bucket["status"]["state"] != "ACTIVE"):
        raise ValueError("policy readback belongs to another or inactive bucket")
    rules = transition(bucket["spec"]["bucket_policy"]["rules"], before=before, after=after)
    raw = canonical(rules)
    with output.open("xb") as stream:
        stream.write(raw)
    return {"bucket_id": BUCKET_ID, "resource_version": version,
        "policy_sha256": digest(raw), "rule_count": len(rules), "cloud_writes": 0}


def main():
    if len(sys.argv) != 6:
        raise SystemExit("usage: lineage_handoff PROPOSAL_SHA BUCKET_JSON BEFORE_OR_0 AFTER_OR_0 NEW_POLICY")
    try:
        result = render(Path(sys.argv[2]), Path(sys.argv[5]), sys.argv[1],
            int(sys.argv[3]) or None, int(sys.argv[4]) or None)
    except Exception as error:
        raise SystemExit(f"Policy rendering failed: {type(error).__name__}") from None
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
