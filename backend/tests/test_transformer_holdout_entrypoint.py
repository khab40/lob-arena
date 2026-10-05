import time

import pytest

from app.ml.transformer.holdout_entrypoint import context_key, run, wait_context
from app.ml.transformer.holdout_runtime import encode_request
from app.ml.transformer.holdout_spec import G8_PREFIX
from app.ml.transformer.holdout_storage import HoldoutStore
from app.ml.transformer.verification_spec import canonical, digest
from transformer_holdout_fixtures import FakeS3, reference, request


def startup(tmp_path):
    package = b"declared evidence, no weights"
    req, envelope, *_ = request([
        reference("tabular.json", b"metadata"), reference("sequence.json", b"metadata"),
        reference("baseline.parquet", b"metadata", uri=G8_PREFIX + "predictions.parquet")],
        package_sha256=digest(package))
    (tmp_path / "source-commit").write_text(req.source_commit)
    (tmp_path / "portable-package.json").write_bytes(package)
    path = tmp_path / "request.gz"
    path.write_bytes(encode_request(req))
    s3 = FakeS3()
    s3.objects[(req.output_bucket, context_key(req))] = canonical(envelope)
    env = {"HOLDOUT_APPROVED_REQUEST_SHA256": req.sha256(),
           "HOLDOUT_TRUSTED_PUBLIC_KEY": req.context_public_key}
    return req, envelope, path, s3, env


@pytest.mark.parametrize("defect", ["approval", "key", "source", "package", "runtime"])
def test_failed_startup_never_constructs_client_or_consumer(tmp_path, defect):
    _, _, path, _, env = startup(tmp_path)
    if defect in ("approval", "key"):
        del env["HOLDOUT_APPROVED_REQUEST_SHA256" if defect == "approval" else "HOLDOUT_TRUSTED_PUBLIC_KEY"]
    elif defect == "source":
        (tmp_path / "source-commit").write_text("0" * 40)
    elif defect == "package":
        (tmp_path / "portable-package.json").write_bytes(b"changed")
    def inspect(root):
        if defect == "runtime":
            raise ValueError("changed dependencies")
    def never():
        pytest.fail("client constructed before admission")
    with pytest.raises(ValueError):
        run(tmp_path, path, env=env, inspect=inspect, client_factory=never)


@pytest.mark.parametrize("defect", [None, "signature", "nonce", "noncanonical"])
def test_context_is_verified_before_consumer_and_shares_execution_budget(tmp_path, defect):
    req, envelope, path, s3, env = startup(tmp_path)
    if defect == "signature":
        envelope["signature"] = "0" * 128
    elif defect == "nonce":
        envelope["context"]["nonce"] = "0" * 32
    raw = canonical(envelope) + (b" " if defect == "noncanonical" else b"")
    s3.objects[(req.output_bucket, context_key(req))] = raw
    called = []
    started = time.monotonic()
    def execute(*args, **kwargs):
        called.append(True)
        store = kwargs["store"]
        assert store.calls == 1 and store.read_bytes == 16385
        assert store.expires <= started + req.timeout_seconds + .1
        assert store.artifacts == {}
        return {"declared": True}
    args = dict(env=env, inspect=lambda root: None, client_factory=lambda: s3, execute_fn=execute)
    if defect:
        with pytest.raises(Exception):
            run(tmp_path, path, **args)
        assert not called
    else:
        assert run(tmp_path, path, **args) == {"declared": True}
        assert not context_key(req).startswith(req.output_prefix)
    assert [kind for kind, _ in s3.calls] == ["get"]  # No final input or result write.


def test_missing_context_is_bounded_and_does_not_write_or_infer(tmp_path):
    req, _, _, s3, _ = startup(tmp_path)
    class Missing(Exception):
        response = {"Error": {"Code": "NoSuchKey"}}
    s3.get_object = lambda **args: (_ for _ in ()).throw(Missing())
    store = HoldoutStore(s3, req, expires=time.monotonic() + req.timeout_seconds)
    pauses = []
    with pytest.raises(TimeoutError):
        wait_context(store, pause=pauses.append)
    assert store.calls == 120 and pauses == [5] * 120
    assert not store.artifacts and store.written == 0
