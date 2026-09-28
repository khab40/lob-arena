import json
from pathlib import Path
import shutil
import subprocess

import pytest

pytest.importorskip("numpy")
from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from app.ml.transformer.verification_context import validate_request, verify_context  # noqa: E402
from app.ml.transformer.verification_measure import measure, verify_parity  # noqa: E402
from app.ml.transformer.verification_runner import execute, run_cases  # noqa: E402
from app.ml.transformer.verification_spec import INVENTORY_SHA, RUN_ID, canonical, digest  # noqa: E402
from transformer_input_fixtures import make_inputs  # noqa: E402
from test_transformer_verification_transport import INVENTORY, Store  # noqa: E402


def request_and_key():
    key = Ed25519PrivateKey.generate()
    return {"schema_version": "transformer_input_execution_v1", "run_id": RUN_ID,
        "source_commit": "1" * 40, "image_digest": "sha256:" + "2" * 64,
        "inventory_sha256": INVENTORY_SHA, "context_public_key": key.public_key().public_bytes_raw().hex(),
        "nonce": "3" * 32}, key


def test_signed_job_context_binds_request_and_rejects_mutation():
    request, key = request_and_key()
    validate_request(request, "1" * 40)
    context = {"request_sha256": digest(canonical(request)), "job_id": "aijob-fixture",
               "job_name": RUN_ID, "image_digest": request["image_digest"], "nonce": request["nonce"]}
    envelope = {"context": context, "signature": key.sign(canonical(context)).hex()}
    assert verify_context(envelope, request) == context
    context["job_id"] = "aijob-different"
    with pytest.raises(InvalidSignature):
        verify_context(envelope, request)
    with pytest.raises(ValueError):
        validate_request(request, "4" * 40)
    with pytest.raises(ValueError):
        validate_request({**request, "run_id": "final"}, "1" * 40)


def test_measurement_matches_inert_contract_and_rejects_parity_drift(tmp_path):
    inputs = tmp_path / "inputs"
    args = make_inputs(inputs / "artifacts")
    manifests = inputs / "manifests"
    manifests.mkdir()
    root = args["root"].canonical_bytes()
    (manifests / "frozen-root.json").write_bytes(root)
    shutil.copyfile(args["tabular_path"], manifests / "tabular-projection.json")
    shutil.copyfile(args["sequence_path"], manifests / "sequence-projection.json")
    records, directories = [], []
    for size in (16, 64, 256):
        target = tmp_path / str(size)
        records.append(measure(inputs, target, root_sha=digest(root), tabular_sha=args["tabular_sha256"],
            sequence_sha=args["sequence_sha256"], expected_rows={"train": 4, "validation": 4}, size=size))
        directories.append(target)
    verify_parity(records, directories)
    normalizer = json.loads((directories[0] / "normalization.json").read_bytes())
    assert normalizer["fitting_rows"] == 4
    assert records[0]["fold_rows"] == {"train": 4, "validation": 4}
    records[-1]["logical_output_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="parity"):
        verify_parity(records, directories)


def test_child_timeout_stops_case_sequence_without_retry(tmp_path, monkeypatch):
    calls = []
    def timeout(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 600
        raise subprocess.TimeoutExpired(command, 600)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        run_cases(tmp_path / "inputs", tmp_path)
    assert len(calls) == 1


def test_download_failure_publishes_only_bounded_failure(tmp_path, monkeypatch):
    import app.ml.transformer.verification_runner as runner
    request, _ = request_and_key()
    s3 = Store()
    monkeypatch.setattr(runner, "wait_context", lambda *_: {"job_id": "aijob-fixture"})
    def reject(*_):
        raise ValueError("changed input")
    monkeypatch.setattr(runner, "download", reject)
    monkeypatch.setattr(runner, "run_cases", lambda *_: pytest.fail("measurement reached"))
    with pytest.raises(ValueError):
        execute(s3, request, INVENTORY, "1" * 40, tmp_path / "work")
    assert [Path(k).name for k in s3.objects] == ["INTENT", "FAILED"]
    assert json.loads(s3.puts[-1]["Body"])["automatic_retry"] is False


def test_publication_error_does_not_append_conflicting_failure(tmp_path, monkeypatch):
    import app.ml.transformer.verification_runner as runner
    request, _ = request_and_key()
    first = tmp_path / "case"
    first.mkdir()
    for name in ("normalization.json", "input-contract.json"):
        (first / name).write_bytes(b"{}")
    monkeypatch.setattr(runner, "wait_context", lambda *_: {"job_id": "aijob-fixture"})
    monkeypatch.setattr(runner, "download", lambda *_: {})
    monkeypatch.setattr(runner, "run_cases", lambda *_: ([], first))
    s3 = Store()
    s3.fail_put = 3
    with pytest.raises(ValueError):
        execute(s3, request, INVENTORY, "1" * 40, tmp_path / "work")
    assert not any(Path(k).name in ("SUCCESS", "FAILED") for k in s3.objects)
