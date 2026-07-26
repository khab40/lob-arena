import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.corpus.models import GovernedBenchmarkProtocol, load_benchmark_protocol
from scripts.generate_governed_contracts import CONTRACTS, render_contract


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "configs" / "benchmark" / "governed-benchmark-v1.json"
SCHEMA_PATH = ROOT / "contracts" / "governed-benchmark-protocol-v1.schema.json"


def test_checked_in_governed_protocol_is_valid_and_stable() -> None:
    protocol = load_benchmark_protocol(PROTOCOL_PATH)

    assert protocol.schema_version == "governed_benchmark_protocol_v1"
    assert protocol.clean_labels.historical_default_label is None
    assert protocol.clean_labels.independent_reviewers >= 2
    assert protocol.splits.keep_all_session_campaigns_together
    assert protocol.splits.purge_ns == 10_000_000_000
    assert protocol.freeze_test_before_training
    assert len(protocol.protocol_hash()) == 64
    assert protocol.protocol_hash() == load_benchmark_protocol(PROTOCOL_PATH).protocol_hash()


def test_protocol_rejects_weak_label_and_leaky_split_policies() -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["clean_labels"]["independent_reviewers"] = 1
    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        GovernedBenchmarkProtocol.model_validate(payload)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["splits"]["group_fields"] = ["run_id"]
    with pytest.raises(ValidationError, match="split group must bind"):
        GovernedBenchmarkProtocol.model_validate(payload)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["splits"]["test_fraction"] = 0.3
    with pytest.raises(ValidationError, match="must sum to one"):
        GovernedBenchmarkProtocol.model_validate(payload)


def test_checked_in_contract_declares_fail_closed_protocol_controls() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["required"])

    assert schema["$schema"].endswith("2020-12/schema")
    assert {
        "clean_labels",
        "splits",
        "bootstrap",
        "metrics",
        "streaming",
        "freeze_test_before_training",
        "require_signed_release_manifest",
    } <= required
    assert schema["properties"]["freeze_test_before_training"] == {"const": True}
    assert schema["properties"]["require_signed_release_manifest"] == {"const": True}


def test_generated_governed_contracts_match_strict_runtime_models() -> None:
    for filename, (model, title) in CONTRACTS.items():
        assert (ROOT / "contracts" / filename).read_text(encoding="utf-8") == (
            render_contract(filename, model, title)
        )
