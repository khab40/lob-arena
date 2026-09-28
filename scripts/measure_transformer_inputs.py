"""Measure inert input preparation, never training, scoring or final-test data."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]

from app.market_data.projections import FrozenPublicSampleRoot  # noqa: E402
from app.ml.transformer.batches import iter_batches  # noqa: E402
from app.ml.transformer.data import DevelopmentInputs  # noqa: E402
from app.ml.transformer.normalization import fit_normalization  # noqa: E402
from transformer_input_fixtures import make_inputs  # noqa: E402


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def peak_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024**2 if sys.platform == "darwin" else 1024)


def measure(fixture, size):
    request = json.loads((fixture / "request.json").read_text())
    baseline = peak_mib()
    start = time.perf_counter()
    data = DevelopmentInputs.open(root=FrozenPublicSampleRoot.model_validate(request["root"]),
              artifact_root=fixture, tabular_path=fixture / "tabular.json",
              sequence_path=fixture / "sequence.json", tabular_sha256=request["tabular_sha256"],
              sequence_sha256=request["sequence_sha256"])
    opened = time.perf_counter()
    normalization = fit_normalization(data)
    fitted = time.perf_counter()
    output = hashlib.sha256()
    count = 0
    for batch in iter_batches(data, normalization, batch_size=size):
        for index, target in enumerate(batch.target_ids):
            metadata = (target, batch.history_row_ids[index], batch.folds[index], batch.run_ids[index])
            output.update(json.dumps(metadata, separators=(",", ":")).encode() + b"\n")
            for name, dtype in (("values", "<f4"), ("valid_steps", "?"), ("missing_features", "?"),
                                ("causal_allowed", "?"), ("timestamps_ns", "<i8"), ("labels", "<i8")):
                output.update(getattr(batch, name)[index].astype(dtype).tobytes())
            count += 1
    end = time.perf_counter()
    assert count == request["windows"]
    for name, value in (("normalization.json", normalization), ("input-contract.json", data.contract)):
        path = fixture / name
        if path.exists():
            assert path.read_bytes() == value.canonical_bytes()
        else:
            with path.open("xb") as stream:
                stream.write(value.canonical_bytes())
    return {"windows": count, "batch_size": size, "preflight_seconds": opened - start,
            "fit_seconds": fitted - opened, "batch_and_digest_seconds": end - fitted,
            "total_seconds": end - start, "windows_per_second": count / (end - fitted),
            "baseline_peak_rss_mib": baseline, "peak_rss_mib": peak_mib(),
            "logical_output_sha256": output.hexdigest(), "contract_sha256": data.contract.sha256(),
            "normalization_sha256": normalization.sha256(), "request_sha256": digest(fixture / "request.json")}


def campaign(output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for count in (1024, 8192):
        fixture = output / f"fixture-{count}"
        args = make_inputs(fixture, count=count // 2)
        request = {"root": args["root"].model_dump(mode="json"), "windows": count,
                   "tabular_sha256": args["tabular_sha256"], "sequence_sha256": args["sequence_sha256"]}
        (fixture / "request.json").write_text(json.dumps(request, sort_keys=True) + "\n")
        for size in (16, 64, 256):
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                         "--fixture", str(fixture), "--batch-size", str(size)],
                         capture_output=True, text=True, check=True, timeout=300)
            row = json.loads(process.stdout)
            results.append(row)
            print(f"Verified {count} windows, batch {size}: {row['total_seconds']:.2f}s, "
                  f"peak {row['peak_rss_mib']:.1f} MiB", flush=True)
        assert len({r["logical_output_sha256"] for r in results if r["windows"] == count}) == 1
        assert len({r["normalization_sha256"] for r in results if r["windows"] == count}) == 1
    files = [*sorted((ROOT / "backend/app/ml/transformer").glob("*.py")),
             ROOT / "backend/tests/transformer_input_fixtures.py", Path(__file__).resolve()]
    receipt = {"schema_version": 1, "scope": "inert_fixture_input_preparation_only",
               "observed_at": datetime.now(UTC).isoformat(), "platform": platform.platform(),
               "machine": platform.machine(), "python": platform.python_version(),
               "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
               "fixture_recipe": "deterministic_counter_features_v1_no_randomness",
               "sequence_length": 64, "features": 60, "cloud_jobs": 0, "model_runs": 0,
               "results": results, "batch_invariance": "passed",
               "limitations": ["one local process per case, not a production performance estimate",
                               "preflight and fit are separate from reported batching throughput",
                               "fixture generation excluded from child-process RSS",
                               "no governed C4 runtime verification or model qualification"]}
    (output / "measurements.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--fixture", type=Path)
    parser.add_argument("--batch-size", type=int, choices=(16, 64, 256), default=64)
    args = parser.parse_args()
    if args.fixture:
        print(json.dumps(measure(args.fixture.resolve(), args.batch_size)))
    else:
        campaign(args.output.resolve())
