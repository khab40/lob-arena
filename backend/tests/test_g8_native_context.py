"""Static signing protocol tests; no Job, filesystem or model workload is started."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

pytest.importorskip("cryptography")
from scripts import sign_g8_native_context as signer  # noqa: E402
from serverless.jobs import g8_native_contract as contract, g8_native_readback as readbacks  # noqa: E402
import test_g8_native_runtime as runtime_fixtures  # noqa: E402
import test_g8_native_readback as fixtures  # noqa: E402

plan_data, plan, readback = fixtures.plan_data, fixtures.plan, fixtures.readback
package = runtime_fixtures.package


def test_signed_context_binds_job_and_requires_terminal_original(package, readback, tmp_path, monkeypatch):
    root, trusted, plan = package
    monkeypatch.setattr(signer, "verify_package", lambda *a, **kw: plan)  # Signature checked by runtime tests.
    monkeypatch.setattr(signer, "verify_readback", lambda *a, **kw: readbacks.verify_readback(*a, **kw, now=fixtures.NOW))
    monkeypatch.setattr(signer, "verify_previous_job", lambda *a, **kw: readbacks.verify_previous_job(*a, **kw, now=fixtures.NOW))
    monkeypatch.setattr(signer, "verify_registry", lambda *a, **kw: readbacks.verify_registry(*a, **kw, now=fixtures.NOW))
    job_file = tmp_path / "job.json"
    job_file.write_bytes(contract.canonical(readback))
    output = tmp_path / "score"
    registry_file = tmp_path / "registry.json"
    registry = plan.registry_verification.model_dump(mode="json")
    registry["verified_at"] = fixtures.NOW.isoformat()
    registry_file.write_bytes(contract.canonical(registry))
    kwargs = dict(package=root, readback=job_file, job_id="aijob-example", phase="score",
                  private_key=tmp_path / "reviewer.pem", output=output, registry_verification=registry_file)
    receipt = signer.sign_context(**kwargs)
    assert receipt["secret_version_selectors_verified"]
    content = (output / "score.json").read_bytes()
    signer.signed(content, (output / "score.sig").read_bytes(), (root / "reviewer-public.pem").read_bytes(), trusted)
    assert json.loads(content)["execution_package_sha256"] == plan.identity()
    with pytest.raises(FileExistsError):
        signer.sign_context(**kwargs)
    previous = deepcopy(readback)
    previous["status"] = {"state": "FAILED", "finished_at": fixtures.NOW.isoformat()}
    previous_file = tmp_path / "terminal.json"
    previous_file.write_bytes(contract.canonical(previous))
    readback["metadata"].update(id="aijob-recovery", name="g8-native-20260915-recover")
    readback["spec"]["args"] = "/job/g8/g8_native_bootstrap.py --phase recover"
    job_file.write_bytes(contract.canonical(readback))
    kwargs.update(phase="recover", job_id="aijob-recovery", output=tmp_path / "recover",
                  original_context=output / "score.json", previous_terminal=previous_file)
    assert signer.sign_context(**kwargs)["job_id"] == "aijob-recovery"
    previous["status"]["state"] = "RUNNING"
    previous_file.write_bytes(contract.canonical(previous))
    kwargs["output"] = tmp_path / "rejected"
    with pytest.raises(ValueError, match="terminal"):
        signer.sign_context(**kwargs)
    assert not kwargs["output"].exists()


def test_terminal_timestamp_and_same_job_cannot_prove_reattachment(plan, readback):
    original = {"execution_package_sha256": plan.identity(), "phase": "score", "job_id": "aijob-example",
                "readback": deepcopy(readback)}
    readback["status"] = {"state": "FAILED", "finished_at": "2020-01-01T00:00:00+00:00"}
    with pytest.raises(ValueError, match="time"):
        readbacks.verify_previous_job(plan, original, readback, recovery_job_id="aijob-recovery", now=fixtures.NOW)
    readback["status"]["finished_at"] = fixtures.NOW.isoformat()
    with pytest.raises(ValueError):
        readbacks.verify_previous_job(plan, original, readback, recovery_job_id="aijob-example", now=fixtures.NOW)


@pytest.mark.parametrize("change", ["digest", "alias", "before-create", "future", "stale"])
def test_registry_context_rejects_drift_and_wrong_observation_time(plan, change):
    receipt = plan.registry_verification.model_dump(mode="json")
    receipt["verified_at"] = fixtures.NOW.isoformat()
    created = (fixtures.NOW - timedelta(minutes=1)).isoformat()
    if change == "digest":
        receipt["resolved_digest"] = "sha256:" + "a" * 64
    elif change == "alias":
        receipt["deployment_image"] = "registry.example/other:latest"
    elif change == "before-create":
        receipt["verified_at"] = (fixtures.NOW - timedelta(minutes=2)).isoformat()
    elif change == "future":
        receipt["verified_at"] = (fixtures.NOW + timedelta(seconds=1)).isoformat()
    else:
        created = (fixtures.NOW - timedelta(minutes=10)).isoformat()
        receipt["verified_at"] = (fixtures.NOW - timedelta(minutes=6)).isoformat()
    with pytest.raises(ValueError):
        readbacks.verify_registry(receipt, created_at=created, now=fixtures.NOW)


def test_recovery_children_reuse_signed_post_creation_registry_observation(plan):
    receipt = plan.registry_verification.model_dump(mode="json")
    receipt["verified_at"] = fixtures.NOW.isoformat()
    assert readbacks.verify_registry(receipt, created_at=fixtures.NOW.isoformat(),
                                    now=fixtures.NOW + timedelta(minutes=20), fresh=False)
