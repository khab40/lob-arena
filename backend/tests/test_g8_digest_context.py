"""Inert signed-context checks: no model fixtures or runtime execution."""
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("mlflow")

from app.ml.lightgbm.cloud_contracts import Wave1ExecutionContext  # noqa: E402
from serverless.jobs import run_lightgbm_g8_replacement as runner  # noqa: E402


IMAGE = "registry.example/jobs@sha256:" + "a" * 64


@pytest.fixture
def signed_context(tmp_path):
    private = tmp_path / "private.pem"
    public = tmp_path / "authorization-public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private)],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                   check=True, capture_output=True)
    (tmp_path / "contexts").mkdir()
    plan = SimpleNamespace(run_id="inert", mount_path=str(tmp_path), image=IMAGE,
                           filesystem_id="computefilesystem-inert", identity=lambda: "b" * 64)
    context = Wave1ExecutionContext(project_id="project-e00g6zvxpr00waz8t3y51k", image=IMAGE,
                                    nebius_job_id="aijob-inert")
    observed = {"metadata": {"id": context.nebius_job_id}, "spec": {"image": IMAGE}}
    raw = dict(execution_package_sha256=plan.identity(), filesystem_id=plan.filesystem_id,
               context=context.model_dump(mode="json"), purpose="execute")

    def verify(change=None, *, recovery=False):
        envelope = {**raw, "job_readback_json": json.dumps(observed)}
        if recovery:
            envelope["purpose"] = "recover"
        envelope["job_readback_sha256"] = hashlib.sha256(envelope["job_readback_json"].encode()).hexdigest()
        if change:
            change(envelope)
        path = tmp_path / "contexts" / ("inert-recovery.json" if recovery else "inert.json")
        path.write_text(json.dumps(envelope))
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(private), "-rawin",
                        "-in", str(path), "-out", str(path.with_suffix(".sig"))],
                       check=True, capture_output=True)
        return runner.observed_context(plan, tmp_path, hashlib.sha256(public.read_bytes()).hexdigest(),
                                       recovery=recovery)
    return verify, observed, context


@pytest.mark.parametrize("recovery", [False, True])
def test_matching_actual_digest_context_is_accepted(signed_context, recovery):
    verify, _, context = signed_context
    assert verify(recovery=recovery) == context


@pytest.mark.parametrize("image", ["registry.example/jobs:latest", "registry.example/jobs@sha256:" + "c" * 64, None])
def test_alias_wrong_or_missing_actual_digest_is_rejected(signed_context, image):
    verify, observed, _ = signed_context
    observed["spec"]["image"] = image
    with pytest.raises(ValueError, match="actual Job identity/image"):
        verify()


def test_another_job_id_is_rejected(signed_context):
    verify, observed, _ = signed_context
    observed["metadata"]["id"] = "aijob-other"
    with pytest.raises(ValueError, match="actual Job identity/image"):
        verify()


@pytest.mark.parametrize("change", [
    lambda raw: raw.pop("job_readback_json"),
    lambda raw: raw.update(job_readback_sha256="0" * 64),
    lambda raw: raw["context"].update(image="registry.example/jobs@sha256:" + "d" * 64),
])
def test_legacy_unbound_or_inconsistent_context_fails(signed_context, change):
    verify, _, _ = signed_context
    with pytest.raises(ValueError):
        verify(change)
