import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.governance import (  # noqa: E402
    build_corpus_manifest,
    load_adjudications,
    load_sessions,
    validate_adjudications,
    validate_corpus,
    write_corpus_bundle,
)
from app.corpus.models import load_benchmark_protocol  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and validate a provenance-bound governed corpus manifest."
    )
    parser.add_argument("--sessions", type=Path, required=True, help="Governed session JSON array")
    parser.add_argument("--adjudications", type=Path, help="Clean-window adjudication JSONL")
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs" / "benchmark" / "governed-benchmark-v2-float32.json",
    )
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Write a provisional failing validation bundle; never use it for training.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    protocol = load_benchmark_protocol(args.protocol)
    sessions = load_sessions(args.sessions)
    manifest = build_corpus_manifest(
        corpus_id=args.corpus_id,
        sessions=sessions,
        protocol=protocol,
    )
    adjudications = load_adjudications(args.adjudications)
    validate_adjudications(
        adjudications,
        manifest=manifest,
        protocol=protocol,
        artifact_root=args.artifact_root,
    )
    validation = validate_corpus(manifest, protocol, artifact_root=args.artifact_root)
    if validation.verdict != "pass" and not args.allow_incomplete:
        print(json.dumps(validation.model_dump(mode="json"), indent=2, sort_keys=True))
        print("governed corpus validation failed; use --allow-incomplete only for provisional review", file=sys.stderr)
        return 2
    write_corpus_bundle(
        args.output,
        manifest=manifest,
        validation=validation,
        adjudications=adjudications,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "corpus_id": manifest.corpus_id,
                "protocol_hash": manifest.protocol_hash,
                "verdict": validation.verdict,
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if validation.verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
