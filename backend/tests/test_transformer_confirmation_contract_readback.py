"""Cross-image origin checks with inert artifact fixtures; never execute a model."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.ml.transformer import research_confirmation_contract as contract
from app.ml.transformer import research_readback as readback
from app.ml.transformer.research_execution_spec import request_sha
from app.ml.transformer.verification_spec import canonical, digest
from test_transformer_confirmation_contract import original_smoke, replacement


@pytest.mark.parametrize("slot", contract.LEGACY_PRIOR)
def test_exact_legacy_references_are_accepted_without_relabelling(slot):
    current, reference = replacement(), contract.prerequisites()[slot]
    contract.require_reference(current, slot, reference["success"], reference["request"]["sha256"])
    previous = {k: contract.MANIFEST[k] for k in ("source_commit", "image_digest", "context_public_key")}
    assert contract.origin_matches(previous, current, slot)
    assert previous["source_commit"] != current["source_commit"]
    for field in previous:
        altered = {**previous, field: "changed"}
        assert not contract.origin_matches(altered, current, slot)


@pytest.mark.parametrize("change", ["success", "request", "version", "slot", "self"])
def test_wrong_reference_fails_before_any_artifact_read(change):
    current, slot = replacement(), "smoke"
    reference = contract.prerequisites()[slot]
    if change == "success":
        reference["success"]["sha256"] = "f" * 64
    elif change == "request":
        reference["request"]["sha256"] = "f" * 64
    elif change == "version":
        reference["success"]["version_id"] = "2"
    elif change == "slot":
        slot = "seed-2027"
    else:
        slot = current["slot"]
    store = SimpleNamespace(request=current, read_publication=lambda *a: pytest.fail("storage touched"))
    with pytest.raises(ValueError):
        readback.collect(store, slot, reference["success"], reference["request"]["sha256"], b"", b"", {})


def test_v1_origin_check_still_requires_identical_source_image_and_key():
    previous, current = original_smoke(), original_smoke()
    assert contract.origin_matches(previous, current, "smoke")
    for field in ("source_commit", "image_digest", "context_public_key"):
        assert not contract.origin_matches({**previous, field: "changed"}, current, "smoke")


def fixture_store(monkeypatch, request, result, current=None):
    """Isolate origin/configuration routing; original audit/signature tests stay separate."""
    raw = {name: canonical({}) for name in readback.AUDIT}
    raw.update({"configuration.json": canonical(request), "execution-context.json": b"{}",
                "baseline-verification.json": b"{}", "result.json": canonical(result)})
    raw["event-0000.json"] = canonical({"index": 0, "previous_sha256": None,
        "request_sha256": request_sha(request), "kind": "completed",
        "payload": {"result_sha256": digest(raw["result.json"])}})
    inventory = {name: {"sha256": digest(value), "size_bytes": len(value), "version_id": "1"}
                 for name, value in raw.items()}
    monkeypatch.setattr(readback, "verify_context", lambda *a: {"job_id": "aijob-fixture"})
    monkeypatch.setattr(readback, "verify_package", lambda *a: {"class_support_passed": True})
    return SimpleNamespace(request=current or request, read_publication=lambda *a: inventory,
                           read=lambda slot, name, item: (raw[name], item)), raw


def test_collector_preserves_original_smoke_request_and_identity(monkeypatch):
    request, current = original_smoke(), replacement()
    result = {"kind": "smoke", "request_sha256": request_sha(request), "job_id": "aijob-fixture",
              "checks": {"status": "verified"}, "real_data": {"optimizer_steps": 32, "rows": 1024, "epochs": 2}}
    store, raw = fixture_store(monkeypatch, request, result, current)
    before = deepcopy(raw)
    reference = contract.LEGACY_PRIOR["smoke"]
    verified = readback.collect(store, "smoke", reference["success"], reference["request"]["sha256"], b"", b"", {})
    assert verified["request"] == request and verified["status"] == "verified"
    assert verified["request"]["source_commit"] == contract.BASE_SOURCE
    assert verified["request"]["image_digest"] == contract.BASE_IMAGE_DIGEST
    assert raw == before


@pytest.mark.parametrize("change", [None, "width", "learning_rate", "seed", "relabel_source"])
def test_collector_requires_exact_confirmation_trial_and_assembly(monkeypatch, change):
    current = replacement()
    request = deepcopy(current)
    if change == "relabel_source":
        request["source_commit"] = "d" * 40
    result = {"kind": "trial", "request_sha256": request_sha(request), "job_id": "aijob-fixture",
              "trial": deepcopy(current["trial"])}
    if change in ("width", "learning_rate", "seed"):
        result["trial"][change] = {"width": 64, "learning_rate": .001, "seed": 2027}[change]
    store, _ = fixture_store(monkeypatch, request, result, current)
    checks = []
    def verify_trial(result, *args, **kwargs):
        checks.append(True)
        return {**result, "status": "verified"}
    monkeypatch.setattr(readback, "verify_trial", verify_trial)
    if change is None:
        verified = readback.collect(store, current["slot"], {}, request_sha(current), b"", b"", {})
        assert verified["status"] == "verified" and checks == [True]
    else:
        with pytest.raises(ValueError):
            readback.collect(store, current["slot"], {}, request_sha(current), b"", b"", {})
        assert not checks
