"""Seal an exact metadata-only request and policy proposal; never submit a Job."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from app.ml.transformer.holdout_delivery import provider_spec
from app.ml.transformer.holdout_entrypoint import context_key
from app.ml.transformer.holdout_policy import access_rules, temporary_policy
from app.ml.transformer.holdout_preparation import audited_inputs
from app.ml.transformer.holdout_runtime import encode_request
from app.ml.transformer.holdout_spec import HoldoutRequest, InputObject, OUTPUT_ROOT, SETTINGS_SHA
from app.ml.transformer.verification_spec import canonical, digest

GROUP = "group-e00wb5ptvpq0q7dpaf"
SELECTORS = {
    "AWS_ACCESS_KEY_ID": {"secret_id": "mbsec-e00arhndyprqr8egjw", "version_id": "mbsecver-e00rjzerny1pf9qhna"},
    "AWS_SECRET_ACCESS_KEY": {"secret_id": "mbsec-e00s7qtjj5n9ghacnh", "version_id": "mbsecver-e00yfn5w54jc1ybkwv"},
}


def save(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def prepare(root, output, source_root):
    if (output / "request.json").exists() or (output / "context-private.key").exists():
        raise ValueError("existing execution identity must never be regenerated")
    output.mkdir(parents=True, exist_ok=True)
    settings_raw = (root / "outputs/transformer-settings-release-20261005/selected-settings.json").read_bytes()
    if digest(settings_raw) != SETTINGS_SHA:
        raise ValueError("selected settings differ")
    settings = json.loads(settings_raw)
    inputs = list(audited_inputs(output / "development-inventory.jsonl",
        source_root / "docs/evidence/transformer-holdout-object-inventory-20261006.json"))
    for name, path in (("checkpoint", "model/checkpoint.pt"), ("contract", "model/input-contract.json"),
                       ("normalization", "model/normalization.json")):
        inputs.append(InputObject(path=path, scope="development", reference=settings["artifacts"][name]))
    ref = json.loads((output / "reference-publication.json").read_bytes())["artifact"]
    if (ref["sha256"] != "220a2cf373290c846e1da29252ed149156b3f74d6598d2da4e9863bfbca364a5"
            or ref["size_bytes"] != 7544 or ref["version_id"] in ("", "null")):
        raise ValueError("published reference differs")
    inputs.append(InputObject(path="reference-logits.json", scope="development", reference=ref))
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    run_id = "transformer-holdout-c4-20261006-r1"
    image = json.loads((output / "image-publication.json").read_bytes())
    request = HoldoutRequest(run_id=run_id, source_commit=image["source_commit"],
        image_repository=image["repository"], image_digest=image["image_digest"],
        context_public_key=public, nonce=secrets.token_hex(16),
        package_sha256="612a904b055fb18da45f5b7fcbd7e7e4f5556e9f184b6368c381726c6d7dc9e2",
        provider_spec_sha256="0" * 64, inputs=tuple(inputs),
        tabular_path="manifests/tabular-projection.json", sequence_path="manifests/sequence-projection.json",
        baseline_paths=("baseline/predictions.parquet",), reference_logits_path="reference-logits.json",
        reference_targets_sha256="db1ae73f950c22d06ccb2d675351fa64df9a5db9af1dc38ff0c08f75da3d155d",
        reference_rows=64, output_prefix=OUTPUT_ROOT + run_id + "/")
    spec = provider_spec(request, SELECTORS)
    request = HoldoutRequest.model_validate({**request.model_dump(), "provider_spec_sha256": digest(canonical(spec))})
    policies = {}
    for name in ("final", "results"):
        policies[name] = json.loads((output / f"{name}-policy-baseline.json").read_bytes())
    final_keys = [item.reference.uri.split("/", 3)[3] for item in inputs
                  if item.scope == "final_test" and "wave1-final-" in item.reference.uri]
    if len(final_keys) != 62 or len(inputs) != 252:
        raise ValueError("holdout input or final-key count differs")
    baseline_key = request.input(request.baseline_paths[0]).reference.uri.split("/", 3)[3]
    final_policy = temporary_policy(policies["final"], access_rules(GROUP, "storage.viewer", final_keys))
    results_policy = temporary_policy(policies["results"],
        access_rules(GROUP, "storage.viewer", [baseline_key]) + access_rules(GROUP, "storage.object-editor",
            [request.output_prefix + "*", context_key(request)]))
    records = {"request.json": request.canonical_bytes(), "request.json.gz": encode_request(request),
        "provider-spec.json": canonical(spec), "selectors.json": canonical(SELECTORS),
        "approval-preview.json": canonical({"approved_request_sha256": request.sha256(), "trusted_public_key": public}),
        "final-policy-temporary.json": canonical(final_policy), "results-policy-temporary.json": canonical(results_policy)}
    proposal = {"schema_version": "transformer_holdout_execution_proposal_v1", "status": "awaiting_exact_authorization",
        "tickets": ["https://github.com/khab40/lob-arena/issues/24", "https://github.com/khab40/lob-arena/issues/314"],
        "request_sha256": request.sha256(), "run_id": run_id, "context_public_key": public,
        "provider_spec_sha256": request.provider_spec_sha256, "image": spec["image"],
        "files": {name: digest(raw) for name, raw in records.items()}, "source_commit": request.source_commit,
        "input_count": len(inputs), "final_keys": 62, "saved_baseline_keys": 1,
        "final_policy_rules": len(final_policy), "results_policy_rules": len(results_policy),
        "access_seconds": 10800, "policy_versions": {"final": "10", "results": "11"},
        "jobs": 1, "attempts": 1, "runtime_seconds": 3600, "create_to_terminal_seconds": 7200,
        "additional_spend_cap_usd_excluding_vat": "6.25", "max_input_bytes": 16 * 1024**3,
        "max_output_bytes": 2 * 1024**3, "max_io_calls": 10000,
        "transient_read_attempt_seconds": [30, 60, 90, 120], "mutation_retries": 0,
        "fitting": False, "reselection": False, "replacement_authorized": False,
        "cleanup": "Remove added grants and restore original policies after terminal state or abort; independently read back.",
        "signing": "Local context key retained in agent custody; sign only live provider observations after exact approval."}
    fd = os.open(output / "context-private.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))
    for name, raw in records.items():
        save(output / name, raw)
    save(output / "proposal.json", canonical(proposal))
    return {"proposal_sha256": digest(canonical(proposal)), "request_sha256": request.sha256(),
            "inputs": len(inputs), "compressed_bytes": len(records["request.json.gz"]), "jobs_created": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root.resolve(), args.output.resolve(), Path(__file__).resolve().parents[1])))
