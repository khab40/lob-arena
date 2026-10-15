"""Prepare an inventory proposal; exact source/classification needs independent review."""
import argparse
import json
from pathlib import Path

from scripts.ci_workload_policy import SCHEMA, canonical, read_bytes, sha, source_paths, test_nodes


def prepare(root, audit_path, audit_sha, destination):
    audit_raw = read_bytes(audit_path)
    if sha(audit_raw) != audit_sha:
        raise ValueError("independent workload audit hash differs")
    audit = json.loads(audit_raw)
    models = {row["node_id"]: row["ast_sha256"] for row in audit["model_reaching_nodes"]}
    if len(models) != audit["model_reaching_test_definition_count"]:
        raise ValueError("independent workload audit duplicates or count differs")
    records, seen = [], set()
    for name in source_paths(root):
        raw = read_bytes(root / name)
        definitions = test_nodes(raw) if name.startswith("backend/tests/") and Path(name).name.startswith("test_") else {}
        tests = []
        for symbol, digest in definitions.items():
            node = name + "::" + symbol
            if node in models:
                if models[node] != digest:
                    raise ValueError("audited model function changed: " + node)
                seen.add(node)
            tests.append({"name": symbol, "ast_sha256": digest,
                          "classification": "nebius_cpu_model_workload" if node in models else "inert"})
        records.append({"path": name, "sha256": sha(raw), "tests": tests})
    if seen != set(models):
        raise ValueError("audited model test definition missing")
    destination.mkdir(parents=True, exist_ok=False)
    chunks = []
    for start in range(0, len(records), 128):
        name = f"source-{start // 128 + 1:02d}.json"
        rows = records[start:start + 128]
        # One explicit record per line keeps small commits and scanner-safe hash fields.
        raw = b"[\n" + b",\n".join(canonical(row) for row in rows) + b"\n]\n"
        (destination / name).write_bytes(raw)
        chunks.append({"path": name, "sha256": sha(raw)})
    index = {"schema_version": SCHEMA, "audit_sha256": audit_sha, "chunks": chunks,
             "model_definition_count": len(models)}
    (destination / "index.json").write_bytes(canonical(index) + b"\n")
    return {"source_files": len(records), "test_definitions": sum(len(row["tests"]) for row in records),
            "model_definitions": len(models), "inventory_sha256": sha((destination / "index.json").read_bytes()),
            "independent_review": "Pending", "model_execution": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.audit, args.audit_sha256, args.output)))
