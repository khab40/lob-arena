import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.release import verify_governed_benchmark_release  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a signed governed benchmark release and its complete inventory."
    )
    parser.add_argument("release", type=Path)
    args = parser.parse_args(argv)
    verify_governed_benchmark_release(args.release)
    print(f"verified governed benchmark release: {args.release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
