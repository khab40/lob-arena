"""Prepare a sealed static overlay; never build, upload, execute models or read S3."""
import argparse
import hashlib
import json
from pathlib import Path
import re

BASE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr@sha256:56ccf4ee7c7bdc7c06f9971223a6158c1080095562e60ca128e0e683e1b6d460"
PACKAGE_SHA = "612a904b055fb18da45f5b7fcbd7e7e4f5556e9f184b6368c381726c6d7dc9e2"
OVERLAY = ("holdout_spec.py", "holdout_context.py", "holdout_data.py", "holdout_baseline.py",
           "holdout_metrics.py", "holdout_storage.py", "holdout_worker.py", "holdout_gpu.py",
           "holdout_readback.py", "holdout_measurements.py", "holdout_runtime.py", "holdout_entrypoint.py",
           "settings_schema.py", "settings_release.py", "research_comparison_readback.py")


def repository(value):
    if len(value) > 64 or not re.fullmatch(r"cr\.eu-north1\.nebius\.cloud/[a-z0-9]+/[a-z0-9-]+", value):
        raise ValueError("digest image repository must satisfy Nebius 64-character limit")
    return value


def prepare(root, output, package, image_repository):
    repository(image_repository)  # Enforce before any build/upload/submission can be attempted.
    root, output, package = map(Path, (root, output, package))
    with package.open("rb") as stream:
        raw = stream.read(512 * 1024 + 1)
    if hashlib.sha256(raw).hexdigest() != PACKAGE_SHA:
        raise ValueError("portable development package differs from verified seven-artifact package")
    lock = root / "configs/experiments/transformer/holdout-runtime-lock-20261005.json"
    pinned = json.loads(lock.read_bytes())
    if (pinned["base_image"] != BASE or any("backend/app/ml/transformer/" + name in pinned["files"]
            for name in OVERLAY)):
        raise ValueError("holdout overlay would replace pinned numerical runtime")
    dockerfile = root / "serverless/transformer_research/Dockerfile.holdout"
    if [line for line in dockerfile.read_text().splitlines() if line.startswith("FROM ")] != ["FROM " + BASE]:
        raise ValueError("holdout image must inherit the verified immutable trained runtime")
    sources = {"backend/app/ml/transformer/" + name: root / "backend/app/ml/transformer" / name
               for name in OVERLAY}
    sources.update({"Dockerfile": dockerfile, "portable-package.json": package, "runtime-lock.json": lock})
    payloads = {name: path.read_bytes() for name, path in sources.items()}
    if payloads["portable-package.json"] != raw:
        raise ValueError("portable package changed during preparation")
    output.mkdir(parents=True, exist_ok=False)
    for name, payload in payloads.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
    receipt = {"base_image": BASE, "image_repository": image_repository,
               "files": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                         for name, raw in payloads.items()},
               "model_execution": False, "cloud_gets": 0, "jobs_created": 0,
               "execution_authorized": False}
    (output / "context-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "output", "package"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--image-repository", required=True)
    print(json.dumps(prepare(**vars(parser.parse_args())), sort_keys=True))
