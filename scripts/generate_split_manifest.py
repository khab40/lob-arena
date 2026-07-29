import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.governance import GovernedCorpusManifest  # noqa: E402
from app.corpus.models import load_benchmark_protocol  # noqa: E402
from app.corpus.splits import generate_split_manifest, write_split_manifest  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a chronological, session-grouped, purged split manifest."
    )
    parser.add_argument("--corpus", type=Path, required=True, help="Governed corpus manifest JSON")
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs" / "benchmark" / "governed-benchmark-v2-float32.json",
    )
    parser.add_argument("--split-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    corpus = GovernedCorpusManifest.model_validate_json(args.corpus.read_text(encoding="utf-8"))
    protocol = load_benchmark_protocol(args.protocol)
    manifest = generate_split_manifest(
        split_id=args.split_id,
        corpus=corpus,
        protocol=protocol,
    )
    write_split_manifest(args.output, manifest, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "split_id": manifest.split_id,
                "assignment_hash": manifest.assignment_hash,
                "test_frozen": manifest.test_frozen,
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
