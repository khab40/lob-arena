"""Build an unsigned production review package; cannot authorize or submit a Job."""
from __future__ import annotations

import argparse
import ast
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.g8_production_review_inputs import collect, digest  # noqa: E402


def prepare(*, r4, candidate, rehearsal, output, run_id, frozen_root=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,53}", run_id):
        raise ValueError("bounded new run ID required, including recovery name headroom")
    if output.absolute() != output.resolve():
        raise ValueError("canonical review destination required")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        raise ValueError("clean source checkout required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    # Inspect literal constants without importing the model/evaluation runtime.
    source = ROOT / "backend/app/ml/lightgbm/g8_replacement.py"
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(source.read_text()).body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in {"IMAGE", "CANDIDATE", "FINAL_RELEASE", "FROZEN_ROOT", "FINAL_PROJECTION", "MODULES"}}
    bindings, request, metadata, history, native, remote = collect(r4, candidate, rehearsal, constants, run_id)
    request.update(created_at=datetime.now(UTC).isoformat(), git_commit=commit)
    helper = ROOT / "backend/app/ml/lightgbm/g8_production_transport.py"
    spec = importlib.util.spec_from_file_location("production_transport_static", helper)
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)  # stdlib-only archive builder, no model imports.
    paths = {name + ".py": "/job/backend/app/ml/lightgbm/" + name + ".py" for name in constants["MODULES"]}
    paths.update({name: "/job/g8/" + name for name in ("run_lightgbm_g8.py", "run_lightgbm_g8_replacement.py")})
    code = {name: (ROOT / ("backend/app/ml/lightgbm" if name.removesuffix(".py") in constants["MODULES"]
                           else "serverless/jobs") / name).read_bytes() for name in paths}
    files = {**code, **transport.build_archives(code, paths), **metadata,
             transport.BOOTSTRAP: (ROOT / "serverless/jobs" / transport.BOOTSTRAP).read_bytes()}
    def canonical(value):
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    files.update({"native-durability.json": canonical(native), "remote-roundtrip.json": canonical(remote)})
    if frozen_root:
        raw = frozen_root.read_bytes()
        if digest(raw) != constants["FROZEN_ROOT"]:
            raise ValueError("frozen root metadata differs")
        files["frozen-root.json"] = raw
    if any(not 0 < len(raw) <= transport.MAX_FILE for raw in files.values()):
        raise ValueError("physical review member exceeds native transport bound")
    output.mkdir(parents=True, exist_ok=False)
    package = output / "package"
    package.mkdir()
    for name, raw in files.items():
        (package / name).write_bytes(raw)
    for name, raw in history.items():
        destination = output / "history" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    transport.verify_archives(package, paths)
    (output / "request.review.json").write_bytes(canonical(request))
    missing = [name for name in ("frozen-root.json", "projection.json", "profile.json", "comparison-inventory.json",
                               "c4-inputs.json", "authorization.json", "authorization.sig", "authorization-public.pem")
               if name not in files]
    review = {"schema_version": "g8_production_package_review_v1", "status": "unsigned_review_not_executable",
        "source_commit": commit, "bindings": bindings, "result_uri": request["result_uri"],
        "frozen_input": request["input"], "request_draft_sha256": digest(canonical(request)),
        "native_package_path": transport.PACKAGE, "bootstrap_injection_count": 1,
        "deployment_image_alias_requires_fresh_registry_check": transport.DEPLOYMENT_IMAGE,
        "mounts": [bindings["filesystem_id"] + ":/g8-durable:rw", bindings["filesystem_id"] + ":/g8-package:ro"],
        "files": {name: {"sha256": digest(raw), "size_bytes": len(raw)} for name, raw in files.items()},
        "history_files": {name: {"sha256": digest(raw), "size_bytes": len(raw)} for name, raw in history.items()},
        "remaining_before_signing": missing + ["original Java comparison evidence and dataset registration verification",
            "production transport runtime verification on Nebius", "fresh identity/storage/output/registry preflight",
            "replacement-specific final-test approval", "canonical request and signed replacement.json v3"],
        "prior_authorization_reused": False, "production_execution_authorized": False,
        "jobs_submitted": 0, "production_data_downloaded": False}
    raw = canonical(review)
    (output / "production-review.json").write_bytes(raw)
    (output / "production-review.sha256").write_text(digest(raw) + "  production-review.json\n")
    return {"review_sha256": digest(raw), "source_commit": commit, "run_id": run_id,
            "status": review["status"], "physical_files": len(files), "missing_files": missing,
            "production_execution_authorized": False, "jobs_submitted": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("r4", "candidate", "rehearsal", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path)
    parser.add_argument("--run-id", required=True)
    print(json.dumps(prepare(**vars(parser.parse_args())), indent=2))
