"""Exercise the provisioner's real bucket boundary without a cloud CLI."""
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
VIEWER = {"group_id": "dev-group", "roles": ["storage.viewer"], "paths": ["releases/*"]}
PREPARATION = {
    "group_id": "group-e00whp6026c6q5sgnw",
    "roles": ["storage.object-editor"],
    "paths": ["data/public-sample-v1/*"],
}


def reconcile(rules: object) -> subprocess.CompletedProcess[str]:
    source = (ROOT / "scripts/provision-nebius-wave1-identities.sh").read_text()
    body = source.split("ensure_bucket() {", 1)[1].split("\n}\n", 1)[0]
    resource = {
        "metadata": {"id": "bucket-test"},
        "spec": {
            "bucket_policy": {"rules": rules},
            "versioning_policy": "enabled",
            "lifecycle_configuration": {"rules": [{
                "status": "enabled",
                "abort_incomplete_multipart_upload": {"days_after_initiation": 1},
            }]},
        },
    }
    harness = """
set -euo pipefail
DEV_BUCKET=development
PROJECT_ID=project-test
die() { printf '%s\\n' "$*" >&2; exit 2; }
lookup_by_name() { printf '%s\\n' "$RESOURCE"; }
json_id() { jq -er '.metadata.id' <<<"$1"; }
nb() { printf 'UNEXPECTED CLOUD MUTATION\\n' >&2; exit 99; }
""" + "ensure_bucket() {" + body + "\n}\n" + """
ensure_bucket "$DEV_BUCKET" "$DESIRED" preserve-superset
printf 'CONTINUED\\n'
"""
    return subprocess.run(
        ["bash", "-c", harness], text=True, capture_output=True, check=False,
        env={**os.environ, "RESOURCE": json.dumps(resource), "DESIRED": json.dumps([VIEWER])},
    )


@pytest.mark.parametrize("rules", [[VIEWER], [VIEWER, PREPARATION], [PREPARATION, VIEWER]])
def test_approved_rules_are_preserved_without_cloud_mutation(rules: list[dict]) -> None:
    result = reconcile(rules)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "bucket-test\nCONTINUED\n"
    assert "UNEXPECTED CLOUD MUTATION" not in result.stderr


@pytest.mark.parametrize("extra", [
    {**PREPARATION, "group_id": "unknown-group"},
    {**PREPARATION, "paths": ["*"]},
    {**PREPARATION, "paths": ["data/public-sample-v1/*", "releases/*"]},
    {**PREPARATION, "roles": ["storage.admin"]},
    {**PREPARATION, "roles": ["storage.object-editor", "storage.viewer"]},
    {**PREPARATION, "condition": "unrecognized"},
    {**VIEWER, "paths": ["data/*"]},
    None,
    "invalid",
])
def test_unknown_grants_stop_reconciliation(extra: object) -> None:
    result = reconcile([VIEWER, extra])
    assert result.returncode != 0
    assert "CONTINUED" not in result.stdout
    assert "UNEXPECTED CLOUD MUTATION" not in result.stderr


@pytest.mark.parametrize("rules", [[], [PREPARATION], None, {}, {"rule": VIEWER}])
def test_missing_or_malformed_required_viewer_stops_reconciliation(rules: object) -> None:
    result = reconcile(rules)
    assert result.returncode != 0
    assert "CONTINUED" not in result.stdout
