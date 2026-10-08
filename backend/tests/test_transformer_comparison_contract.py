"""Inert comparison namespace and checkpoint admission tests; no model calls."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("numpy")
from app.ml.transformer import research_comparison_contract as contract  # noqa: E402
from app.ml.transformer import research_confirmation_contract as confirmation  # noqa: E402
from app.ml.transformer import research_readback as readback  # noqa: E402
from app.ml.transformer.research_execution_spec import (  # noqa: E402
    comparison_template, provider_spec, request_sha, validate,
)
from app.ml.transformer.research_storage import key  # noqa: E402


def request():
    return comparison_template("a" * 40, "sha256:" + "b" * 64,
                               confirmation.CONTEXT_PUBLIC_KEY, "c" * 32)


def checkpoint_inputs():
    previous = json.loads((Path(__file__).parent / "fixtures/transformer_selected_origin.json").read_bytes())
    current = request()
    bindings = {**deepcopy(previous["result"]["bindings"]), "source_commit": current["source_commit"],
                "image_digest": current["image_digest"]}
    return current, {"search-128-0003": previous}, bindings


def test_only_exact_seven_inputs_and_one_hour_inference_are_admitted():
    current = request()
    validate(current)
    assert provider_spec(current)["timeout"] == "3600s"
    assert len(current["prior"]) == 7
    assert key("inference", "INTENT", current) == contract.PREFIX + "inference/INTENT"
    for slot in current["prior"]:
        prefix = confirmation.LEGACY_PREFIX if slot in confirmation.LEGACY_PRIOR else confirmation.PREFIX
        assert key(slot, "SUCCESS", current) == prefix + slot + "/SUCCESS"
    assert request_sha(current) != request_sha(confirmation_request())


def confirmation_request():
    from app.ml.transformer.research_execution_spec import replacement_template
    return replacement_template("seed-7", "a" * 40, "sha256:" + "b" * 64,
                                confirmation.CONTEXT_PUBLIC_KEY, "c" * 32)


@pytest.mark.parametrize("field,value", [
    ("schema_version", confirmation.SCHEMA), ("slot", "seed-7"), ("final_test", True),
    ("campaign", "another"), ("output_prefix", confirmation.LEGACY_PREFIX + "inference/"),
    ("numerical_source_commit", "d" * 40), ("compatibility_sha256", "e" * 64),
    ("source_commit", confirmation.BASE_SOURCE), ("image_digest", confirmation.BASE_IMAGE_DIGEST),
    ("image_digest", contract.MANIFEST["confirmation_origin"]["image_digest"]),
    ("context_public_key", "f" * 64), ("resources", {"timeout_seconds": 7200}),
])
def test_comparison_rejects_changed_scope_or_origin(field, value):
    current = request()
    current[field] = value
    with pytest.raises(ValueError):
        validate(current)


@pytest.mark.parametrize("slot", contract.MANIFEST["prior"])
@pytest.mark.parametrize("change", ["missing", "request", "success", "version"])
def test_changed_reference_is_rejected_before_storage(slot, change):
    current = request()
    if change == "missing":
        current["prior"].pop(slot)
    else:
        item = current["prior"][slot]
        if change == "request":
            item["request"]["sha256"] = "f" * 64
        elif change == "success":
            item["success"]["sha256"] = "f" * 64
        else:
            item["success"]["version_id"] = "changed"
    with pytest.raises(ValueError):
        validate(current)
    store = SimpleNamespace(request=request(), read_publication=lambda *a: pytest.fail("storage touched"))
    with pytest.raises(ValueError):
        readback.collect(store, slot, {}, "f" * 64, b"", b"", {})


def test_checkpoint_preserves_original_bindings_and_does_not_mutate_inputs():
    current, prior, bindings = checkpoint_inputs()
    before = deepcopy((current, prior, bindings))
    origin = contract.checkpoint_origin(current, prior, bindings)
    assert origin["checkpoint"]["epoch"] == 4
    assert prior[origin["slot"]]["result"]["trial"]["seed"] == 42
    assert origin["bindings"]["source_commit"] == confirmation.BASE_SOURCE
    assert origin["bindings"]["source_commit"] != bindings["source_commit"]
    assert (current, prior, bindings) == before
    origin["bindings"]["ordered_targets_sha256"]["calibration"] = "changed"
    assert (current, prior, bindings) == before


@pytest.mark.parametrize("change", ["unverified", "checkpoint", "trial", "origin", "request",
                                    "normalization", "rows", "extra", "assembly"])
def test_checkpoint_substitution_or_data_drift_fails_before_loading(change):
    current, prior, bindings = checkpoint_inputs()
    previous = prior["search-128-0003"]
    if change == "unverified":
        previous["status"] = "pending"
    elif change == "checkpoint":
        previous["result"]["selected_checkpoint"]["version_id"] = "2"
    elif change == "trial":
        previous["result"]["trial"]["seed"] = 7
    elif change == "origin":
        previous["result"]["bindings"]["source_commit"] = current["source_commit"]
    elif change == "request":
        previous["request"]["nonce"] = "d" * 32
    elif change == "normalization":
        bindings["normalization_sha256"] = "f" * 64
    elif change == "rows":
        bindings["ordered_targets_sha256"]["calibration"] = "f" * 64
    elif change == "extra":
        bindings["unknown"] = True
    else:
        bindings["source_commit"] = confirmation.BASE_SOURCE
    with pytest.raises(ValueError):
        contract.checkpoint_origin(current, prior, bindings)
