"""Metadata-only resource and command checks; no model or evaluation execution."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ml.lightgbm.cloud_contracts import (
    APPROVED_FIXTURE_FEATURE_RELEASE_SHA256, LightGbmCloudJobRequest,
    Wave1ExecutionContext, Wave1ResourceRequest,
)


def request(mode="final-evaluation", timeout=10800):
    data = dict(campaign_id="inert", run_id="inert", mode=mode,
        project_id="project-e00g6zvxpr00waz8t3y51k", created_at=datetime.now(timezone.utc),
        image="registry.example/inert@sha256:" + "a" * 64, git_commit="b" * 40,
        input={"kind": "approved-research-fixture", "feature_release_sha256": APPROVED_FIXTURE_FEATURE_RELEASE_SHA256},
        result_uri="file:///inert", resource={"timeout_seconds": timeout})
    if mode == "final-evaluation":
        data.update({n: {"logical_name": n, "uri": n + ".json", "sha256": "c" * 64, "size_bytes": 1}
                     for n in ("candidate", "authorization", "authorization_signature", "authorization_public_key")})
    return LightGbmCloudJobRequest.model_validate(data)


@pytest.mark.parametrize("timeout", [3600, 10800])
def test_reviewed_final_windows_and_actual_context(timeout):
    value = request(timeout=timeout)
    context = Wave1ExecutionContext(project_id=value.project_id, image=value.image, timeout_seconds=timeout)
    assert context.timeout_seconds == value.resource.timeout_seconds


@pytest.mark.parametrize("mode", ["development", "preflight", "verify"])
def test_other_modes_retain_one_hour_ceiling(mode):
    with pytest.raises(ValueError, match="only authorized final"):
        request(mode)
    assert request(mode, 3600).resource.timeout_seconds == 3600


@pytest.mark.parametrize("timeout", [59, 60, 1800, 3599, 3601, 7200, 10801, 14400])
def test_unsupported_windows_are_rejected_before_signing(timeout):
    with pytest.raises(ValueError):
        Wave1ResourceRequest(timeout_seconds=timeout)


def test_published_resource_schema_matches_context_windows():
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "contracts/lightgbm-cloud-job-v1.schema.json").read_text())
    timeout = schema["$defs"]["Wave1ResourceRequest"]["properties"]["timeout_seconds"]
    context = Wave1ExecutionContext.model_json_schema()["properties"]["timeout_seconds"]
    assert timeout["enum"] == context["enum"] == [3600, 10800]
    assert timeout["default"] == context["default"] == 3600


def renderer():
    source = Path(__file__).resolve().parents[1] / "app/ml/lightgbm/g8_replacement.py"
    function = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "job_command")
    namespace = dict(Path=Path, ReplacementPlan=object, LightGbmCloudJobRequest=LightGbmCloudJobRequest,
        sha256_file=lambda p: hashlib.sha256(p.read_bytes()).hexdigest(), SHA=r"^[0-9a-f]{64}$",
        DEPLOYMENT_IMAGE="inert", BOOTSTRAP="bootstrap.py", PACKAGE="/g8-package/production", ARCHIVES=())
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["job_command"]


@pytest.mark.parametrize("timeout,expected", [(3600, "1h"), (10800, "3h")])
def test_renderer_binds_timeout_to_request_bytes(tmp_path, timeout, expected):
    value = request(timeout=timeout)
    path = tmp_path / "request.json"
    path.write_bytes(value.canonical_bytes())
    plan = SimpleNamespace(files={"request.json": SimpleNamespace(sha256=hashlib.sha256(path.read_bytes()).hexdigest())},
        request_sha256=value.canonical_hash(), run_id=value.run_id, subnet_id="inert",
        filesystem_id="inert", mount_path="/g8-durable", secret_selectors={})
    command = renderer()(plan, tmp_path, "a" * 64)
    assert command[command.index("--timeout") + 1] == expected
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="package-bound request"):
        renderer()(plan, tmp_path, "a" * 64)
