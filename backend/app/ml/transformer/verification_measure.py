"""One fresh-process measurement of verified input arrays; no model imports."""
from __future__ import annotations

import hashlib
import json
import platform
import resource
import sys
import time
from pathlib import Path

from app.market_data.projections import FrozenPublicSampleRoot
from .batches import iter_batches
from .data import DevelopmentInputs
from .normalization import fit_normalization
from .verification_spec import canonical, checked_file, digest


def measure(inputs: Path, output: Path, *, root_sha, tabular_sha, sequence_sha, expected_rows, size):
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    root = FrozenPublicSampleRoot.model_validate_json(
        checked_file(inputs / "manifests/frozen-root.json", root_sha))
    data = DevelopmentInputs.open(root=root, artifact_root=inputs / "artifacts",
        tabular_path=inputs / "manifests/tabular-projection.json", tabular_sha256=tabular_sha,
        sequence_path=inputs / "manifests/sequence-projection.json", sequence_sha256=sequence_sha)
    opened = time.perf_counter()
    normalization = fit_normalization(data)
    fitted = time.perf_counter()
    logical = hashlib.sha256()
    identities = {fold: hashlib.sha256() for fold in expected_rows}
    counts = dict.fromkeys(expected_rows, 0)
    for batch in iter_batches(data, normalization, batch_size=size):
        for index, target in enumerate(batch.target_ids):
            fold = batch.folds[index]
            identities[fold].update((target + "\n").encode())
            counts[fold] += 1
            logical.update(canonical((target, batch.history_row_ids[index], fold, batch.run_ids[index])) + b"\n")
            for name, dtype in (("values", "<f4"), ("valid_steps", "?"), ("missing_features", "?"),
                                ("causal_allowed", "?"), ("timestamps_ns", "<i8"), ("labels", "<i8")):
                logical.update(getattr(batch, name)[index].astype(dtype).tobytes())
    end = time.perf_counter()
    if counts != expected_rows or normalization.fitting_rows != counts["train"]:
        raise ValueError("consumed fold counts differ from approved release")
    for name, value in (("normalization.json", normalization), ("input-contract.json", data.contract)):
        (output / name).write_bytes(value.canonical_bytes())
    receipt = {"batch_size": size, "fold_rows": counts,
        "fold_identity_sha256": {f: h.hexdigest() for f, h in identities.items()},
        "logical_output_sha256": logical.hexdigest(), "normalization_sha256": normalization.sha256(),
        "contract_sha256": data.contract.sha256(), "preflight_seconds": opened - start,
        "fit_seconds": fitted - opened, "batch_and_digest_seconds": end - fitted,
        "total_seconds": end - start, "batch_windows_per_second": sum(counts.values()) / (end - fitted),
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == "darwin" else 1024),
        "python": platform.python_version(), "platform": platform.platform()}
    (output / "measurement.json").write_bytes(canonical(receipt))
    return receipt


def verify_parity(cases, directories):
    if [r["batch_size"] for r in cases] != [16, 64, 256]:
        raise ValueError("missing approved batch measurements")
    for key in ("fold_rows", "fold_identity_sha256", "logical_output_sha256",
                "normalization_sha256", "contract_sha256"):
        if len({canonical(r[key]) for r in cases}) != 1:
            raise ValueError(f"batch parity failed: {key}")
    for name, key in (("normalization.json", "normalization_sha256"), ("input-contract.json", "contract_sha256")):
        payloads = [d.joinpath(name).read_bytes() for d in directories]
        if len(set(payloads)) != 1 or digest(payloads[0]) != cases[0][key]:
            raise ValueError("artifact byte parity failed")


if __name__ == "__main__":
    from .verification_spec import FOLD_ROWS, ROOT_SHA, SEQUENCE_SHA, TABULAR_SHA
    if len(sys.argv) != 4 or int(sys.argv[3]) not in (16, 64, 256):
        raise SystemExit("usage: verification_measure INPUT_DIRECTORY OUTPUT_DIRECTORY BATCH_SIZE")
    result = measure(Path(sys.argv[1]), Path(sys.argv[2]), root_sha=ROOT_SHA,
        tabular_sha=TABULAR_SHA, sequence_sha=SEQUENCE_SHA, expected_rows=FOLD_ROWS, size=int(sys.argv[3]))
    print(json.dumps(result, sort_keys=True))
