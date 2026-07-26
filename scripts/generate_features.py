import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.features.io import (  # noqa: E402
    fetch_events,
    iter_events_jsonl,
    iter_fetch_events,
    load_config,
    load_events_jsonl,
    load_labels,
    load_run_metadata,
    write_feature_run,
)
from app.features.pipeline import FeaturePipeline  # noqa: E402
from app.features.streaming import write_streaming_feature_run  # noqa: E402
from app.corpus.governance import (  # noqa: E402
    GovernedCorpusManifest,
    load_adjudications,
    merge_verified_clean_feature_labels,
    validate_adjudications,
    validate_corpus,
)
from app.corpus.models import load_benchmark_protocol  # noqa: E402
from app.evaluation.canonical_bundle import (  # noqa: E402
    bind_replay_manifest_to_corpus_session,
    load_canonical_evaluation_input,
    open_canonical_evaluation_stream,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate versioned causal LOB features from canonical exchange events."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--events", type=Path, help="Canonical exchange-event JSONL")
    source.add_argument(
        "--events-url",
        help="Paginated /api/arena/exchange-events endpoint for the current Java run",
    )
    source.add_argument(
        "--replay-manifest",
        type=Path,
        help="Governed canonical Java replay bundle manifest",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Feature run metadata JSON; required for raw events and derived from governed replay bundles",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "features" / "lightgbm-v1.json",
        help="Versioned feature configuration JSON",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="Separate feature_labels_v1/v2 or scenario ground truth JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Artifact root for paths referenced by --replay-manifest",
    )
    parser.add_argument(
        "--clean-adjudications",
        type=Path,
        help="Governed clean-window adjudication JSONL to export as explicit negative labels",
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        help="Governed corpus manifest binding the replay and clean adjudications",
    )
    parser.add_argument(
        "--benchmark-protocol",
        type=Path,
        default=ROOT / "configs" / "benchmark" / "governed-benchmark-v1.json",
        help="Protocol used to verify governed corpus and clean-window decisions",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Write bounded-memory Parquet row groups instead of retaining feature rows",
    )
    parser.add_argument("--row-group-size", type=int, default=25_000)
    parser.add_argument("--quantile-sample-size", type=int, default=2_048)
    parser.add_argument(
        "--expected-event-count",
        type=int,
        help=(
            "Expected full-stream event count for bounded-state growth evidence; "
            "derived automatically for replay manifests and local JSONL inputs"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    governed_requested = args.clean_adjudications is not None or args.corpus_manifest is not None
    if governed_requested and (
        args.replay_manifest is None
        or args.clean_adjudications is None
        or args.corpus_manifest is None
        or args.artifact_root is None
    ):
        raise ValueError(
            "governed negative labels require --replay-manifest, --clean-adjudications, "
            "--corpus-manifest, and --artifact-root"
        )
    replay = None
    replay_stream = None
    if args.replay_manifest is not None:
        if args.metadata is not None or args.labels is not None:
            raise ValueError("governed replay manifests supply metadata and labels; do not override them")
        if args.streaming:
            replay_stream = open_canonical_evaluation_stream(
                args.replay_manifest,
                artifact_root=args.artifact_root,
            )
            metadata = replay_stream.feature_metadata()
            labels = replay_stream.labels
            events = replay_stream.iter_events()
        else:
            replay = load_canonical_evaluation_input(
                args.replay_manifest,
                artifact_root=args.artifact_root,
            )
            metadata = replay.feature_metadata()
            labels = replay.labels
            events = replay.events
    else:
        if args.metadata is None:
            raise ValueError("--metadata is required with --events or --events-url")
        metadata = load_run_metadata(args.metadata)
        labels = load_labels(args.labels)
        if args.streaming:
            events = (
                iter_events_jsonl(args.events)
                if args.events is not None
                else iter_fetch_events(args.events_url, timeout=args.timeout)
            )
        else:
            events = (
                load_events_jsonl(args.events)
                if args.events is not None
                else fetch_events(args.events_url, timeout=args.timeout)
            )
    governed_label_provenance: dict[str, object] = {}
    if governed_requested:
        replay_manifest = replay.manifest if replay is not None else replay_stream.manifest
        protocol = load_benchmark_protocol(args.benchmark_protocol)
        corpus = GovernedCorpusManifest.model_validate_json(
            args.corpus_manifest.read_text(encoding="utf-8")
        )
        corpus_validation = validate_corpus(
            corpus,
            protocol,
            artifact_root=args.artifact_root,
        )
        if corpus_validation.verdict != "pass":
            raise ValueError("governed corpus failed local artifact validation")
        adjudications = load_adjudications(args.clean_adjudications)
        validate_adjudications(
            adjudications,
            manifest=corpus,
            protocol=protocol,
            artifact_root=args.artifact_root,
        )
        sessions = {
            session.base_session_id: session
            for session in corpus.sessions
        }
        session = sessions.get(replay_manifest.base_session_id)
        if session is None:
            raise ValueError("replay base session is absent from the governed corpus")
        bind_replay_manifest_to_corpus_session(replay_manifest, session)
        labels = merge_verified_clean_feature_labels(
            labels,
            adjudications,
            base_session_id=replay_manifest.base_session_id,
            replay_mode=replay_manifest.mode,
        )
        governed_label_provenance = {
            "governed_corpus_id": corpus.corpus_id,
            "governed_corpus_sha256": corpus.corpus_hash(),
            "governed_protocol_id": protocol.protocol_id,
            "governed_protocol_sha256": protocol.protocol_hash(),
            "clean_adjudications_sha256": _sha256(args.clean_adjudications),
            "clean_negative_window_ids": sorted(
                window.provenance_id
                for window in labels.labels
                if window.label == 0 and window.provenance_id is not None
            ),
            "clean_negative_window_count": sum(
                window.label == 0
                for window in labels.labels
            ),
            "clean_label_artifact_verification_mode": corpus_validation.artifact_verification_mode,
        }
    expected_event_count = args.expected_event_count
    if replay is not None:
        expected_event_count = replay.manifest.event_count
    elif replay_stream is not None:
        expected_event_count = replay_stream.manifest.event_count
    elif expected_event_count is None and args.events is not None:
        expected_event_count = _nonempty_line_count(args.events)
    pipeline = FeaturePipeline(
        config,
        metadata,
        labels,
        expected_event_count=expected_event_count,
    )
    if args.streaming:
        governed_manifest = (
            replay.manifest
            if replay is not None
            else replay_stream.manifest
            if replay_stream is not None
            else None
        )
        replay_provenance = (
            {
                "canonical_java_replay_bundle": governed_manifest.schema_version,
                "java_engine_version": governed_manifest.java_engine_version,
                "java_canonical_event_stream_hash": governed_manifest.canonical_event_stream_hash,
                "replay_manifest_sha256": _sha256(args.replay_manifest),
            }
            if governed_manifest is not None
            else {}
        )
        replay_provenance.update(governed_label_provenance)
        manifest = write_streaming_feature_run(
            args.output,
            events=events,
            pipeline=pipeline,
            config=config,
            metadata=metadata,
            row_group_size=args.row_group_size,
            quantile_sample_size=args.quantile_sample_size,
            overwrite=args.overwrite,
            extra_input_provenance=replay_provenance,
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        if config.fail_on_invalid_rows and manifest["output"]["invalid_row_count"]:
            print(
                "feature generation completed with invalid rows; inspect feature-quality.json",
                file=sys.stderr,
            )
            return 2
        return 0
    result = pipeline.generate(events)
    if replay is not None:
        if result.input_sha256 != replay.feature_input_sha256:
            raise ValueError("feature input digest diverged from governed replay validation")
        result.input_provenance.update(
            {
                "canonical_java_replay_bundle": replay.manifest.schema_version,
                "java_engine_version": replay.manifest.java_engine_version,
                "java_canonical_event_stream_hash": replay.manifest.canonical_event_stream_hash,
                "replay_manifest_sha256": _sha256(args.replay_manifest),
            }
        )
    result.input_provenance.update(governed_label_provenance)
    manifest = write_feature_run(
        args.output,
        result=result,
        config=config,
        metadata=metadata,
        overwrite=args.overwrite,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if config.fail_on_invalid_rows and result.quality_report["invalid_row_count"]:
        print(
            "feature generation completed with invalid rows; inspect feature-quality.json",
            file=sys.stderr,
        )
        return 2
    return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty_line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for line in handle:
            count += bool(line.strip())
    if count < 1:
        raise ValueError("canonical event input requires at least one non-empty line")
    return count


if __name__ == "__main__":
    raise SystemExit(main())
