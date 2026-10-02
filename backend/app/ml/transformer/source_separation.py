"""Offline C4 instrument-domain proof; no payload enumeration or execution authority."""
import json
from pathlib import Path
import sys

from app.market_data.projections import (
    FrozenPublicSampleRoot, SequenceProjectionManifest, TabularProjectionManifest,
)
from . import lineage_readback
from .label_domain import verify_labels
from .lineage_inventory import run_members
from .role_audit_bundle import MAX_BUNDLE, read_bounded
from .role_manifest import ROLES, SYMBOLS, metadata_plan
from .source_contract import PRODUCER_COMMIT, PRODUCER_IMAGE, verify_domains
from .verification_spec import canonical, digest


def separate(lineage, roles, domains):
    """Internal proof over authenticated metadata; public callers must use verify()."""
    if (lineage["metadata_lineage_verified"] is not True
            or lineage["producer_commit"] != PRODUCER_COMMIT
            or lineage["producer_image"] != PRODUCER_IMAGE):
        raise ValueError("source proof requires the reviewed producer contract")
    members = {m["run_id"]: m for m in run_members()}
    runs = {r["run_id"]: r for r in lineage["runs"]}
    if len(runs) != len(lineage["runs"]) or set(runs) != set(members):
        raise ValueError("source proof requires exact unique run coverage")
    groups = roles["groups"]
    if (len(groups) != len(ROLES) or {g["role"] for g in groups} != set(ROLES)
            or set(domains) != set(SYMBOLS)):
        raise ValueError("source proof requires three complete development roles")
    assigned, partitions, result = set(), set(), []
    for group in groups:
        identity = group["source_identity"]
        symbol = identity["instrument"]
        domain = domains[symbol]
        partition = (domain["source_sha256"], symbol)
        expected = {key for key, member in members.items() if member["symbol"] == symbol}
        shards = {s["run_id"]: s for s in group["shards"]}
        sessions = sorted({members[key]["base_session_id"] for key in expected})
        if (identity["source_sha256"] != domain["source_sha256"] or partition in partitions
                or set(shards) != expected or len(shards) != len(group["shards"])
                or group["base_sessions"] != sessions or assigned.intersection(shards)):
            raise ValueError("source domain is divided, aliased or incomplete")
        labels, rows = 0, 0
        for key, shard in shards.items():
            run, member = runs[key], members[key]
            if (run["instrument"] != symbol or run["dataset_id"] != domain["dataset_id"]
                    or run["base_session_id"] != member["base_session_id"]
                    or run["campaign_id"] != (key if member["mode"] == "hybrid" else None)
                    or run["supervised_row_count"] != shard["row_count"]):
                raise ValueError("run escaped its whole instrument domain")
            labels += verify_labels(run)
            rows += shard["row_count"]
        if rows != group["row_count"]:
            raise ValueError("role row coverage differs from frozen inventory")
        result.append({"role": group["role"], **domain, "group_sha256": group["group_sha256"],
            "base_sessions": sessions, "run_ids": sorted(shards), "row_count": rows,
            "positive_label_windows": labels, "label_scope": "entire_source_file_instrument"})
        partitions.add(partition)
        assigned.update(shards)
    if assigned != set(runs):
        raise ValueError("source roles do not cover every authenticated run")
    return result


def verify(bundle: Path, phase_one: Path, phase_two: Path):
    lineage = lineage_readback.verify(bundle, phase_one, phase_two)
    raw = read_bounded(bundle, MAX_BUNDLE)
    if digest(raw) != lineage["anchor_sha256"]:
        raise ValueError("anchor changed after authentication")
    files = json.loads(raw)["files"]
    root = FrozenPublicSampleRoot.model_validate_json(files["frozen-root.json"])
    tabular = TabularProjectionManifest.model_validate_json(files["tabular-projection.json"])
    sequence = SequenceProjectionManifest.model_validate_json(files["sequence-projection.json"])
    roles = metadata_plan(root, tabular, sequence)
    source = next(s for s in root.sources if s.fold == "validation").model_dump(mode="json")
    domains = verify_domains(json.loads(files["metadata-01.json"])["manifests"], source)
    groups = separate(lineage, roles, domains)
    return {"schema_version": "transformer_source_separation_v1",
        "proof_method": "authenticated_metadata_and_pinned_producer_contract",
        "producer_commit": PRODUCER_COMMIT, "producer_image": PRODUCER_IMAGE,
        "anchor_sha256": digest(raw), "lineage_receipt_sha256": digest(canonical(lineage)),
        "phase_one_receipts_sha256": lineage["phase_one_receipts_sha256"],
        "phase_two_receipts_sha256": lineage["phase_two_receipts_sha256"],
        "role_metadata_sha256": digest(canonical(roles)),
        "feature_release_id": roles["feature_release_id"],
        "feature_release_sha256": roles["feature_release_sha256"], "groups": groups,
        "source_observation_identity": ["source_stream_sha256", "source_sequence"],
        "source_observation_separation_verified": True, "label_horizon_separation_verified": True,
        "source_separation_verified": True, "payload_observation_ids_reenumerated": False,
        "temporal_disjoint": False, "statistical_independence_claimed": False,
        "label_tick_to_timestamp_mapping_claimed": False,
        "negative_label_source": "research_control_assumption", "independently_verified_clean": False,
        "class_support_verified": False, "gpu_ready": False, "execution_authorized": False,
        "limitations": ["one_validation_date", "one_instrument_per_role", "correlated_market_time",
            "shared_synthetic_templates_and_seeds", "prior_development_exposure",
            "producer_contract_proof_without_payload_reenumeration"],
        "remaining_proof": ["CPU_class_support_and_exact_row_alignment", "MLflow_and_platform_readiness",
            "exact_execution_authorization"], "payload_reads": 0, "cloud_reads": 0, "model_runs": 0}


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: source_separation BUNDLE PHASE_ONE PHASE_TWO NEW_RECEIPT")
    try:
        output = Path(sys.argv[4])
        if output.exists():
            raise FileExistsError("receipt already exists")
        result = verify(*(Path(arg) for arg in sys.argv[1:4]))
        with output.open("xb") as stream:
            stream.write(canonical(result))
    except Exception as error:
        raise SystemExit(f"Source separation failed: {type(error).__name__}") from None
    print(canonical({"source_separation_verified": True, "gpu_ready": False}).decode())


if __name__ == "__main__":
    main()
