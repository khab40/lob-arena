"""Prepare one comparison from exact verified local artifacts; never call cloud."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import secrets
import shlex

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ml.transformer.research_comparison_contract import MANIFEST, checkpoint_origin
from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY
from app.ml.transformer.research_execution_spec import (
    comparison_replacement_template, comparison_template, request_sha, validate,
)
from app.ml.transformer.research_policy import Trial, seed_stability
from app.ml.transformer.verification_spec import canonical, digest
from transformer_confirmation_prepare import VERIFIED_SHA, create_command, verify_legacy

CONFIRMATIONS = {
    "seed-7": "5b1703e2a5689f284d0c67cb059c42014689438b78da4a2a2f003a8fd43e2737",
    "seed-2027": "3301c1e05dcda8515793576fdfb63ce21f3eee039c442c5d29d65e1ec5a18ee1",
}


def local_preflight(legacy, confirmations, bundle, source):
    for name, version in {"botocore": "1.43.103", "cryptography": "50.0.0", "numpy": "2.4.6",
                          "pyarrow": "25.0.0", "pydantic": "2.13.5"}.items():
        if importlib.metadata.version(name) != version:
            raise ValueError("comparison operator dependency differs")
    from app.ml.transformer.role_source import authenticate
    authenticate(bundle.read_bytes(), source.read_bytes())
    verify_legacy(legacy)
    prior = {}
    for slot, fixed in MANIFEST["prior"].items():
        directory = (confirmations if slot in CONFIRMATIONS else legacy) / slot
        raw = (directory / "verification.json").read_bytes()
        report = json.loads(raw)
        request = json.loads((directory / "request.json").read_bytes())
        if (digest(raw) != {**VERIFIED_SHA, **CONFIRMATIONS}[slot] or report["status"] != "verified"
                or request_sha(request) != fixed["request"]["sha256"]
                or json.loads((directory / "success-receipt.json").read_bytes()) != fixed["success"]):
            raise ValueError("comparison prerequisite receipt differs")
        for name, item in report["inventory"].items():
            path = directory / "artifacts" / name
            if not path.resolve().is_relative_to((directory / "artifacts").resolve()):
                raise ValueError("comparison artifact escapes evidence")
            data = path.read_bytes()
            if len(data) != item["size_bytes"] or digest(data) != item["sha256"]:
                raise ValueError("comparison local artifact differs")
        if json.loads((directory / "artifacts/configuration.json").read_bytes()) != request:
            raise ValueError("comparison artifact configuration differs")
        prior[slot] = {**report, "request": request}
    winner = prior[MANIFEST["selected"]["slot"]]["result"]
    stability = seed_stability([winner, *(prior[s]["result"] for s in CONFIRMATIONS)], Trial(**winner["trial"]))
    if not stability["passed"]:
        raise ValueError("comparison requires passed seed stability")
    return prior, stability


def prepare(legacy, confirmations, bundle, source, output, custody, source_commit, image_digest, replacement=False):
    prior, stability = local_preflight(legacy, confirmations, bundle, source)
    private = Ed25519PrivateKey.from_private_bytes(custody.read_bytes())
    public = private.public_key().public_bytes_raw().hex()
    if public != CONTEXT_PUBLIC_KEY:
        raise ValueError("comparison signing custody differs")
    builder = comparison_replacement_template if replacement else comparison_template
    request = builder(source_commit, image_digest, public, secrets.token_hex(16))
    validate(request)
    bindings = {**prior[MANIFEST["selected"]["slot"]]["result"]["bindings"],
                "source_commit": source_commit, "image_digest": image_digest}
    origin = checkpoint_origin(request, prior, bindings)
    output.mkdir(parents=True, exist_ok=False)
    path = output / "inference/request.json"
    path.parent.mkdir()
    path.write_bytes(canonical(request))
    command = create_command(request, path)
    command[command.index("--timeout") + 1] = "1h"
    manifest = {"schema_version": "transformer_comparison_preparation_v1",
        "request_sha256": request_sha(request), "request_path": str(path.resolve()),
        "request_bytes": path.stat().st_size, "create_command": shlex.join(command),
        "stability": stability, "checkpoint_origin": origin,
        "verified_prerequisite_artifacts": sum(len(v["inventory"]) for v in prior.values()),
        "jobs_created": 0, "context_attestation_started": False}
    (output / "prepared.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("legacy", "confirmations", "bundle", "source", "output", "custody"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "image-digest"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--replacement", action="store_true")
    result = prepare(**vars(parser.parse_args()))
    print(json.dumps({"requests_prepared": 1, "request_sha256": result["request_sha256"], "jobs_created": 0}))
