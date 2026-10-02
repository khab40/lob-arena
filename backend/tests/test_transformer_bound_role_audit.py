"""Inert adapter seam tests, never reading governed payloads or running models."""
import json
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import role_audit as a  # noqa: E402
from test_transformer_role_rows import fixture  # noqa: E402


@pytest.fixture
def package_seams(monkeypatch):
    windows, metadata = fixture()
    calls = []
    contract = NS(canonical_bytes=lambda: b'{"inert":"contract"}')
    normalizer = b'{"inert":"original normalizer bytes"}'
    binding = {"source_receipt_sha256": "a" * 64, "source_separation_verified": True}

    def authenticate(bundle, source):
        calls.append("authenticate")
        assert (bundle, source) == (b"bundle", b"source")
        return metadata, contract, normalizer, binding

    def open_adapter(**_):
        calls.append("payload")
        return NS(contract=contract, windows=lambda fold: iter(windows) if fold == "validation" else None)

    monkeypatch.setattr(a, "authenticate", authenticate)
    monkeypatch.setattr(a, "load_metadata", lambda _: (None, None, None))
    monkeypatch.setattr(a, "metadata_plan", lambda *_: metadata)
    monkeypatch.setattr(a, "DevelopmentInputs", NS(open=open_adapter))
    return calls, metadata, normalizer


def test_source_authenticated_before_payload_and_frozen_bytes_preserved(package_seams, tmp_path):
    calls, _, normalizer = package_seams
    artifacts = a.audit_package(tmp_path, b"bundle", b"source")
    assert calls == ["authenticate", "payload"]
    assert artifacts["normalization.json"] == normalizer
    result = a.verify_package(artifacts, b"bundle", b"source")
    assert result["class_support_passed"] and result["source_binding"]["source_separation_verified"]
    assert result["gpu_ready"] is False and result["model_runs"] == 0
    assert result["blockers"] == ["platform_readiness_required", "exact_execution_authorization_required"]
    assert result["independent_readback_scope"] == "target_identity_coverage_and_class_count_arithmetic"


def test_rejected_source_never_opens_payload(package_seams, tmp_path, monkeypatch):
    calls, _, _ = package_seams

    def reject(*_):
        raise ValueError("altered source receipt")

    monkeypatch.setattr(a, "authenticate", reject)
    with pytest.raises(ValueError, match="altered source"):
        a.audit_package(tmp_path, b"bundle", b"source")
    assert calls == []


def test_changed_manifest_never_opens_payload(package_seams, tmp_path, monkeypatch):
    calls, _, _ = package_seams
    monkeypatch.setattr(a, "metadata_plan", lambda *_: {"changed": True})
    with pytest.raises(ValueError, match="downloaded manifests"):
        a.audit_package(tmp_path, b"bundle", b"source")
    assert calls == ["authenticate"]


@pytest.mark.parametrize("defect", ["aggregate", "normalizer", "contract", "missing", "extra", "label"])
def test_independent_readback_rejects_changed_artifacts(package_seams, tmp_path, defect):
    artifacts = a.audit_package(tmp_path, b"bundle", b"source")
    if defect == "aggregate":
        value = json.loads(artifacts["role-audit.json"])
        value["roles"]["selection"]["positive_rows"] += 1
        artifacts["role-audit.json"] = a.canonical(value)
    elif defect in ("normalizer", "contract"):
        artifacts["normalization.json" if defect == "normalizer" else "input-contract.json"] += b" "
    elif defect == "missing":
        artifacts.pop("target-ledger.jsonl")
    elif defect == "extra":
        artifacts["extra"] = b"unbound"
    else:
        rows = [json.loads(line) for line in artifacts["target-ledger.jsonl"].splitlines()]
        rows[0]["label"] = 1 - rows[0]["label"]
        artifacts["target-ledger.jsonl"] = b"".join(a.canonical(row) + b"\n" for row in rows)
    with pytest.raises(ValueError):
        a.verify_package(artifacts, b"bundle", b"source")


def test_insufficient_support_publishes_verifiable_negative_audit(package_seams, tmp_path, monkeypatch):
    _, _, normalizer = package_seams
    windows, _ = fixture(19)
    contract = NS(canonical_bytes=lambda: b'{"inert":"contract"}')
    monkeypatch.setattr(a, "DevelopmentInputs", NS(open=lambda **_: NS(
        contract=contract, windows=lambda _: iter(windows))))
    artifacts = a.audit_package(tmp_path, b"bundle", b"source")
    result = a.verify_package(artifacts, b"bundle", b"source")
    assert result["class_support_passed"] is False
    assert "insufficient_class_support" in result["blockers"]
    assert artifacts["normalization.json"] == normalizer
    assert result["row_count"] == 120 and not result["gpu_ready"]
