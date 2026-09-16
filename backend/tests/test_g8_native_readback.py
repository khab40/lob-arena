"""Static native contract/readback checks; no model imports or cloud calls."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args, get_origin

import pytest

from serverless.jobs import g8_native_contract as contract
from serverless.jobs.g8_native_readback import verify_readback

NOW = datetime(2026, 9, 15, 13, tzinfo=UTC)


@pytest.fixture
def plan_data():
    values = {name: get_args(field.annotation)[0] for name, field in contract.NativePlan.model_fields.items()
              if get_origin(field.annotation) is Literal}
    values.update(source_commit="1" * 40, filesystem_id="computefilesystem-example", verified_at=NOW - timedelta(minutes=5),
        registry_verification={"deployment_image": contract.DEPLOYMENT_IMAGE, "expected_digest": contract.IMAGE_DIGEST,
                               "resolved_digest": contract.IMAGE_DIGEST, "manifest_sha256": "b" * 64,
                               "verified_at": NOW - timedelta(minutes=5)},
        secret_selectors={**contract.S3_SELECTORS,
            "MLFLOW_TRACKING_USERNAME": "mbsec-exampleuser@mbsecver-exampleuser",
            "MLFLOW_TRACKING_PASSWORD": "mbsec-examplepassword@mbsecver-examplepassword"},
        files={name: {"sha256": "a" * 64, "size_bytes": 1}
               for name in set(contract.CODE_PATHS) | contract.CAPSULE | set(contract.ARCHIVES)
               | {contract.BOOTSTRAP, "reviewer-public.pem", "filesystem.json"}})
    return values


@pytest.fixture
def plan(plan_data):
    return contract.NativePlan.model_validate(plan_data)


@pytest.fixture
def readback(plan):
    return {
        "metadata": {"id": "aijob-example", "name": "g8-native-20260915-score",
                     "parent_id": contract.PROJECT, "created_at": NOW.isoformat()},
        "spec": {
            "image": contract.DEPLOYMENT_IMAGE, "container_command": "python",
            "args": "/job/g8/g8_native_bootstrap.py --phase score",
            "platform": "cpu-d3", "preset": "4vcpu-16gb", "subnet_id": contract.SUBNET,
            "timeout": "3600s", "disk": {"type": "NETWORK_SSD", "size_bytes": "107374182400"},
            "volumes": [{"source": plan.filesystem_id, "container_path": "/g8-durable", "mode": "READ_WRITE"}],
            # Ordinary API views omit injected content but retain plain settings.
            "injected_files": [{"container_path": p} for p in contract.injections(plan)],
            "environment_variables": [{"name": k, "value": v} for k, v in contract.environment(plan).items()] + [
                {"name": k, "mysterybox_secret": {"secret_id": s.split("@")[0], "version_id": s.split("@")[1]}}
                for k, s in plan.secret_selectors.items()],
        }, "status": {"state": "RUNNING", "instances": [{"private_ip": "10.4.0.1"}]},
    }


def check(plan, readback):
    return verify_readback(plan, readback, phase="score", expected_job_id="aijob-example", now=NOW)


def test_normal_redaction_does_not_claim_runtime_bytes(plan, readback):
    result = check(plan, readback)
    assert result["secret_version_selectors_verified"] and result["injected_file_paths_verified"]
    assert result["plain_environment_configuration_verified"]
    assert not result["injected_file_bytes_verified"] and not result["runtime_environment_verified"]
    assert not result["native_storage_verified"] and not result["remote_mlflow_verified"]
    readback["spec"].update(restart_attempts="0", public_ip=False, preemptible=False)
    assert check(plan, readback)["job_id"] == "aijob-example"


@pytest.mark.parametrize("change", ["missing", "wrong", "redacted"])
def test_plain_environment_requires_actual_reviewed_configuration(plan, readback, change):
    entry = next(v for v in readback["spec"]["environment_variables"] if v["name"] == "AWS_DEFAULT_REGION")
    if change == "missing":
        del entry["value"]
    else:
        entry["value"] = "us-east-1" if change == "wrong" else "[REDACTED]"
    with pytest.raises(ValueError, match="Job plain environment differs"):
        check(plan, readback)


@pytest.mark.parametrize("key,value", [
    ("image", "registry.example/jobs:latest"), ("timeout", "7200s"), ("preset", "8vcpu-32gb"),
    ("restart_attempts", "1"), ("restart_attempts", "-1"), ("public_ip", True),
    ("ssh_authorized_keys", ["ssh-ed25519 example"]), ("preemptible", True),
    ("working_dir", "/tmp"), ("ports", [{"container_port": 5500}]),
    ("registry_credentials", {"mysterybox_secret_version": "mbsecver-other"}),
    ("shm_size_bytes", "1073741824"), ("unknown_option", "unreviewed"),
])
def test_configuration_drift_rejected(plan, readback, key, value):
    readback["spec"][key] = value
    with pytest.raises(ValueError):
        check(plan, readback)


@pytest.mark.parametrize("change", ["version", "missing-version", "inline", "duplicate"])
def test_secret_binding_requires_exact_id_and_version(plan, readback, change):
    env = readback["spec"]["environment_variables"]
    secret = next(v for v in env if v["name"] == "AWS_SECRET_ACCESS_KEY")
    if change == "version":
        secret["mysterybox_secret"]["version_id"] = "mbsecver-other"
    elif change == "missing-version":
        del secret["mysterybox_secret"]["version_id"]
    elif change == "inline":
        secret["value"] = "example-only"
    else:
        env.append(deepcopy(secret))
    with pytest.raises(ValueError):
        check(plan, readback)


@pytest.mark.parametrize("change", ["wrong-fs", "s3", "subdir", "extra-mount", "missing-file", "duplicate-file"])
def test_mount_and_injection_identity_drift_rejected(plan, readback, change):
    volume = readback["spec"]["volumes"][0]
    if change == "wrong-fs":
        volume["source"] = "computefilesystem-other"
    elif change == "s3":
        volume["source"] = "s3://example"
    elif change == "subdir":
        volume["source_path"] = "/other"
    elif change == "extra-mount":
        readback["spec"]["volumes"].append(deepcopy(volume))
    elif change == "missing-file":
        readback["spec"]["injected_files"].pop()
    else:
        readback["spec"]["injected_files"].append(readback["spec"]["injected_files"][0])
    with pytest.raises(ValueError):
        check(plan, readback)


def test_old_job_wrong_phase_and_future_context_rejected(plan, readback):
    with pytest.raises(ValueError):
        verify_readback(plan, readback, phase="recover", expected_job_id="aijob-example", now=NOW)
    with pytest.raises(ValueError):
        verify_readback(plan, readback, phase="score", expected_job_id="aijob-other", now=NOW)
    with pytest.raises(ValueError):
        verify_readback(plan, readback, phase="score", expected_job_id="aijob-example", now=NOW - timedelta(seconds=1))


def test_plan_rejects_production_candidate_and_unbounded_resources(plan_data):
    for key, value in (("candidate_sha256", "5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff"),
                       ("maximum_jobs", 3), ("maximum_additional_cost_usd", 3), ("capacity_gib", 100),
                       ("production_final_test_authorized", True), ("campaign_spend_usd", 40)):
        with pytest.raises(ValueError):
            contract.NativePlan.model_validate({**plan_data, key: value})


def test_commands_pin_each_secret_version_and_only_one_native_mount(plan, tmp_path):
    command = contract.job_command(plan, tmp_path, phase="recover")
    assert command.count("--inject-file") == 16
    assert command[command.index("--args") + 1] == "/job/g8/g8_native_bootstrap.py --phase recover"
    assert not any(p.endswith("/g8_native_lifecycle.py") for p in contract.injections(plan))
    assert command.count("--volume") == 1
    assert command[command.index("--volume") + 1] == plan.filesystem_id + ":/g8-durable:rw"
    assert command[command.index("--restart-policy") + 1] == "never"
    assert command[command.index("--image") + 1] == contract.DEPLOYMENT_IMAGE
    assert len(contract.DEPLOYMENT_IMAGE) <= 64 and plan.image == contract.IMAGE
    assert {command[i + 1] for i, v in enumerate(command) if v == "--env-secret"} == {
        f"{k}={v}" for k, v in plan.secret_selectors.items()}


def test_transport_bound_does_not_limit_uncompressed_code(plan_data):
    plan_data["files"][next(iter(contract.CODE_PATHS))]["size_bytes"] = 65536
    contract.NativePlan.model_validate(plan_data)
    plan_data["files"]["native-code-2.zip"]["size_bytes"] = 40961
    with pytest.raises(ValueError, match="40 KiB"):
        contract.NativePlan.model_validate(plan_data)


def test_delayed_submission_readback_keeps_identity_checks(plan, readback):
    delayed = NOW + timedelta(days=7)
    readback["metadata"]["created_at"] = delayed.isoformat()
    assert verify_readback(plan, readback, phase="score", expected_job_id="aijob-example",
                           now=delayed)["job_id"] == "aijob-example"
    readback["spec"]["image"] = "unreviewed"
    with pytest.raises(ValueError, match="configuration"):
        verify_readback(plan, readback, phase="score", expected_job_id="aijob-example", now=delayed)
