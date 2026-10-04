"""Fresh comparison identity and preserved v3 contracts; no model or cloud calls."""
from copy import deepcopy

import pytest

from app.ml.transformer import research_comparison_contract as contract
from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY
from app.ml.transformer.research_execution_spec import (
    comparison_replacement_template, comparison_template, provider_spec, request_sha, validate,
)
from app.ml.transformer.research_storage import key
from test_transformer_comparison_contract import checkpoint_inputs


def replacement():
    return comparison_replacement_template("a" * 40, "sha256:" + "b" * 64, CONTEXT_PUBLIC_KEY, "c" * 32)


def test_replacement_is_fresh_but_preserves_prerequisites_and_resources():
    current = replacement()
    original = comparison_template("a" * 40, "sha256:" + "b" * 64, CONTEXT_PUBLIC_KEY, "c" * 32)
    validate(current)
    validate(original)
    assert current["prior"] == original["prior"] and provider_spec(current) == provider_spec(original)
    assert current["run_id"] != original["run_id"] and request_sha(current) != request_sha(original)
    assert current["replacement_of"] == contract.REPLACEMENT_OF
    assert key("inference", "INTENT", current) == contract.REPLACEMENT_PREFIX + "inference/INTENT"
    assert key("inference", "INTENT", original) == contract.PREFIX + "inference/INTENT"
    for slot in current["prior"]:
        assert key(slot, "SUCCESS", current) == key(slot, "SUCCESS", original)


@pytest.mark.parametrize("field,value", [
    ("campaign", contract.CAMPAIGN), ("schema_version", contract.SCHEMA),
    ("run_id", contract.CAMPAIGN + "-inference"), ("output_prefix", contract.PREFIX + "inference/"),
    ("replacement_of", {}), ("source_commit", contract.REPLACEMENT_OF["source_commit"]),
    ("image_digest", contract.REPLACEMENT_OF["image_digest"]), ("final_test", True),
    ("resources", {"timeout_seconds": 7200}),
])
def test_replacement_cannot_reuse_consumed_identity_or_expand_scope(field, value):
    current = replacement()
    current[field] = value
    with pytest.raises(ValueError):
        validate(current)


@pytest.mark.parametrize("field", sorted(contract.REPLACEMENT_OF))
def test_consumed_attempt_reference_is_exact(field):
    current = replacement()
    current["replacement_of"][field] = "changed"
    with pytest.raises(ValueError):
        validate(current)


def test_selected_checkpoint_and_historical_bindings_survive_replacement():
    _, prior, bindings = checkpoint_inputs()
    current = replacement()
    before = deepcopy((prior, bindings))
    origin = contract.checkpoint_origin(current, prior, bindings)
    assert origin["checkpoint"] == contract.MANIFEST["selected"]["checkpoint"]
    assert origin["trial_sha256"] == contract.MANIFEST["selected"]["trial_sha256"]
    assert (prior, bindings) == before
