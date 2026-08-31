from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("lightgbm", reason="G5 tests require the ml extra")

from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1ExperimentSpec  # noqa: E402
from app.ml.lightgbm.cloud_runner import execute_wave1_request, verify_wave1_result  # noqa: E402
from app.ml.lightgbm.reproducibility import (  # noqa: E402
    _canonical_hash,
    _verified_collection_receipt,
    compare_g5_results,
)
from app.nebius.object_storage import inventory_directory  # noqa: E402
from scripts import lightgbm_wave1 as wave1_script  # noqa: E402


def test_g5_requires_governed_cloud_runs_but_supports_local_preflight(tmp_path: Path) -> None:
    results = _fixture_development_repeats(tmp_path, count=3)

    blocked = tmp_path / "g5-cloud-blocked.json"
    with pytest.raises(ValueError, match="G5 reproducibility gates failed"):
        compare_g5_results(results, blocked)
    blocked_payload = json.loads(blocked.read_text(encoding="utf-8"))
    assert blocked_payload["status"] == "failed"
    assert blocked_payload["gates"]["governed_projection_bound"] is False
    assert blocked_payload["gates"]["verified_collection_receipts"] is False

    comparison = tmp_path / "g5-local-preflight.json"
    compare_g5_results(results, comparison, allow_fixture_preflight=True)
    payload = json.loads(comparison.read_text(encoding="utf-8"))

    assert payload["status"] == "preflight_passed"
    assert payload["scope"] == "local-preflight-only"
    assert payload["repeat_count"] == 3
    assert payload["gates"]["distinct_run_ids"] is True
    assert payload["gates"]["deterministic_evidence_matches"] is True
    assert all(item["matches"] for item in payload["comparisons"].values())


def test_g5_fails_closed_on_experiment_drift(tmp_path: Path) -> None:
    results = _fixture_development_repeats(tmp_path, count=2)
    results.extend(
        _fixture_development_repeats(
            tmp_path,
            count=1,
            start=2,
            experiment=Wave1ExperimentSpec(excluded_features=("spread",)),
        )
    )

    comparison = tmp_path / "g5-drift.json"
    with pytest.raises(ValueError, match="deterministic_evidence_matches"):
        compare_g5_results(results, comparison, allow_fixture_preflight=True)
    payload = json.loads(comparison.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["comparisons"]["request_equivalence_hash"]["matches"] is False
    assert payload["comparisons"]["ordered_features_hash"]["matches"] is False


def test_g5_requires_exactly_three_results_and_receipts(tmp_path: Path) -> None:
    results = _fixture_development_repeats(tmp_path, count=2)

    with pytest.raises(ValueError, match="exactly three results"):
        compare_g5_results(results, tmp_path / "unused.json", allow_fixture_preflight=True)
    with pytest.raises(ValueError, match="exactly three collection receipts"):
        compare_g5_results(
            [*results, results[0]],
            tmp_path / "unused-collections.json",
            collections=[tmp_path / "one.json"],
        )


def test_g5_collection_receipt_is_bound_to_the_downloaded_result(tmp_path: Path) -> None:
    result = _fixture_development_repeats(tmp_path, count=1)[0]
    request = LightGbmCloudJobRequest.model_validate_json((result / "request.json").read_text(encoding="utf-8"))
    run = verify_wave1_result(result)
    receipt = {
        "schema_version": "lightgbm_wave1_collection_v1",
        "verified": True,
        "run_id": request.run_id,
        "request_sha256": request.canonical_hash(),
        "mlflow_run_id": run.mlflow_run_id,
        "nebius_job_id": "aijob-g5receipt",
        "result_sha256": _canonical_hash(inventory_directory(result).model_dump(mode="json")),
        "actual_job_context": {
            "project_id": request.project_id,
            "image": request.image,
            "platform": request.resource.platform,
            "preset": request.resource.preset,
            "disk_size_gib": request.resource.disk_size_gib,
            "timeout_seconds": request.resource.timeout_seconds,
        },
    }
    receipt_path = tmp_path / "collection.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    verified = _verified_collection_receipt(receipt_path, result, request, run.mlflow_run_id)
    assert verified["nebius_job_id"] == "aijob-g5receipt"

    receipt["result_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered-collection.json"
    tampered_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="not bound"):
        _verified_collection_receipt(tampered_path, result, request, run.mlflow_run_id)


def _fixture_development_repeats(
    root: Path,
    *,
    count: int,
    start: int = 0,
    experiment: Wave1ExperimentSpec | None = None,
) -> list[Path]:
    results: list[Path] = []
    for index in range(start, start + count):
        inputs = root / f"g5-input-{index}"
        inputs.mkdir()
        result = root / f"g5-result-{index}"
        request = wave1_script._request(
            campaign_id="wave1-g5-test",
            run_id=f"wave1-g5-repeat-{index}",
            mode="development",
            created_at=datetime(2026, 8, 16, 12, index, tzinfo=UTC),
            result=result,
            experiment=experiment,
        )
        request_path = inputs / "request.json"
        request_path.write_bytes(request.canonical_bytes())
        execute_wave1_request(request_path, input_root=inputs)
        results.append(result)
    return results
