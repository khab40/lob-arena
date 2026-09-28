import io
import json

import pytest

pytest.importorskip("numpy")
from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.normalization import fit_normalization  # noqa: E402
from app.ml.transformer.verification_readback import collect, verify_artifacts  # noqa: E402
from app.ml.transformer.verification_spec import INVENTORY_SHA, canonical, digest  # noqa: E402
from test_transformer_verification_runner import request_and_key  # noqa: E402
from transformer_input_fixtures import make_inputs  # noqa: E402


def fixture_package(tmp_path, monkeypatch):
    import app.ml.transformer.verification_readback as reader
    args = make_inputs(tmp_path)
    dataset = DevelopmentInputs.open(**args)
    norm = fit_normalization(dataset)
    monkeypatch.setattr(reader, "TABULAR_SHA", args["tabular_sha256"])
    monkeypatch.setattr(reader, "SEQUENCE_SHA", args["sequence_sha256"])
    monkeypatch.setattr(reader, "ROOT_IDENTITY_SHA", args["root"].canonical_hash())
    monkeypatch.setattr(reader, "FOLD_ROWS", {"train": 4, "validation": 4})
    request, _ = request_and_key()
    context = {"job_id": "aijob-fixture"}
    metrics = [{"batch_size": b, "fold_rows": {"train": 4, "validation": 4},
                "normalization_sha256": norm.sha256(), "contract_sha256": dataset.contract.sha256(),
                "fold_identity_sha256": {"train": norm.fitting_row_sha256, "validation": "9" * 64},
                "logical_output_sha256": "8" * 64} for b in (16, 64, 256)]
    artifacts = {"configuration.json": canonical(request), "normalization.json": norm.canonical_bytes(),
        "input-contract.json": dataset.contract.canonical_bytes(), "measurements.json": canonical(metrics),
        "inventory-reference.json": canonical({"sha256": INVENTORY_SHA, "objects": 185}),
        "lineage.json": canonical({"context": context, "source_commit": request["source_commit"],
            "model_runs": 0, "scope": "development_input_preparation_only"})}
    return artifacts, request, context


@pytest.mark.parametrize("defect", [None, "normalizer", "rows", "digest", "job", "inventory", "root"])
def test_independent_artifact_checks_reject_inconsistent_package(tmp_path, monkeypatch, defect):
    artifacts, request, context = fixture_package(tmp_path, monkeypatch)
    if defect == "normalizer":
        value = json.loads(artifacts["normalization.json"])
        value["means"][0] += 1
        artifacts["normalization.json"] = canonical(value)
    elif defect in ("rows", "digest"):
        value = json.loads(artifacts["measurements.json"])
        if defect == "rows":
            value[0]["fold_rows"]["validation"] += 1
        else:
            value[1]["logical_output_sha256"] = "0" * 64
        artifacts["measurements.json"] = canonical(value)
    elif defect == "job":
        context["job_id"] = "aijob-another"
    elif defect == "inventory":
        artifacts["inventory-reference.json"] = b"{}"
    elif defect == "root":
        monkeypatch.setattr("app.ml.transformer.verification_readback.ROOT_IDENTITY_SHA", "0" * 64)
    if defect:
        with pytest.raises(ValueError):
            verify_artifacts(artifacts, request, context, "aijob-fixture")
    else:
        assert verify_artifacts(artifacts, request, context, "aijob-fixture")["fold_rows"]["train"] == 4


def test_success_must_match_independently_observed_job_log(tmp_path):
    class Reader:
        def get_object(self, **kwargs):
            assert kwargs["Key"].endswith("/SUCCESS")
            return {"ContentLength": 2, "Body": io.BytesIO(b"{}")}
    request, _ = request_and_key()
    with pytest.raises(ValueError, match="provider Job log"):
        collect(Reader(), request, "aijob-fixture", digest(b"changed"), tmp_path / "readback")
