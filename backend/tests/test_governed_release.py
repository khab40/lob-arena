import json
import subprocess
from pathlib import Path

import pytest

from app.evaluation.governed_metrics import SessionMetricComponents
from app.evaluation.release import (
    verify_governed_benchmark_release,
    write_governed_benchmark_release,
)


def _results() -> dict:
    return {
        "schema_version": "governed_benchmark_results_v2",
        "model_id": "candidate-v1",
        "protocol_id": "protocol-v1",
        "protocol_hash": "a" * 64,
        "corpus_id": "corpus-v1",
        "corpus_hash": "b" * 64,
        "split_id": "split-v1",
        "assignment_hash": "c" * 64,
        "fold": "test",
        "metrics": {
            "precision": 1.0,
            "attack_level_recall": 1.0,
            "f1": 1.0,
            "false_alerts_per_million_events": 0.0,
            "detection_before_benefit_rate": 1.0,
            "duplicate_alert_load": 1.0,
        },
        "confidence_intervals": {},
        "regime_matrix": {},
        "worst_decile": {},
        "input_artifacts": [{"manifest_sha256": "d" * 64}],
    }


def _session() -> SessionMetricComponents:
    return SessionMetricComponents(
        base_session_id="session-1",
        instrument="SPY",
        regimes={"liquidity": "normal"},
        true_positive=1,
        false_positive=0,
        false_negative=0,
        true_negative=1,
        evaluable_event_count=100,
        raw_false_alert_count=0,
        false_alert_cluster_count=0,
        raw_evaluable_alert_count=1,
        evaluable_alert_cluster_count=1,
        benefit_eligible_attack_count=1,
        detected_before_benefit_count=1,
        detection_latencies_ns=(10,),
    )


def _validation() -> dict:
    return {
        "schema_version": "governed_benchmark_release_validation_v1",
        "verdict": "pass",
        "checks": {"all": True},
        "training_gate_passed": True,
    }


def test_signed_governed_release_binds_every_scientific_artifact(tmp_path: Path) -> None:
    key = tmp_path / "private.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(key)],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "release"

    manifest = write_governed_benchmark_release(
        output,
        results=_results(),
        session_metrics=[_session()],
        validation=_validation(),
        signing_key=key,
        signer="Independent QA",
    )

    assert manifest["signed"] is True
    assert (output / "manifest.sig").is_file()
    assert (output / "checksums.sha256").is_file()
    verify_governed_benchmark_release(output)
    signature = json.loads((output / "signature.json").read_text())
    assert signature["algorithm"] == "Ed25519"
    assert signature["signer"] == "Independent QA"


def test_signed_release_rejects_tampered_result(tmp_path: Path) -> None:
    key = tmp_path / "private.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(key)],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "release"
    write_governed_benchmark_release(
        output,
        results=_results(),
        session_metrics=[_session()],
        validation=_validation(),
        signing_key=key,
        signer="QA",
    )
    (output / "benchmark-results.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity validation"):
        verify_governed_benchmark_release(output)


def test_release_refuses_failing_scientific_validation(tmp_path: Path) -> None:
    validation = _validation()
    validation["verdict"] = "fail"

    with pytest.raises(ValueError, match="passing validation"):
        write_governed_benchmark_release(
            tmp_path,
            results=_results(),
            session_metrics=[_session()],
            validation=validation,
            signing_key=None,
            signer="QA",
        )
