from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("numpy")

from app.ml.transformer import source_separation as s  # noqa: E402
from app.ml.transformer.lineage_inventory import run_members  # noqa: E402


def evidence():
    domains = {symbol: {"source_sha256": "a" * 64, "instrument": symbol,
        "dataset_id": symbol, "normalized_rows": 100,
        "ancestry_scope": "entire_source_file_instrument_including_warmup"} for symbol in s.SYMBOLS}
    runs = []
    for member in run_members():
        hybrid = member["mode"] == "hybrid"
        runs.append({"run_id": member["run_id"], "instrument": member["symbol"],
            "dataset_id": member["symbol"], "base_session_id": member["base_session_id"],
            "campaign_id": member["run_id"] if hybrid else None, "supervised_row_count": 10,
            "negative_label_source": "research_control_assumption", "independently_verified_clean": False,
            "label_windows": [{"label": 1, "attack_family": member["family"],
                "label_source": "synthetic_scenario", "provenance_id": None,
                "start_tick": 1, "end_tick": 4, "end_inclusive": True,
                "start_timestamp_ns": None, "end_timestamp_ns": None, "phases": {}}] if hybrid else []})
    groups = [{"role": role, "source_identity": {"instrument": symbol, "source_sha256": "a" * 64},
        "base_sessions": [f"xnas-2019-10-30-{symbol.lower()}"], "group_sha256": str(i) * 64,
        "shards": [{"run_id": r["run_id"], "row_count": 10} for r in runs if r["instrument"] == symbol],
        "row_count": 100} for i, (symbol, role) in enumerate(zip(s.SYMBOLS, s.ROLES, strict=True))]
    return {"metadata_lineage_verified": True, "producer_commit": s.PRODUCER_COMMIT,
        "producer_image": s.PRODUCER_IMAGE, "runs": runs}, {"groups": groups}, domains


def test_whole_symbol_domains_keep_all_seeds_and_labels_in_one_role():
    result = s.separate(*evidence())
    assert len(result) == 3
    assert {r["positive_label_windows"] for r in result} == {9}
    assert all(len(r["run_ids"]) == 10 for r in result)
    assert {r["source_sha256"] for r in result} == {"a" * 64}
    assert all(r["label_scope"] == "entire_source_file_instrument" for r in result)


@pytest.mark.parametrize("defect", ["commit", "image", "unauthenticated", "missing_run", "duplicate_run",
    "extra_run", "instrument", "dataset", "session", "campaign", "row_count", "group_count",
    "role_alias", "source_alias", "split_variant", "duplicate_shard", "source_hash", "base_sessions"])
def test_unsupported_or_divided_domains_cannot_claim_separation(defect):
    lineage, roles, domains = evidence()
    run, group = lineage["runs"][0], roles["groups"][0]
    if defect in ("commit", "image"):
        lineage[f"producer_{defect}"] = "unreviewed"
    elif defect == "unauthenticated":
        lineage["metadata_lineage_verified"] = False
    elif defect == "missing_run":
        lineage["runs"].pop()
    elif defect == "duplicate_run":
        lineage["runs"].append(deepcopy(run))
    elif defect == "extra_run":
        lineage["runs"].append({**run, "run_id": "unknown"})
    elif defect in ("instrument", "dataset", "session", "campaign"):
        run[{"dataset": "dataset_id", "session": "base_session_id", "campaign": "campaign_id"}.get(defect, defect)] = "unknown"
    elif defect == "row_count":
        run["supervised_row_count"] += 1
    elif defect == "group_count":
        roles["groups"].pop()
    elif defect == "role_alias":
        roles["groups"][1]["role"] = group["role"]
    elif defect == "source_alias":
        roles["groups"][1]["source_identity"] = deepcopy(group["source_identity"])
    elif defect == "split_variant":
        roles["groups"][1]["shards"].append(group["shards"].pop())
    elif defect == "duplicate_shard":
        group["shards"].append(deepcopy(group["shards"][0]))
    elif defect == "source_hash":
        group["source_identity"]["source_sha256"] = "b" * 64
    else:
        group["base_sessions"] = ["another-session"]
    with pytest.raises(ValueError):
        s.separate(lineage, roles, domains)


