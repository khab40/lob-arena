from datetime import UTC, datetime
from pathlib import Path
import json

import pytest

pytest.importorskip("lightgbm")

from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1ExperimentSpec  # noqa: E402
from app.ml.lightgbm.cloud_runner import execute_wave1_request  # noqa: E402
from app.ml.lightgbm.g8_benchmark_readiness import assess_benchmark_compatibility  # noqa: E402
from serverless.jobs.g8_rehearsal import IMAGE, projections, projected_input  # noqa: E402
from scripts.lightgbm_wave1 import main  # noqa: E402


@pytest.fixture()
def audit_inputs(tmp_path):
    development, _ = projections(tmp_path / "fixtures")
    selected = tmp_path / "selected"
    request = LightGbmCloudJobRequest(
        campaign_id="readiness-fixture",
        run_id="readiness-development",
        mode="development",
        project_id="project-e00g6zvxpr00waz8t3y51k",
        image=IMAGE,
        created_at=datetime.now(UTC),
        git_commit="0" * 40,
        experiment=Wave1ExperimentSpec(),
        input=projected_input(development),
        result_uri=selected.as_uri(),
    )
    request_path = development / "request.json"
    request_path.write_bytes(request.canonical_bytes())
    execute_wave1_request(request_path, input_root=development)
    return dict(
        frozen_root_path=development / "manifests/frozen-root.json",
        lineage_path=development / "manifests/c4-mlflow-dataset-release.json",
        candidate_path=selected / "candidate.json",
        benchmark_protocol_path=Path(__file__).resolve().parents[2] / "configs/benchmark/nasdaq-public-sample-v1.json",
    )


def test_same_protocol_name_does_not_bypass_different_hash(audit_inputs, monkeypatch):
    original = Path.open

    def metadata_only(path, *args, **kwargs):
        assert path.suffix not in {".parquet", ".jsonl", ".gz"}
        assert path.name != "model.txt"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", metadata_only)
    report = assess_benchmark_compatibility(**audit_inputs)
    assert report["candidate_c4_binding_verified"]
    assert report["frozen_protocol_id"] == report["benchmark_protocol_id"]
    assert report["blocking_reasons"] == ["protocol_hash_mismatch", "insufficient_frozen_source_dates"]
    assert not report["test_rows_read_by_audit"]
    assert not report["submission_authorized"]


def test_changed_candidate_training_metadata_fails_before_reporting(audit_inputs):
    candidate = audit_inputs["candidate_path"]
    training = candidate.parent / "artifacts/training/training-run.json"
    training.write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        assess_benchmark_compatibility(**audit_inputs)


def test_changed_root_rejected_against_lineage(audit_inputs):
    path = audit_inputs["frozen_root_path"]
    root = json.loads(path.read_text())
    root["protocol_sha256"] = "e" * 64
    path.write_text(json.dumps(root))
    with pytest.raises(ValueError, match="dataset lineage"):
        assess_benchmark_compatibility(**audit_inputs)


def test_cli_records_blocker_and_returns_nonzero(audit_inputs, tmp_path):
    output = tmp_path / "audit.json"
    args = [
        "g8-benchmark-readiness",
        "--frozen-root",
        str(audit_inputs["frozen_root_path"]),
        "--c4-mlflow-evidence",
        str(audit_inputs["lineage_path"]),
        "--candidate",
        str(audit_inputs["candidate_path"]),
        "--benchmark-protocol",
        str(audit_inputs["benchmark_protocol_path"]),
        "--output",
        str(output),
    ]
    assert main(args) == 2
    assert json.loads(output.read_text())["status"] == "incompatible"
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        main(args)
    assert output.read_bytes() == original
