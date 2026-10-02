"""Label-independent roles from externally bound C4 metadata; no row reads."""
from __future__ import annotations

from pathlib import Path

from app.market_data.projections import (
    FrozenPublicSampleRoot, SequenceProjectionManifest, TabularProjectionManifest,
    _load_bound_manifest,
)
from .data import baseline_order, domain
from .verification_spec import FOLD_ROWS, ROOT_SHA, SEQUENCE_SHA, SYMBOLS, TABULAR_SHA, canonical, checked_file, digest

ROLES = ("selection", "calibration", "operating_point")


def load_metadata(inputs: Path):
    root = FrozenPublicSampleRoot.model_validate_json(
        checked_file(inputs / "manifests/frozen-root.json", ROOT_SHA))
    tabular = _load_bound_manifest(inputs / "manifests/tabular-projection.json",
        expected_sha256=TABULAR_SHA, model=TabularProjectionManifest, root=root)
    sequences = _load_bound_manifest(inputs / "manifests/sequence-projection.json",
        expected_sha256=SEQUENCE_SHA, model=SequenceProjectionManifest, root=root)
    return root, tabular, sequences


def assign_roles(groups):
    """Canonical source identities merge replay aliases before round-robin assignment.

    Only C4's symbol-local source domains are supported. Unknown cross-instrument
    or cross-session features require a new provenance protocol, not this mapping.
    """
    merged = {}
    sessions = set()
    for group in groups:
        key = digest(canonical(group["source_identity"]))
        session = group["base_session_id"]
        if session in sessions:
            raise ValueError("duplicate base source session")
        sessions.add(session)
        entry = merged.setdefault(key, {"group_sha256": key,
            "source_identity": group["source_identity"], "base_sessions": []})
        entry["base_sessions"].append(session)
    if len(merged) < len(ROLES):
        raise ValueError("fewer than three independent source groups")
    return [{**merged[key], "base_sessions": sorted(merged[key]["base_sessions"]),
             "role": ROLES[index % len(ROLES)]} for index, key in enumerate(sorted(merged))]


def metadata_plan(root, tabular, sequences):
    if tabular.access_scope != "development" or sequences.access_scope != "development":
        raise ValueError("role preparation rejects final-test manifests")
    for manifest in (tabular, sequences):
        if manifest.root_sha256 != root.canonical_hash():
            raise ValueError("projection escaped its root binding")
    by_domain = {domain(shard): shard for shard in sequences.shards}
    if len(by_domain) != len(sequences.shards) or set(by_domain) != {domain(s) for s in tabular.shards}:
        raise ValueError("projection domains differ")
    expected_sessions = {f"xnas-{s.trade_date}-{symbol.lower()}": (s, symbol)
                         for s in root.sources if s.fold != "test" for symbol in SYMBOLS}
    if {s.base_session_id for s in tabular.shards} != set(expected_sessions):
        raise ValueError("C4 base source session inventory changed")
    counts = dict.fromkeys(FOLD_ROWS, 0)
    grouped = {}
    runs = set()
    for shard in sorted(tabular.shards, key=baseline_order):
        source, symbol = expected_sessions[shard.base_session_id]
        other = by_domain[domain(shard)]
        if shard.fold != source.fold or shard.run_id in runs:
            raise ValueError("changed source fold or duplicate replay run")
        runs.add(shard.run_id)
        if (other.sequence_length != 64 or other.sequence_count != shard.supervised_row_count
                or other.sequence_identity_sha256 != shard.row_identity_sha256):
            raise ValueError("sequence and target identities differ")
        counts[shard.fold] += shard.supervised_row_count
        if shard.fold == "validation":
            group = grouped.setdefault(shard.base_session_id, {
                "base_session_id": shard.base_session_id,
                "source_identity": {"source_sha256": source.source_sha256,
                    "source_manifest_sha256": source.source_manifest_sha256,
                    "parser_config_sha256": source.parser_config_sha256,
                    "trade_date": str(source.trade_date), "instrument": symbol},
                "shards": []})
            group["shards"].append({"run_id": shard.run_id,
                "row_count": shard.supervised_row_count,
                "row_identity_sha256": shard.row_identity_sha256,
                "replay_manifest_sha256": shard.replay_manifest_sha256,
                "tabular_sha256": shard.rows.sha256,
                "sequence_sha256": other.sequences.sha256})
    if counts != FOLD_ROWS:
        raise ValueError("C4 fold row inventory changed")
    assignments = assign_roles(grouped.values())
    for item in assignments:
        item["shards"] = [shard for session in item["base_sessions"] for shard in grouped[session]["shards"]]
        item["row_count"] = sum(s["row_count"] for s in item["shards"])
    return {"schema_version": "transformer_role_metadata_v1",
        "algorithm": "canonical_source_group_sha256_round_robin_v1",
        "root_identity_sha256": root.canonical_hash(),
        "feature_release_id": root.feature_release_id,
        "feature_release_sha256": root.feature_release_sha256,
        "fold_rows": counts, "groups": assignments,
        "payload_audit": "pending", "gpu_ready": False,
        "limitations": ["one_validation_date", "one_instrument_per_role",
            "prior_development_exposure", "metadata_does_not_prove_class_support",
            "source_observation_and_label_horizon_separation_require_provenance_receipt"]}


def prepare(inputs: Path):
    return metadata_plan(*load_metadata(inputs))


def main():
    import sys

    if len(sys.argv) != 3:
        raise SystemExit("usage: role_manifest INPUT_DIRECTORY NEW_OUTPUT_FILE")
    payload = canonical(prepare(Path(sys.argv[1])))
    with Path(sys.argv[2]).open("xb") as stream:
        stream.write(payload)
    print(canonical({"role_metadata_sha256": digest(payload), "gpu_ready": False}).decode())


if __name__ == "__main__":
    main()
