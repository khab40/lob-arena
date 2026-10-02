"""Receipt authentication tests use inert metadata; no source payloads."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import role_source as s  # noqa: E402
import test_transformer_role_audit_bundle as bundle_tests  # noqa: E402

bundle = bundle_tests.bundle


@pytest.fixture
def evidence(monkeypatch):
    metadata = {"feature_release_id": "fixture", "feature_release_sha256": "a" * 64,
        "groups": [{"role": role, "group_sha256": str(index) * 64,
            "base_sessions": [role], "row_count": 40,
            "source_identity": {"instrument": role, "source_sha256": "b" * 64},
            "shards": [{"run_id": role + "-control"}]} for index, role in enumerate(
                ("selection", "calibration", "operating_point"))]}
    receipt = {"anchor_sha256": s.ANCHOR_SHA,
        "role_metadata_sha256": s.digest(s.canonical(metadata)),
        **{name: metadata[name] for name in ("feature_release_id", "feature_release_sha256")},
        "groups": [{name: group[name] for name in ("role", "group_sha256", "base_sessions", "row_count")}
            | group["source_identity"] | {"run_ids": [group["shards"][0]["run_id"]]}
            for group in metadata["groups"]]}
    receipt.update({name: True for name in ("source_separation_verified",
        "source_observation_separation_verified", "label_horizon_separation_verified")})
    receipt.update({name: "fixture" for name in ("lineage_receipt_sha256", "phase_one_receipts_sha256",
        "phase_two_receipts_sha256", "producer_commit", "producer_image", "proof_method")})
    raw = s.canonical(receipt)
    monkeypatch.setattr(s, "SOURCE_RECEIPT_SHA", s.digest(raw))
    return raw, metadata


def test_exact_receipt_retains_lineage_without_claiming_payload_independence(evidence):
    raw, metadata = evidence
    result = s.verify_source(raw, metadata)
    assert result["source_receipt_sha256"] == s.digest(raw)
    assert result["anchor_sha256"] == s.ANCHOR_SHA and result["source_separation_verified"]
    assert not result["statistical_independence_claimed"]
    assert not result["payload_observation_ids_reenumerated"]


def test_committed_reviewed_receipt_has_the_external_pin():
    path = Path(__file__).resolve().parents[2] / "docs/evidence/transformer-source-separation-receipt-20261002.json"
    assert s.digest(path.read_bytes()) == s.SOURCE_RECEIPT_SHA


@pytest.mark.parametrize("defect", ["changed", "extra_byte", "oversized"])
def test_changed_receipt_fails_before_interpretation(evidence, defect):
    raw, metadata = evidence
    raw = b"invalid" if defect == "changed" else raw + b" "
    if defect == "oversized":
        raw = b"x" * (s.MAX_SOURCE_RECEIPT + 1)
    with pytest.raises(ValueError, match="checksum"):
        s.verify_source(raw, metadata)


@pytest.mark.parametrize("field", ["role", "group_sha256", "base_sessions", "row_count", "run_ids",
    "instrument", "source_sha256", "anchor_sha256", "feature_release_id", "feature_release_sha256",
    "role_metadata_sha256", "source_separation_verified", "source_observation_separation_verified",
    "label_horizon_separation_verified"])
def test_even_checksum_bound_receipt_must_match_metadata(evidence, monkeypatch, field):
    raw, metadata = evidence
    changed = json.loads(raw)
    owner = changed["groups"][0] if field in changed["groups"][0] else changed
    owner[field] = False if field.endswith("verified") else "changed"
    raw = s.canonical(changed)
    monkeypatch.setattr(s, "SOURCE_RECEIPT_SHA", s.digest(raw))
    with pytest.raises(ValueError):
        s.verify_source(raw, metadata)


def test_changed_metadata_and_group_inventory_fail_closed(evidence, monkeypatch):
    raw, metadata = evidence
    altered = deepcopy(metadata)
    altered["groups"][0]["row_count"] += 1
    with pytest.raises(ValueError, match="frozen role metadata"):
        s.verify_source(raw, altered)
    receipt = json.loads(raw)
    receipt["groups"].pop()
    raw = s.canonical(receipt)
    monkeypatch.setattr(s, "SOURCE_RECEIPT_SHA", s.digest(raw))
    with pytest.raises(ValueError, match="coverage"):
        s.verify_source(raw, metadata)


def test_bundle_authentication_precedes_metadata_interpretation(monkeypatch):
    calls = []
    monkeypatch.setattr(s.role_audit_bundle, "verify", lambda raw: calls.append(raw))
    with pytest.raises(ValueError, match="anchor"):
        s.authenticate(b"altered", b"unused")
    assert calls == []


def test_authenticate_preserves_frozen_normalizer_and_training_contract(bundle, monkeypatch):
    raw = s.canonical(bundle)
    monkeypatch.setattr(s, "ANCHOR_SHA", s.digest(raw))
    calls = []

    def checked_source(source_raw, metadata):
        calls.append((source_raw, metadata["fold_rows"]))
        return {"source_separation_verified": True}

    monkeypatch.setattr(s, "verify_source", checked_source)
    metadata, contract, normalizer, binding = s.authenticate(raw, b"fixture receipt")
    assert calls == [(b"fixture receipt", {"train": 33450, "validation": 9210})]
    assert normalizer == bundle["files"]["normalization.json"].encode()
    assert json.loads(normalizer)["training_binding_sha256"] == contract.training_binding()
    assert sum(group["row_count"] for group in metadata["groups"]) == 9210
    assert binding == {"source_separation_verified": True}
