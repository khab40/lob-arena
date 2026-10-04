"""Fixed replacement scope and storage tests; no model, cloud or credential calls."""
from copy import deepcopy

import pytest

from app.ml.transformer import research_confirmation_contract as contract
from app.ml.transformer.research_execution_spec import (
    provider_spec, replacement_template, request_sha, template, validate,
)
from app.ml.transformer.research_storage import Store, key
from app.ml.transformer.verification_spec import canonical, digest
from test_transformer_research_storage import S3


def replacement(slot="seed-7"):
    return replacement_template(slot, "a" * 40, "sha256:" + "b" * 64,
                                contract.CONTEXT_PUBLIC_KEY, "c" * 32)


def original_smoke():
    return template("smoke", contract.BASE_SOURCE, contract.BASE_IMAGE_DIGEST,
                    contract.CONTEXT_PUBLIC_KEY, "8ea4408036fcf3330b39a9e3a6223802", {})


def test_original_request_hash_and_provider_namespace_remain_identical():
    request = original_smoke()
    validate(request, contract.BASE_SOURCE)
    assert request_sha(request) == contract.LEGACY_PRIOR["smoke"]["request"]["sha256"]
    assert key("smoke", "SUCCESS", request) == key("smoke", "SUCCESS")
    assert provider_spec(request)["image"].endswith("@" + contract.BASE_IMAGE_DIGEST)


@pytest.mark.parametrize("slot", contract.SLOTS)
def test_replacement_binds_frozen_inputs_and_new_assembly_identity(slot):
    request = replacement(slot)
    validate(request, "a" * 40)
    assert request["numerical_source_commit"] == contract.BASE_SOURCE
    assert request["base_image_digest"] == contract.BASE_IMAGE_DIGEST
    assert request["compatibility_sha256"] == digest(canonical(contract.MANIFEST))
    assert request["prior"] == contract.LEGACY_PRIOR
    assert request["trial"] == {"width": 128, "learning_rate": .0003, "seed": int(slot[5:]),
                                "max_epochs": 30, "batch_size": 64, "patience": 5}
    assert request["run_id"] == contract.CAMPAIGN + "-" + slot
    assert request["output_prefix"] == contract.PREFIX + slot + "/"
    assert provider_spec(request)["timeout"] == "7200s"
    assert len(canonical(request)) <= 16384
    request["prior"]["smoke"]["success"]["version_id"] = "changed"
    assert replacement()["prior"] == contract.LEGACY_PRIOR


@pytest.mark.parametrize("field,value", [
    ("schema_version", "transformer_research_execution_v1"), ("campaign", "another"),
    ("run_id", "consumed-run"), ("output_prefix", contract.LEGACY_PREFIX + "seed-7/"),
    ("numerical_source_commit", "f" * 40), ("base_image_digest", "sha256:" + "f" * 64),
    ("compatibility_sha256", "f" * 64), ("source_commit", contract.BASE_SOURCE),
    ("image_digest", contract.BASE_IMAGE_DIGEST), ("image_digest", "mutable:tag"),
    ("context_public_key", "f" * 64), ("final_test", True), ("slot", "inference"),
    ("trial", {"width": 64}), ("resources", {"timeout_seconds": 14400}),
])
def test_replacement_rejects_changed_identity_or_expanded_scope(field, value):
    request = replacement()
    request[field] = value
    with pytest.raises(ValueError):
        validate(request)


@pytest.mark.parametrize("change", ["missing", "extra", "swap", "version", "hash", "malformed"])
def test_prerequisite_set_is_exact_not_just_well_formed(change):
    request = replacement()
    prior = request["prior"]
    if change == "missing":
        prior.pop("smoke")
    elif change == "extra":
        prior["seed-7"] = deepcopy(prior["smoke"])
    elif change == "swap":
        prior["search-64-0003"], prior["search-128-0003"] = prior["search-128-0003"], prior["search-64-0003"]
    elif change == "version":
        prior["smoke"]["success"]["version_id"] = "2"
    elif change == "hash":
        prior["smoke"]["request"]["sha256"] = "f" * 64
    else:
        prior["smoke"] = None
    with pytest.raises((ValueError, TypeError)):
        validate(request)


@pytest.mark.parametrize("slot", ["smoke", "search-128-0003", "inference", "seed-99"])
def test_replacement_constructor_does_not_offer_other_workloads(slot):
    with pytest.raises(ValueError):
        replacement(slot)


def test_fresh_claim_preserves_consumed_evidence_and_only_writes_own_prefix():
    request, s3 = replacement(), S3()
    old = key("seed-7", "FAILED")
    s3.objects[old] = (b"failed", {"sha256": digest(b"failed")})
    store = Store(s3, request)
    store.claim()
    store.put("result.json", b"{}")
    assert s3.objects[old][0] == b"failed"
    assert all(name == old or name.startswith(request["output_prefix"]) for name in s3.objects)
    with pytest.raises(ValueError, match="already has evidence"):
        Store(s3, request).claim()


def test_legacy_reads_share_current_store_budget_and_cannot_access_other_seeds():
    request, s3 = replacement(), S3()
    store = Store(s3, request)
    for slot in contract.LEGACY_PRIOR:
        name = key(slot, "fixture.json")
        s3.objects[name] = (b"{}", {"sha256": digest(b"{}")})
        assert store.read(slot, "fixture.json")[0] == b"{}"
    assert store.gets == 5 and store.read_bytes == 10
    for slot in ("seed-2027", "inference"):
        with pytest.raises(ValueError, match="outside"):
            store.read(slot, "fixture.json")
    assert key("seed-7", "FAILED", request) != key("seed-7", "FAILED")
    store.gets = 1024
    with pytest.raises(ValueError, match="budget"):
        store.read("smoke", "fixture.json")


@pytest.mark.parametrize("name", ["../INTENT", "/INTENT", "seed-7/INTENT"])
def test_artifact_names_cannot_escape_the_fixed_prefix(name):
    with pytest.raises(ValueError):
        key("smoke", name, replacement())