def test_verifier_reauthenticates_before_interpreting_metadata(monkeypatch, tmp_path):
    calls = []

    def reject(*paths):
        calls.append(paths)
        raise ValueError("retained evidence differs")

    monkeypatch.setattr(s.lineage_readback, "verify", reject)
    paths = tuple(tmp_path / name for name in ("anchor", "phase1", "phase2"))
    with pytest.raises(ValueError, match="retained evidence"):
        s.verify(*paths)
    assert calls == [paths]


def test_anchor_change_after_authentication_is_rejected(monkeypatch, tmp_path):
    bundle = tmp_path / "anchor"
    bundle.write_bytes(b"changed bytes")
    monkeypatch.setattr(s.lineage_readback, "verify", lambda *_: {"anchor_sha256": "a" * 64})
    with pytest.raises(ValueError, match="anchor changed"):
        s.verify(bundle, tmp_path, tmp_path)


def test_success_retains_lineage_and_never_opens_later_gates(monkeypatch, tmp_path):
    lineage, roles, domains = evidence()
    bundle = tmp_path / "anchor.json"
    files = {name: "{}" for name in ("frozen-root.json", "tabular-projection.json",
        "sequence-projection.json")}
    files["metadata-01.json"] = s.canonical({"manifests": {}}).decode()
    raw = s.canonical({"files": files})
    # Freeze the orchestration inputs; authentication itself is tested by readback tests.
    bundle.write_bytes(raw)
    lineage.update(anchor_sha256=s.digest(raw), phase_one_receipts_sha256="b" * 64,
        phase_two_receipts_sha256="c" * 64)
    roles.update(feature_release_id="fixture-release", feature_release_sha256="d" * 64)
    root = NS(sources=[NS(fold="validation", model_dump=lambda **_: {})])
    monkeypatch.setattr(s.lineage_readback, "verify", lambda *_: lineage)
    monkeypatch.setattr(s, "FrozenPublicSampleRoot", NS(model_validate_json=lambda _: root))
    for model in ("TabularProjectionManifest", "SequenceProjectionManifest"):
        monkeypatch.setattr(s, model, NS(model_validate_json=lambda _: None))
    monkeypatch.setattr(s, "metadata_plan", lambda *_: roles)
    monkeypatch.setattr(s, "verify_domains", lambda *_: domains)
    result = s.verify(bundle, tmp_path, tmp_path)
    assert result["lineage_receipt_sha256"] == s.digest(s.canonical(lineage))
    assert result["role_metadata_sha256"] == s.digest(s.canonical(roles))
    assert result["feature_release_sha256"] == roles["feature_release_sha256"]
    assert all(result[key] for key in ("source_observation_separation_verified",
        "label_horizon_separation_verified", "source_separation_verified"))
    assert all(result[key] is False for key in ("class_support_verified", "gpu_ready",
        "execution_authorized", "temporal_disjoint", "statistical_independence_claimed",
        "payload_observation_ids_reenumerated", "label_tick_to_timestamp_mapping_claimed",
        "independently_verified_clean"))
    assert result["payload_reads"] == result["cloud_reads"] == result["model_runs"] == 0


def test_cli_preserves_existing_output_and_never_publishes_failed_proof(monkeypatch, tmp_path):
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(s.sys, "argv", ["source_separation", "missing", "missing", "missing", str(output)])
    with pytest.raises(SystemExit, match="FileNotFoundError"):
        s.main()
    assert not output.exists()
    output.write_bytes(b"retained")
    with pytest.raises(SystemExit, match="FileExistsError"):
        s.main()
    assert output.read_bytes() == b"retained"


def test_cli_writes_exact_success_and_never_authorizes_execution(monkeypatch, tmp_path):
    output = tmp_path / "receipt.json"
    receipt = {"source_separation_verified": True, "gpu_ready": False, "execution_authorized": False}
    monkeypatch.setattr(s, "verify", lambda *_: receipt)
    monkeypatch.setattr(s.sys, "argv", ["source_separation", "a", "b", "c", str(output)])
    s.main()
    assert Path(output).read_bytes() == s.canonical(receipt)
