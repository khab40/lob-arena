#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.market_data.projections import (  # noqa: E402
    C4MlflowDatasetReleaseReceipt,
    FrozenPublicSampleRoot,
)
from app.market_data.tracking import log_frozen_dataset_release  # noqa: E402
from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and index a fold-isolated C4 dataset release in MLflow."
    )
    parser.add_argument("--frozen-root", type=Path, required=True)
    _projection_arguments(parser, "tabular-development")
    _projection_arguments(parser, "tabular-final")
    _projection_arguments(parser, "sequence-development")
    _projection_arguments(parser, "sequence-final")
    parser.add_argument("--access-denial", type=Path, required=True)
    parser.add_argument("--mlflow-tracking-uri", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.evidence_output.exists():
        raise FileExistsError("C4 MLflow evidence output must be new")
    run_id = log_frozen_dataset_release(
        frozen_root_path=args.frozen_root,
        tabular_development_path=args.tabular_development_manifest,
        tabular_development_artifact_root=args.tabular_development_artifact_root,
        tabular_development_source_uri=args.tabular_development_source_uri,
        tabular_final_path=args.tabular_final_manifest,
        tabular_final_artifact_root=args.tabular_final_artifact_root,
        tabular_final_source_uri=args.tabular_final_source_uri,
        sequence_development_path=args.sequence_development_manifest,
        sequence_development_artifact_root=args.sequence_development_artifact_root,
        sequence_development_source_uri=args.sequence_development_source_uri,
        sequence_final_path=args.sequence_final_manifest,
        sequence_final_artifact_root=args.sequence_final_artifact_root,
        sequence_final_source_uri=args.sequence_final_source_uri,
        access_denial_path=args.access_denial,
        tracking_uri=args.mlflow_tracking_uri,
    )
    root = FrozenPublicSampleRoot.model_validate_json(args.frozen_root.read_text(encoding="utf-8"))
    receipt = C4MlflowDatasetReleaseReceipt(
        mlflow_run_id=run_id,
        release_id=root.release_id,
        root_file_sha256=sha256_file(args.frozen_root),
        root_identity_sha256=root.canonical_hash(),
        tabular_development_sha256=sha256_file(args.tabular_development_manifest),
        tabular_final_sha256=sha256_file(args.tabular_final_manifest),
        sequence_development_sha256=sha256_file(args.sequence_development_manifest),
        sequence_final_sha256=sha256_file(args.sequence_final_manifest),
        access_denial_sha256=sha256_file(args.access_denial),
    )
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_output.write_bytes(receipt.canonical_bytes())
    print(run_id)
    return 0


def _projection_arguments(parser: argparse.ArgumentParser, prefix: str) -> None:
    parser.add_argument(f"--{prefix}-manifest", type=Path, required=True)
    parser.add_argument(f"--{prefix}-artifact-root", type=Path, required=True)
    parser.add_argument(f"--{prefix}-source-uri", required=True)


if __name__ == "__main__":
    raise SystemExit(main())
