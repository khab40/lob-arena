import json
from pathlib import Path

import pytest

from app.ml.transformer.campaign_spec import configuration, configuration_sha256, load_configuration
from app.ml.transformer.verification_spec import canonical, digest


def test_repository_configuration_matches_reviewed_protocol():
    path = Path(__file__).resolve().parents[2] / "configs/experiments/transformer/c4-campaign-20260928.json"
    assert load_configuration(path, digest(path.read_bytes())) == configuration()


def test_campaign_has_finite_ordered_slots_and_four_fixed_trials():
    config = configuration()
    slots = config["resources"]["slots"]
    assert len(slots) == len({s["id"] for s in slots}) == 10
    assert slots[0]["id"] == "role-audit" and slots[-1]["id"] == "calibration"
    assert sum(s["kind"] == "gpu" for s in slots) == 8
    assert sum(s["timeout_seconds"] for s in slots if s["kind"] == "gpu") == 14 * 3600
    assert sum(s["timeout_seconds"] for s in slots) == 16 * 3600
    assert len([s for s in slots if s["id"].startswith("search-")]) == 4
    assert config["training"]["candidate_seed"] == 42
    assert config["authorization"]["execution"] == "separate_exact_package"


@pytest.mark.parametrize("field,value", [
    ("concurrency", 2), ("restart_policy", "on-failure"),
    ("preemptible", True), ("automatic_replacement", True),
    ("ephemeral_disk_gib", 200), ("output_total_gib", 21),
])
def test_matching_file_hash_does_not_authorize_changed_bounds(tmp_path, field, value):
    config = configuration()
    config["resources"][field] = value
    payload = canonical(config)
    path = tmp_path / "config.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="reviewed finite campaign"):
        load_configuration(path, digest(payload))


def test_configuration_rejects_unknown_fields_and_boolean_integer_coercion(tmp_path):
    for mutate in (lambda c: c.update(extra="unapproved"),
                   lambda c: c["resources"].update(concurrency=True),
                   lambda c: c["training"].update(candidate_seed=7),
                   lambda c: c["resources"]["slots"].append(c["resources"]["slots"][0])):
        config = configuration()
        mutate(config)
        payload = canonical(config)
        path = tmp_path / "config.json"
        path.write_bytes(payload)
        with pytest.raises(ValueError, match="reviewed finite campaign"):
            load_configuration(path, digest(payload))


def test_configuration_hash_and_independent_mutation(tmp_path):
    a, b = configuration(), configuration()
    a["model"]["widths"].append(256)
    assert b["model"]["widths"] == [64, 128]
    path = tmp_path / "config.json"
    path.write_bytes(canonical(b))
    assert load_configuration(path, configuration_sha256()) == b
    path.write_text(json.dumps(a))
    with pytest.raises(ValueError, match="checksum"):
        load_configuration(path, configuration_sha256())
