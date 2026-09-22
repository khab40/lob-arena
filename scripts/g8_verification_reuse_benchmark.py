"""Frozen-image synthetic verification benchmark; no training, scoring or remote calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

PACKAGE = Path("/bench/package")
SCORED = Path("/g8-package/synthetic-final/scored")
CHECKPOINT_SHA = "548355b02bfb27ea57f70f97cbdd74a171bbfb4e4de5a9e0d51a87604461ed87"


def require(value):
    if not value:
        raise ValueError("verification reuse benchmark failed")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap():
    require(sha(Path(__file__)) == os.environ["G8_BENCH_WORKER_SHA256"])
    require(not any(os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "MLFLOW_TRACKING_PASSWORD")))
    source = PACKAGE / "g8_native_bootstrap.py"
    require(sha(source) == os.environ["G8_BENCH_BOOTSTRAP_SHA256"])
    spec = importlib.util.spec_from_file_location("verified_bootstrap", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    finder = module.install(PACKAGE)
    require(sha(SCORED / "checkpoint.json") == CHECKPOINT_SHA)
    marker = json.loads((SCORED / "checkpoint.json").read_bytes())
    for ref in marker["inventory"]["files"]:
        path = SCORED / "payload" / ref["path"]
        require(path.resolve() == path.absolute() and path.is_relative_to(SCORED / "payload"))
        require(path.stat().st_size == ref["size_bytes"] and sha(path) == ref["sha256"])
    return finder


def main():
    def timeout(*_):
        raise TimeoutError("benchmark deadline")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(900)
    finder = bootstrap()
    def guard(event, args):
        if event == "socket.connect":
            raise PermissionError("network outside synthetic benchmark")
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            if name.startswith("/g8-package/") and not name.startswith(str(SCORED) + "/"):
                raise PermissionError("non-synthetic native evidence outside benchmark")
    sys.addaudithook(guard)
    from app.ml.lightgbm import c4_replay_evidence as c4, tracking
    from app.ml.lightgbm.g8_scored_checkpoint import ScoredCheckpoint, _arguments
    from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile
    from app.market_data.projections import FrozenPublicSampleRoot
    from app.ml.lightgbm import cloud_runner, scoring, training

    def forbidden(*_, **__):
        raise AssertionError("model execution outside verification benchmark")
    cloud_runner._run_final = forbidden
    scoring.predict_governed_fold = forbidden
    training.train_binary_attack_model = forbidden

    checkpoint = ScoredCheckpoint.model_validate_json((SCORED / "checkpoint.json").read_bytes())
    target = SimpleNamespace(spec=checkpoint.reservation)
    require(checkpoint.reservation.candidate_sha256 == "e04f50ff0748a0077c0602c397ed7c9c3087757fe0892f1a2d284e91b2383b7c")
    calls = 0
    original = c4.evaluate_c4_observations
    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)
    c4.evaluate_c4_observations = counted

    def verify(payload):
        args = _arguments(payload, checkpoint.context, target)
        with tracking._verified_benchmark_snapshot(args["benchmark_results_path"],
                artifact_root=args["artifact_root"], predictions=args["predictions"],
                c4_inputs=args["c4_evaluation_inputs"]) as value:
            return value[0]

    payload = SCORED / "payload"
    if "--fresh" in sys.argv:
        verify(payload)
        require(calls == 1)
        print(json.dumps({"fresh_process_full_comparisons": calls}), flush=True)
        return
    args = _arguments(payload, checkpoint.context, target)
    inputs = args["c4_evaluation_inputs"]
    initial_start = time.monotonic()
    c4.evaluate_c4_release(profile=C4EvaluationProfile.model_validate_json(inputs.profile.read_bytes()),
        root=FrozenPublicSampleRoot.model_validate_json(inputs.frozen_root.read_bytes()),
        projection_path=inputs.projection, comparison_path=inputs.comparison,
        candidate_path=inputs.candidate, artifact_root=args["artifact_root"], predictions=args["predictions"])
    initial_seconds = time.monotonic() - initial_start
    require(calls == 1 and c4._VERIFIED_COMPARISON is None)
    first_start = time.monotonic()
    expected = verify(payload)
    first_seconds = time.monotonic() - first_start
    require(calls == 2)
    repeats_start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="synthetic-c4-reuse-") as directory:
        copy = Path(directory) / "payload"
        shutil.copytree(payload, copy)
        for _ in range(8):
            require(verify(copy) == expected and calls == 2)
        repeats_seconds = time.monotonic() - repeats_start
        paths = ["metadata/candidate.json", "metadata/profile.json", "metadata/projection.json",
                 "artifacts/" + args["predictions"].predictions.uri]
        paths.append(next(r["path"] for r in json.loads((SCORED / "checkpoint.json").read_bytes())["inventory"]["files"]
                          if r["path"].startswith("comparison/") and r["path"].endswith("/events.jsonl")))
        rejected = 0
        for relative in paths:
            path = copy / relative
            raw = path.read_bytes()
            path.chmod(0o600)
            path.write_bytes(raw + b"\n")
            try:
                verify(copy)
            except (ValueError, RuntimeError):
                rejected += 1
            else:
                raise AssertionError("changed bytes accepted")
            finally:
                path.write_bytes(raw)
            require(calls == 2)
        require(rejected == 5 and verify(copy) == expected)
    fresh = subprocess.run([sys.executable, str(Path(__file__)), "--fresh"],
                           check=True, capture_output=True, text=True, timeout=180)
    require(json.loads(fresh.stdout)["fresh_process_full_comparisons"] == 1)
    print(json.dumps({"schema_version": "g8_verification_reuse_benchmark_v1", "passed": True,
        "synthetic_only": True, "model_training_calls": 0, "model_scoring_calls": 0,
        "production_test_accessed": False, "remote_writes": False, "full_comparison_calls": calls,
        "independent_first_verification_recomputed": True, "unchanged_copy_repeats": 8,
        "changed_inputs_rejected_before_reuse": rejected, "fresh_process_full_comparisons": 1,
        "initial_seconds": initial_seconds, "first_verification_seconds": first_seconds,
        "eight_repeats_seconds": repeats_seconds, "checkpoint_sha256": CHECKPOINT_SHA,
        "overlay_sha256": {name: hashlib.sha256(value[1]).hexdigest() for name, value in finder.sources.items()},
        "production_runtime_established": False}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(json.dumps({"benchmark_passed": False, "error_type": type(error).__name__}), flush=True)
        sys.exit(1)
