import json
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.holdout_spec import G8_PREFIX, object_location  # noqa: E402
from app.ml.transformer.holdout_worker import execute  # noqa: E402
from app.ml.transformer.normalization import fit_normalization  # noqa: E402
from app.ml.transformer.verification_spec import canonical, digest  # noqa: E402
from transformer_holdout_fixtures import FakeS3, reference, request  # noqa: E402
from transformer_input_fixtures import make_inputs  # noqa: E402


def prepared(tmp_path, monkeypatch):
    source = tmp_path / "source"
    data = DevelopmentInputs.open(**make_inputs(source))
    normalizer = fit_normalization(data)
    records = {"development-tabular.json": (source / "tabular.json").read_bytes(),
        "development-sequences.json": (source / "sequence.json").read_bytes(),
        **{name: (source / name).read_bytes() for name in
           ("train.parquet", "validation.parquet", "train-sequences.parquet", "validation-sequences.parquet")},
        "contract.json": data.contract.canonical_bytes(), "normalization.json": normalizer.canonical_bytes(),
        "selected.pt": b"declared non-model bytes", "selection.json": canonical({"result": {"bindings": {}}})}
    items = [reference(name, raw, "development", "s3://fixture/development/" + name)
             for name, raw in records.items()]
    artifacts = SimpleNamespace(**{name: next(item.reference for item in items if item.path == path)
        for name, path in (("contract", "contract.json"), ("normalization", "normalization.json"),
                           ("checkpoint", "selected.pt"), ("selection_verification", "selection.json"))})
    release = SimpleNamespace(artifacts=artifacts, require_research_inference=lambda: None)
    monkeypatch.setattr("app.ml.transformer.holdout_worker.load_release", lambda *a, **k: release)
    final = [reference("tabular.json", b"no final read"), reference("sequence.json", b"no final read"),
             reference("baseline.parquet", b"no final read", uri=G8_PREFIX + "predictions.parquet")]
    package = canonical({"settings": "{}", "evidence": {}})
    req, envelope, _, saved = request(items + final, package_sha256=digest(package))
    records["reference.json"] = saved
    s3 = FakeS3()
    for item in req.inputs:
        if item.scope == "development":
            s3.objects[object_location(item.reference)] = records[item.path]
    return req, envelope, package, s3


class DeclaredParityFailure:
    """No Torch or learned model: intentionally incorrect declared output."""
    def __init__(self, *args, **kwargs):
        pass

    def infer(self, *args, **kwargs):
        return ("a" * 64,), (1,), np.asarray([10.])


def test_failed_parity_stops_final_gets_and_success(tmp_path, monkeypatch):
    req, envelope, package, s3 = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="parity failed"):
        execute(s3, req, package, envelope, approved_request_sha256=req.sha256(),
            trusted_public_key=req.context_public_key, work=tmp_path / "work",
            source_commit=req.source_commit, consumer_factory=DeclaredParityFailure)
    approved = {object_location(item.reference) for item in req.inputs if item.scope == "development"}
    assert all((args["Bucket"], args["Key"]) in approved for kind, args in s3.calls
               if kind == "get" and args["Bucket"] != req.output_bucket)
    writes = [args["Key"] for kind, args in s3.calls if kind == "put"]
    assert writes[-1].endswith("/FAILED")
    assert not any(key.endswith("/SUCCESS") for key in writes)
    failed = json.loads(s3.objects[(req.output_bucket, writes[-1])])
    assert failed["stage"] == "reference_parity"


@pytest.mark.parametrize("defect", ["approval", "source", "package", "key", "signature"])
def test_admission_failure_has_zero_io(tmp_path, monkeypatch, defect):
    req, envelope, package, s3 = prepared(tmp_path, monkeypatch)
    args = dict(approved_request_sha256=req.sha256(), trusted_public_key=req.context_public_key,
                work=tmp_path / "work", source_commit=req.source_commit)
    if defect == "approval":
        args["approved_request_sha256"] = "0" * 64
    elif defect == "source":
        args["source_commit"] = "0" * 40
    elif defect == "package":
        package += b" "
    elif defect == "key":
        args["trusted_public_key"] = "0" * 64
    else:
        envelope["signature"] = "0" * 128
    with pytest.raises(Exception):
        execute(s3, req, package, envelope, **args, consumer_factory=DeclaredParityFailure)
    assert s3.calls == []
    assert not (tmp_path / "work").exists()
