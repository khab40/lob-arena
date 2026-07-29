import argparse
import json
import sys
from pathlib import Path
from typing import Type

from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.corpus.governance import (  # noqa: E402
    CleanWindowAdjudication,
    GovernedCorpusManifest,
)
from app.corpus.models import GovernedBenchmarkProtocol  # noqa: E402
from app.corpus.splits import GovernedSplitManifest  # noqa: E402
from app.evaluation.regimes import GovernedRegimeEvidence  # noqa: E402
from app.features.streaming import StreamingValidationEvidence  # noqa: E402
from app.ml.lightgbm.contracts import (  # noqa: E402
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
)
from app.ml.lightgbm.feature_release import (  # noqa: E402
    GovernedFeatureReleaseManifest,
)


CONTRACTS: dict[str, tuple[Type[BaseModel], str]] = {
    "governed-benchmark-protocol-v1.schema.json": (
        GovernedBenchmarkProtocol,
        "LOB Arena Governed Benchmark Protocol v1",
    ),
    "governed-corpus-v1.schema.json": (
        GovernedCorpusManifest,
        "LOB Arena Governed Corpus v1",
    ),
    "clean-window-adjudication-v1.schema.json": (
        CleanWindowAdjudication,
        "LOB Arena Clean Window Adjudication v1",
    ),
    "split-manifest-v1.schema.json": (
        GovernedSplitManifest,
        "LOB Arena Governed Split Manifest v1",
    ),
    "feature-streaming-validation-v1.schema.json": (
        StreamingValidationEvidence,
        "LOB Arena Feature Streaming Validation v1",
    ),
    "governed-regime-evidence-v1.schema.json": (
        GovernedRegimeEvidence,
        "LOB Arena Governed Regime Evidence v1",
    ),
    "governed-feature-release-v1.schema.json": (
        GovernedFeatureReleaseManifest,
        "LOB Arena Governed Feature Release v1",
    ),
    "lightgbm-training-run-v1.schema.json": (
        LightGbmTrainingRun,
        "LOB Arena LightGBM Training Run v1",
    ),
    "lightgbm-model-bundle-v1.schema.json": (
        ModelBundleManifest,
        "LOB Arena LightGBM Model Bundle v1",
    ),
    "model-calibration-v1.schema.json": (
        CalibrationManifest,
        "LOB Arena Model Calibration v1",
    ),
    "detector-predictions-v1.schema.json": (
        DetectorPredictionsManifest,
        "LOB Arena Detector Predictions v1",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate fail-closed governed JSON Schemas from runtime Pydantic models."
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stale: list[str] = []
    for filename, (model, title) in CONTRACTS.items():
        rendered = render_contract(filename, model, title)
        path = ROOT / "contracts" / filename
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                stale.append(filename)
        else:
            path.write_text(rendered, encoding="utf-8")
    if stale:
        raise SystemExit(f"generated governed contracts are stale: {', '.join(stale)}")
    return 0


def render_contract(
    filename: str,
    model: Type[BaseModel],
    title: str,
) -> str:
    schema = model.model_json_schema()
    _require_serialized_fields(schema)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://lob-arena.local/contracts/{filename}",
            "title": title,
        }
    )
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _require_serialized_fields(node: object) -> None:
    if isinstance(node, dict):
        if "const" in node:
            constant = node["const"]
            node.clear()
            node["const"] = constant
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
        for value in node.values():
            _require_serialized_fields(value)
    elif isinstance(node, list):
        for value in node:
            _require_serialized_fields(value)


if __name__ == "__main__":
    raise SystemExit(main())
