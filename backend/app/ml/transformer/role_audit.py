"""CPU audit entrypoint for a future authorized Job; never trains or scores."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

from .campaign_spec import configuration, configuration_sha256
from .contracts import Normalization
from .data import DevelopmentInputs
from .role_manifest import ROLES, load_metadata, metadata_plan
from .verification_spec import SEQUENCE_SHA, TABULAR_SHA, canonical, checked_file, digest


def summarize_rows(windows, roles_by_run, expected_counts):
    """Input must come from the checksum-bound, fully verified window adapter."""
    targets = {role: [] for role in ROLES}
    labels = {role: Counter() for role in ROLES}
    observed_runs = Counter()
    seen = set()
    for window in windows:
        if window.fold != "validation" or window.run_id not in roles_by_run:
            raise ValueError("audit row escaped validation role assignment")
        if type(window.label) is not int or window.label not in (0, 1):
            raise ValueError("invalid binary audit label")
        if window.target_id in seen:
            raise ValueError("duplicate target across development roles")
        seen.add(window.target_id)
        role = roles_by_run[window.run_id]
        targets[role].append(window.target_id)
        labels[role][window.label] += 1
        observed_runs[window.run_id] += 1
    if dict(observed_runs) != expected_counts:
        raise ValueError("audit row coverage differs from bound shard inventory")
    summary = {}
    for role in ROLES:
        ids = targets[role]
        summary[role] = {"target_ids": ids, "row_count": len(ids),
            "row_identity_sha256": digest("".join(t + "\n" for t in ids).encode()),
            "positive_rows": labels[role][1], "negative_rows": labels[role][0],
            "support_passed": labels[role][0] >= 20 and labels[role][1] >= 20}
    return summary


def audit(inputs: Path, normalizer: Path):
    root, tabular, sequences = load_metadata(inputs)
    metadata = metadata_plan(root, tabular, sequences)
    normalization = Normalization.model_validate_json(checked_file(normalizer,
        configuration()["inputs"]["normalization_sha256"]))
    data = DevelopmentInputs.open(root=root, tabular_path=inputs / "manifests/tabular-projection.json",
        tabular_sha256=TABULAR_SHA, sequence_path=inputs / "manifests/sequence-projection.json",
        sequence_sha256=SEQUENCE_SHA, artifact_root=inputs / "artifacts")
    if normalization.training_binding_sha256 != data.contract.training_binding():
        raise ValueError("normalizer belongs to a different training release")
    by_run = {s["run_id"]: group["role"] for group in metadata["groups"] for s in group["shards"]}
    expected = {s["run_id"]: s["row_count"] for group in metadata["groups"] for s in group["shards"]}
    roles = summarize_rows(data.windows("validation"), by_run, expected)
    support = all(role["support_passed"] for role in roles.values())
    # Do not turn row disjointness into a claim of independent source observations.
    return {"schema_version": "transformer_role_audit_v1",
        "campaign_sha256": configuration_sha256(), "metadata_sha256": digest(canonical(metadata)),
        "normalization_sha256": configuration()["inputs"]["normalization_sha256"],
        "roles": roles, "class_support_passed": support, "gpu_ready": False,
        "blockers": ([] if support else ["insufficient_class_support"])
            + ["source_provenance_receipt_required", "platform_readiness_required",
               "exact_execution_authorization_required"],
        "model_runs": 0, "final_test_access": False}


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: role_audit INPUT_DIRECTORY NORMALIZATION_JSON NEW_OUTPUT_DIRECTORY")
    output = Path(sys.argv[3])
    output.mkdir(parents=True, exist_ok=False)
    result = audit(Path(sys.argv[1]), Path(sys.argv[2]))
    (output / "role-audit.json").write_bytes(canonical(result))
    print(json.dumps({"class_support_passed": result["class_support_passed"],
                      "gpu_ready": False, "artifact_sha256": digest(canonical(result))}))
    if not result["class_support_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
