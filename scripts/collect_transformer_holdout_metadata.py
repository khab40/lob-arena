"""Preflight or run the separately approved exact holdout metadata audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def verify_sources(root, pins, *, loaded=False):
    for name, expected in pins.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("operator file escapes reviewed repository")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("operator file differs from reviewed proposal")
    if str(Path(__file__).relative_to(root)) not in pins:
        raise ValueError("operator script is not pinned")
    if loaded:
        for name, module in tuple(sys.modules.items()):
            if name != "collect_transformer_lineage_metadata" and name != "app" and not name.startswith("app."):
                continue
            filename = getattr(module, "__file__", None)
            if filename is None:
                continue  # Namespace paths are checked by verify_imports.
            path = Path(filename)
            relative = str(path.resolve().relative_to(root))
            if relative not in pins or path.is_symlink():
                raise ValueError("loaded operator module is outside the pinned closure")


def run(proposal_path, output=None, approved_proposal_sha256=None, preflight=False):
    root = Path(__file__).resolve().parents[1]
    with Path(proposal_path).open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("metadata proposal exceeds byte bound")
    proposal = json.loads(raw)
    if not preflight and hashlib.sha256(raw).hexdigest() != approved_proposal_sha256:
        raise ValueError("exact operator approval required before credentials")
    verify_sources(root, proposal["operator_files_sha256"])
    from collect_transformer_lineage_metadata import authenticated_client, runtime_probe, verify_imports
    from app.ml.transformer.verification_transport import client
    from app.ml.transformer.holdout_metadata import collect
    verify_imports(root)
    verify_sources(root, proposal["operator_files_sha256"], loaded=True)
    receipt = runtime_probe(client, proposal)
    verify_imports(root)
    verify_sources(root, proposal["operator_files_sha256"], loaded=True)
    if preflight:
        return {"status": "offline_preflight_passed", "runtime": receipt,
                "credentials_read": False, "cloud_gets": 0, "model_execution": False}
    if output is None or Path(output).exists() or Path(output).is_symlink():
        raise ValueError("unused audit output required before credentials")
    s3 = authenticated_client(client)
    try:
        return collect(s3, raw, approved_proposal_sha256, output)
    finally:
        s3.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--approved-proposal-sha256")
    parser.add_argument("--preflight", action="store_true")
    try:
        print(json.dumps(run(**vars(parser.parse_args())), sort_keys=True))
    except Exception as error:
        raise SystemExit("Holdout metadata operator failed: " + type(error).__name__) from None
