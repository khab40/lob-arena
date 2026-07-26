import argparse
import hashlib
import json
import platform
import resource
import sys
import time
import tracemalloc
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.governance import GovernedCorpusManifest  # noqa: E402
from app.corpus.models import load_benchmark_protocol  # noqa: E402
from app.evaluation.canonical_bundle import (  # noqa: E402
    CanonicalJavaReplayManifest,
    bind_replay_manifest_to_corpus_session,
)
from app.features.streaming import StreamingValidationEvidence  # noqa: E402
from scripts.generate_features import main as generate_features  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark bounded-memory full-session feature generation."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--events", type=Path)
    source.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "features" / "lightgbm-v1.json",
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--row-group-size", type=int, default=25_000)
    parser.add_argument("--comparison-row-group-size", type=int)
    parser.add_argument("--comparison-output", type=Path)
    parser.add_argument("--quantile-sample-size", type=int, default=2_048)
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Governed corpus manifest; requires --replay-manifest and emits release-gate evidence",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs" / "benchmark" / "governed-benchmark-v1.json",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.row_group_size < 1:
        raise ValueError("--row-group-size must be positive")
    comparison_size = args.comparison_row_group_size or (
        2 if args.row_group_size == 1 else max(1, args.row_group_size // 2)
    )
    if comparison_size < 1 or comparison_size == args.row_group_size:
        raise ValueError("comparison row-group size must be positive and differ from primary size")
    comparison_output = args.comparison_output or args.output.with_name(
        f"{args.output.name}-chunk-{comparison_size}"
    )
    if comparison_output.resolve() == args.output.resolve():
        raise ValueError("primary and comparison feature outputs must differ")
    if args.corpus is not None and args.replay_manifest is None:
        raise ValueError("governed streaming evidence requires --replay-manifest")

    command = _generation_command(args, output=args.output, row_group_size=args.row_group_size)
    comparison_command = _generation_command(
        args,
        output=comparison_output,
        row_group_size=comparison_size,
    )

    tracemalloc.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    exit_code = generate_features(command)
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    _, python_peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if exit_code != 0:
        return exit_code
    comparison_exit_code = generate_features(comparison_command)
    if comparison_exit_code != 0:
        return comparison_exit_code

    manifest = json.loads((args.output / "run-metadata.json").read_text(encoding="utf-8"))
    comparison_manifest = json.loads(
        (comparison_output / "run-metadata.json").read_text(encoding="utf-8")
    )
    event_count = int(manifest["input"]["canonical_event_count"])
    row_count = int(manifest["output"]["row_count"])
    logical_hashes = {
        args.row_group_size: manifest["output"]["logical_feature_rows_sha256"],
        comparison_size: comparison_manifest["output"]["logical_feature_rows_sha256"],
    }
    if (
        comparison_manifest["input"]["canonical_event_count"] != event_count
        or comparison_manifest["input"]["canonical_event_stream_sha256"]
        != manifest["input"]["canonical_event_stream_sha256"]
        or len(set(logical_hashes.values())) != 1
    ):
        raise ValueError("streaming output changed across configured row-group sizes")
    benchmark = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "input": {
            "feature_row_count": row_count,
            "canonical_event_stream_sha256": manifest["input"]["canonical_event_stream_sha256"],
        },
        "configuration": {
            "primary": manifest["streaming"],
            "comparison": comparison_manifest["streaming"],
        },
        "performance": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "feature_rows_per_second": row_count / wall_seconds if wall_seconds else None,
            "python_tracemalloc_peak_bytes": python_peak_bytes,
            "process_peak_rss_bytes": _peak_rss_bytes(),
            "output_bytes": int(manifest["output"]["feature_file_size_bytes"]),
        },
    }
    events_per_second = event_count / wall_seconds if wall_seconds else 0.0
    if args.corpus is not None:
        report = _governed_evidence(
            args,
            manifest=manifest,
            event_count=event_count,
            events_per_second=events_per_second,
            logical_hashes=logical_hashes,
            benchmark=benchmark,
        )
    else:
        report = {
            "schema_version": "feature_streaming_benchmark_v2",
            "verdict": "pass",
            "full_session": False,
            "canonical_event_count": event_count,
            "events_per_second": events_per_second,
            "memory_growth_fraction": manifest["input"].get(
                "bounded_state_growth_fraction"
            ),
            "logical_hashes_by_chunk_size": logical_hashes,
            "benchmark": benchmark,
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _generation_command(
    args: argparse.Namespace,
    *,
    output: Path,
    row_group_size: int,
) -> list[str]:
    command = [
        "--config",
        str(args.config),
        "--output",
        str(output),
        "--streaming",
        "--row-group-size",
        str(row_group_size),
        "--quantile-sample-size",
        str(args.quantile_sample_size),
    ]
    if args.events is not None:
        if args.metadata is None:
            raise ValueError("--metadata is required with --events")
        command.extend(["--events", str(args.events), "--metadata", str(args.metadata)])
        if args.labels is not None:
            command.extend(["--labels", str(args.labels)])
    else:
        command.extend(["--replay-manifest", str(args.replay_manifest)])
        if args.artifact_root is not None:
            command.extend(["--artifact-root", str(args.artifact_root)])
    if args.overwrite:
        command.append("--overwrite")
    return command


def _governed_evidence(
    args: argparse.Namespace,
    *,
    manifest: dict[str, object],
    event_count: int,
    events_per_second: float,
    logical_hashes: dict[int, str],
    benchmark: dict[str, object],
) -> dict[str, object]:
    protocol = load_benchmark_protocol(args.protocol)
    corpus = GovernedCorpusManifest.model_validate_json(
        args.corpus.read_text(encoding="utf-8")
    )
    replay = CanonicalJavaReplayManifest.model_validate_json(
        args.replay_manifest.read_text(encoding="utf-8")
    )
    sessions = {
        session.base_session_id: session
        for session in corpus.sessions
    }
    session = sessions.get(replay.base_session_id)
    if session is None:
        raise ValueError("streaming replay session is absent from the governed corpus")
    if replay.mode != "historical_control" or not session.complete_session:
        raise ValueError("streaming release evidence requires a complete historical-control replay")
    bind_replay_manifest_to_corpus_session(replay, session)
    if event_count != replay.event_count:
        raise ValueError("streaming event count does not match the canonical replay manifest")
    memory_growth = manifest["input"].get("bounded_state_growth_fraction")
    if not isinstance(memory_growth, (int, float)):
        raise ValueError("streaming run did not produce bounded-state growth evidence")
    if memory_growth > protocol.streaming.max_memory_growth_fraction:
        raise ValueError("streaming bounded-state growth exceeds the governed protocol")
    evidence = StreamingValidationEvidence(
        verdict="pass",
        protocol_hash=protocol.protocol_hash(),
        corpus_hash=corpus.corpus_hash(),
        base_session_id=session.base_session_id,
        control_replay_manifest_sha256=_sha256(args.replay_manifest),
        canonical_event_stream_hash=replay.canonical_event_stream_hash,
        full_session=True,
        canonical_event_count=event_count,
        memory_growth_fraction=float(memory_growth),
        events_per_second=events_per_second,
        logical_hashes_by_chunk_size=logical_hashes,
        benchmark=benchmark,
    )
    return evidence.model_dump(mode="json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _peak_rss_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


if __name__ == "__main__":
    raise SystemExit(main())
