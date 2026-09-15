"""Static signing protocol tests; no Job, filesystem or model workload is started."""
from copy import deepcopy
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
    job_file = tmp_path / "job.json"
    job_file.write_bytes(contract.canonical(readback))
    output = tmp_path / "score"
    kwargs = dict(package=root, readback=job_file, job_id="aijob-example", phase="score",
                  private_key=tmp_path / "reviewer.pem", output=output)
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
    readback["spec"]["args"] = "/job/g8/run_g8_native_rehearsal.py --phase recover"
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
