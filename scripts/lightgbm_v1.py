import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.lightgbm.contracts import (  # noqa: E402
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    LightGbmV1Hyperparameters,
    ModelBundleManifest,
)
from app.ml.lightgbm.data import load_governed_feature_dataset  # noqa: E402
from app.ml.lightgbm.release import (  # noqa: E402
    build_model_bundle,
    verify_complete_lightgbm_v1_release,
)
from app.ml.lightgbm.scoring import (  # noqa: E402
    calibrate_validation_predictions,
    predict_governed_fold,
)
from app.ml.lightgbm.tracking import (  # noqa: E402
    log_development_run,
    log_governed_evaluation_run,
)
from app.ml.lightgbm.training import train_binary_attack_model  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train, calibrate, evaluate and verify governed LightGBM v1.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Train on governed train/validation folds")
    _add_governed_inputs(train)
    train.add_argument("--artifact-root", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--created-at", required=True)
    train.add_argument("--git-commit", required=True)
    train.add_argument("--model-id", default="lightgbm-attack-active-v1")
    train.add_argument("--training-seed", type=int, default=42)
    train.add_argument("--hyperparameters", type=Path)
    train.add_argument("--early-stopping-rounds", type=int, default=50)
    train.add_argument("--early-stopping-min-delta", type=float, default=0.0)
    train.add_argument("--batch-size", type=int, default=65_536)

    calibrate = subparsers.add_parser("calibrate", help="Fit validation-only calibration and thresholds")
    _add_governed_inputs(calibrate)
    calibrate.add_argument("--artifact-root", type=Path, required=True)
    calibrate.add_argument("--training-manifest", type=Path, required=True)
    calibrate.add_argument("--output", type=Path, required=True)
    calibrate.add_argument("--created-at", required=True)
    calibrate.add_argument("--method", choices=("raw", "platt", "isotonic"), default="platt")
    calibrate.add_argument("--precision-floor", type=float, default=0.90)
    calibrate.add_argument("--recall-floor", type=float, default=0.90)
    calibrate.add_argument("--ece-bins", type=int, default=10)
    calibrate.add_argument("--batch-size", type=int, default=65_536)
    calibrate.add_argument("--mlflow-tracking-uri")

    predict = subparsers.add_parser("predict-test", help="Open and score only the frozen test fold")
    _add_governed_inputs(predict)
    predict.add_argument("--artifact-root", type=Path, required=True)
    predict.add_argument("--training-manifest", type=Path, required=True)
    predict.add_argument("--calibration-manifest", type=Path, required=True)
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--created-at", required=True)
    predict.add_argument(
        "--operating-mode",
        choices=("high_precision", "balanced", "high_recall"),
        default="balanced",
    )
    predict.add_argument("--top-contributions", type=int, default=5)
    predict.add_argument("--batch-size", type=int, default=65_536)

    bundle = subparsers.add_parser("bundle", help="Assemble and verify a checksummed model bundle")
    bundle.add_argument("--artifact-root", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument("--created-at", required=True)
    _add_release_paths(bundle)
    bundle.add_argument("--reliability-bins", type=Path)
    bundle.add_argument("--reliability-diagram", type=Path)
    bundle.add_argument("--mlflow-tracking-uri")
    bundle.add_argument("--benchmark-results", type=Path)

    verify = subparsers.add_parser("verify", help="Verify an existing governed model bundle")
    verify.add_argument("--artifact-root", type=Path, required=True)
    _add_manifest_paths(verify, include_bundle=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "train":
        dataset = _load_dataset(args, access_mode="development")
        hyperparameters = (
            LightGbmV1Hyperparameters.model_validate_json(
                args.hyperparameters.read_text(encoding="utf-8")
            )
            if args.hyperparameters is not None
            else None
        )
        result = train_binary_attack_model(
            dataset,
            output_dir=args.output,
            artifact_root=args.artifact_root,
            created_at=_aware_datetime(args.created_at),
            git_commit=args.git_commit,
            model_id=args.model_id,
            training_seed=args.training_seed,
            hyperparameters=hyperparameters,
            early_stopping_rounds=args.early_stopping_rounds,
            early_stopping_min_delta=args.early_stopping_min_delta,
            batch_size=args.batch_size,
        )
        _print_manifest(result.training_manifest)
        return 0

    if args.command == "calibrate":
        dataset = _load_dataset(args, access_mode="development")
        training = _load_training(args.training_manifest)
        result = calibrate_validation_predictions(
            dataset,
            training=training,
            artifact_root=args.artifact_root,
            output_dir=args.output,
            created_at=_aware_datetime(args.created_at),
            method=args.method,
            precision_floor=args.precision_floor,
            recall_floor=args.recall_floor,
            ece_bins=args.ece_bins,
            batch_size=args.batch_size,
        )
        if args.mlflow_tracking_uri is not None:
            model_path = (args.artifact_root / training.model_artifact.uri).resolve()
            run_id = log_development_run(
                artifact_root=args.artifact_root,
                training=training,
                calibration=result.manifest,
                training_manifest_path=args.training_manifest,
                calibration_manifest_path=result.manifest_path,
                validation_metrics_path=result.validation_metrics_path,
                feature_importance_path=result.feature_importance_path,
                reliability_bins_path=result.reliability_bins_path,
                reliability_diagram_path=result.reliability_diagram_path,
                model_path=model_path,
                tracking_uri=args.mlflow_tracking_uri,
            )
            print(json.dumps({"mlflow_run_id": run_id}, sort_keys=True))
        _print_manifest(result.manifest)
        return 0

    if args.command == "predict-test":
        dataset = _load_dataset(args, access_mode="final_test")
        result = predict_governed_fold(
            dataset,
            training=_load_training(args.training_manifest),
            calibration=_load_calibration(args.calibration_manifest),
            artifact_root=args.artifact_root,
            output_dir=args.output,
            created_at=_aware_datetime(args.created_at),
            operating_mode=args.operating_mode,
            top_contributions=args.top_contributions,
            batch_size=args.batch_size,
        )
        _print_manifest(result.manifest)
        return 0

    if args.command == "bundle":
        training = _load_training(args.training_manifest)
        calibration = _load_calibration(args.calibration_manifest)
        predictions = _load_predictions(args.prediction_manifest)
        result = build_model_bundle(
            args.artifact_root,
            output_dir=args.output,
            training=training,
            calibration=calibration,
            predictions=predictions,
            training_manifest_path=args.training_manifest,
            calibration_manifest_path=args.calibration_manifest,
            prediction_manifest_path=args.prediction_manifest,
            feature_schema_path=args.feature_schema,
            validation_metrics_path=args.validation_metrics,
            feature_importance_path=args.feature_importance,
            contributions_path=args.contributions,
            reliability_bins_path=args.reliability_bins,
            reliability_diagram_path=args.reliability_diagram,
            created_at=_aware_datetime(args.created_at),
        )
        if args.mlflow_tracking_uri is not None:
            run_id = log_governed_evaluation_run(
                artifact_root=args.artifact_root,
                training=training,
                calibration=calibration,
                predictions=predictions,
                bundle=result.bundle,
                bundle_path=result.bundle_path,
                checksum_path=result.checksum_path,
                prediction_manifest_path=args.prediction_manifest,
                benchmark_results_path=args.benchmark_results,
                tracking_uri=args.mlflow_tracking_uri,
            )
            print(json.dumps({"mlflow_run_id": run_id}, sort_keys=True))
        _print_manifest(result.bundle)
        return 0

    training = _load_training(args.training_manifest)
    calibration = _load_calibration(args.calibration_manifest)
    predictions = _load_predictions(args.prediction_manifest)
    bundle = ModelBundleManifest.model_validate_json(
        args.model_bundle.read_text(encoding="utf-8")
    )
    verify_complete_lightgbm_v1_release(
        args.artifact_root,
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )
    _print_manifest(bundle)
    return 0


def _add_governed_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--corpus-validation", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--feature-config", type=Path, required=True)
    parser.add_argument("--feature-release", type=Path, required=True)
    parser.add_argument("--feature-release-sha256", required=True)
    parser.add_argument("--feature-artifact-root", type=Path, required=True)
    parser.add_argument("--corpus-artifact-root", type=Path, required=True)


def _add_manifest_paths(parser: argparse.ArgumentParser, *, include_bundle: bool) -> None:
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--calibration-manifest", type=Path, required=True)
    parser.add_argument("--prediction-manifest", type=Path, required=True)
    if include_bundle:
        parser.add_argument("--model-bundle", type=Path, required=True)


def _add_release_paths(parser: argparse.ArgumentParser) -> None:
    _add_manifest_paths(parser, include_bundle=False)
    parser.add_argument("--feature-schema", type=Path, required=True)
    parser.add_argument("--validation-metrics", type=Path, required=True)
    parser.add_argument("--feature-importance", type=Path, required=True)
    parser.add_argument("--contributions", type=Path, required=True)


def _load_dataset(args: argparse.Namespace, *, access_mode: str):
    return load_governed_feature_dataset(
        protocol_path=args.protocol,
        corpus_manifest_path=args.corpus,
        corpus_validation_path=args.corpus_validation,
        split_manifest_path=args.split,
        feature_config_path=args.feature_config,
        feature_release_manifest_path=args.feature_release,
        expected_feature_release_sha256=args.feature_release_sha256,
        feature_artifact_root=args.feature_artifact_root,
        corpus_artifact_root=args.corpus_artifact_root,
        access_mode=access_mode,
    )


def _load_training(path: Path) -> LightGbmTrainingRun:
    return LightGbmTrainingRun.model_validate_json(path.read_text(encoding="utf-8"))


def _load_calibration(path: Path) -> CalibrationManifest:
    return CalibrationManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _load_predictions(path: Path) -> DetectorPredictionsManifest:
    return DetectorPredictionsManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created-at must include a timezone")
    return parsed


def _print_manifest(manifest: object) -> None:
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
