"""Bounded restricted row ledger and independent arithmetic/identity readback."""
from collections import Counter
import json

from .verification_spec import canonical, digest

ROLES = ("selection", "calibration", "operating_point")
MAX_LEDGER = 2 * 1024**2
MAX_ROWS = 9210


def _inventory(metadata):
    groups = metadata["groups"]
    if len(groups) != len(ROLES) or {group["role"] for group in groups} != set(ROLES):
        raise ValueError("row audit requires every predeclared role")
    runs = {}
    for group in groups:
        if sum(shard["row_count"] for shard in group["shards"]) != group["row_count"]:
            raise ValueError("role row count differs from shard inventory")
        for shard in group["shards"]:
            if (shard["run_id"] in runs or type(shard["row_count"]) is not int
                    or shard["row_count"] <= 0):
                raise ValueError("invalid or duplicate audit run inventory")
            runs[shard["run_id"]] = {**shard, "role": group["role"]}
    if not 0 < sum(run["row_count"] for run in runs.values()) <= MAX_ROWS:
        raise ValueError("row inventory exceeds audit bound")
    return runs


def verify_rows(raw: bytes, metadata):
    """Recompute coverage from retained rows; labels remain worker-verified truth."""
    if not 0 < len(raw) <= MAX_LEDGER or not raw.endswith(b"\n"):
        raise ValueError("row ledger exceeds byte bound or lacks terminal newline")
    inventory = _inventory(metadata)
    targets = {run: [] for run in inventory}
    labels = {role: Counter() for role in ROLES}
    role_targets = {role: [] for role in ROLES}
    seen, run_order = set(), []
    for line in raw.splitlines():
        row = json.loads(line)
        if (not isinstance(row, dict) or set(row) != {"run_id", "target_id", "label"}
                or canonical(row) != line or not isinstance(row["run_id"], str)
                or row["run_id"] not in inventory):
            raise ValueError("row ledger escaped its canonical validation inventory")
        run, target, label = row["run_id"], row["target_id"], row["label"]
        if (not isinstance(target, str) or len(target) != 64
                or any(char not in "0123456789abcdef" for char in target)
                or target in seen or type(label) is not int or label not in (0, 1)):
            raise ValueError("invalid, duplicate or nonbinary audit row")
        if not run_order or run_order[-1] != run:
            if run in run_order:
                raise ValueError("audit run rows must be contiguous")
            run_order.append(run)
        if len(targets[run]) >= inventory[run]["row_count"]:
            raise ValueError("audit run has excess rows")
        seen.add(target)
        targets[run].append(target)
        role = inventory[run]["role"]
        role_targets[role].append(target)
        labels[role][label] += 1
    # For this frozen C4 inventory, lexical run order equals the adapter's
    # base-session, control-first, then campaign/run ordering.
    if run_order != sorted(inventory):
        raise ValueError("audit run order or coverage differs from the frozen adapter")
    runs = {}
    for run, ids in targets.items():
        identity = digest("".join(target + "\n" for target in ids).encode())
        if len(ids) != inventory[run]["row_count"] or identity != inventory[run]["row_identity_sha256"]:
            raise ValueError("audit run target order or coverage differs from bound shard")
        runs[run] = {"row_count": len(ids), "row_identity_sha256": identity}
    roles = {role: {"row_count": len(ids),
        "row_identity_sha256": digest("".join(target + "\n" for target in ids).encode()),
        "positive_rows": labels[role][1], "negative_rows": labels[role][0],
        "support_passed": labels[role][0] >= 20 and labels[role][1] >= 20}
        for role, ids in role_targets.items()}
    return {"roles": roles, "runs": runs, "row_count": len(seen),
        "ledger_sha256": digest(raw), "ledger_size_bytes": len(raw),
        "class_support_passed": all(role["support_passed"] for role in roles.values())}


def collect(windows, metadata):
    """Accept only adapter windows; publication keeps the ledger restricted."""
    rows = bytearray()
    for count, window in enumerate(windows, 1):
        if window.fold != "validation" or count > MAX_ROWS:
            raise ValueError("audit window escaped the validation row bound")
        rows.extend(canonical({"run_id": window.run_id,
            "target_id": window.target_id, "label": window.label}) + b"\n")
        if len(rows) > MAX_LEDGER:
            raise ValueError("audit ledger exceeds byte bound")
    raw = bytes(rows)
    return raw, verify_rows(raw, metadata)
