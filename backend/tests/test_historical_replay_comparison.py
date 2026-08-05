import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.run_historical_replay_comparison import build_comparison, write_bundle
from scripts.run_historical_replay_comparison import verify_bundle_signature


def _raw_comparison() -> dict[str, object]:
    control = {
        "source_row_count": 12,
        "source_rows_replayed": 12,
        "events_sha256": "fixture-sha",
        "canonical_event_count": 15,
        "detector_alert_ticks": {},
        "ground_truth": None,
    }
    hybrid = {
        "source_row_count": 12,
        "source_rows_replayed": 12,
        "events_sha256": "fixture-sha",
        "canonical_event_count": 20,
        "detector_alert_ticks": {"spoofing_like_detector": [1]},
        "ground_truth": {"has_attack": True},
    }
    return {
        "dataset_id": "sample-btcusdt-0945",
        "events_sha256": "fixture-sha",
        "control": control,
        "hybrid": hybrid,
        "realism_impact": {
            "canonical_event_count_delta": 5,
            "final_depth_delta": 1.0,
            "final_spread_delta": 0.0,
        },
    }


def test_builds_metrics_without_treating_control_history_as_ground_truth() -> None:
    comparison = build_comparison(_raw_comparison())
    spoofing = next(row for row in comparison["detector_metrics"] if row["detector"] == "spoofing_like_detector")

    assert comparison["same_historical_window"] is True
    assert spoofing["true_positive"] == 1
    assert spoofing["false_positive"] == 0
    assert spoofing["false_negative"] == 0
    assert spoofing["true_negative"] == 1
    assert spoofing["precision"] == 1.0
    assert spoofing["recall"] == 1.0
    assert spoofing["f1"] == 1.0
    assert spoofing["hybrid_evaluation"]["detection_timing"] == "not_applicable"

    missed = next(row for row in comparison["detector_metrics"] if row["detector"] == "layering_like_detector")
    assert missed["true_positive"] == 0
    assert missed["false_positive"] == 0
    assert missed["false_negative"] == 1
    assert missed["true_negative"] == 1
    assert missed["precision"] is None
    assert missed["recall"] == 0.0
    assert missed["f1"] == 0.0


def test_writes_deterministic_manifest_and_checksums(tmp_path: Path) -> None:
    raw = _raw_comparison()
    raw["injection_schedule"] = {"schedule_sha256": "d" * 64}
    raw["control"]["source_integrity"] = {
        "format": "itch_parquet_v1",
        "source_stream_sha256": "a" * 64,
        "parser_config_sha256": "b" * 64,
    }
    raw["control"]["historical_source_sequences"] = 12
    write_bundle(raw, tmp_path)

    assert {path.name for path in tmp_path.iterdir()} == {
        "control.json",
        "hybrid.json",
        "comparison.json",
        "manifest.json",
        "checksums.sha256",
    }
    for line in (tmp_path / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == expected
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_integrity"]["format"] == "itch_parquet_v1"
    assert manifest["source_counts"]["historical_source_sequences"] == 12
    assert manifest["injection_schedule"]["schedule_sha256"] == "d" * 64


def test_ed25519_signs_and_verifies_commercial_validation_report(tmp_path: Path) -> None:
    private_key = tmp_path.parent / "validation-private-key.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "Ed25519",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )

    write_bundle(
        _raw_validation_comparison(),
        tmp_path,
        signing_key=private_key,
        signer="LOB Arena QA",
    )

    assert (tmp_path / "manifest.sig").is_file()
    assert not (tmp_path / "validation-report.sig").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["signed"] is True
    assert set(manifest["artifacts"]) == {
        "comparison.json",
        "control.json",
        "hybrid.json",
        "signature.json",
        "validation-public-key.pem",
        "validation-report.json",
    }
    signature = json.loads((tmp_path / "signature.json").read_text(encoding="utf-8"))
    assert signature["algorithm"] == "Ed25519"
    assert signature["signer"] == "LOB Arena QA"
    assert signature["key_id"].startswith("sha256:")
    assert signature["signed_artifact"] == "manifest.json"
    verify_bundle_signature(tmp_path)

    (tmp_path / "control.json").write_text('{"tampered":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="artifact .* mismatch"):
        verify_bundle_signature(tmp_path)


def _raw_validation_comparison() -> dict[str, object]:
    raw = _raw_comparison()
    sha_a = "a" * 64
    sha_b = "b" * 64
    base_trace = [
        {
            "tick": tick,
            "exchange_timestamp_ns": 34_200_000_000_000 + tick,
            "book_hash": sha_a,
            "spread": 1.0,
            "depth_top_n": 100.0,
            "imbalance": 0.0,
            "level_count": 2,
            "message_count": 2,
            "add_count": 1,
            "cancel_count": 1,
            "execute_count": 0,
        }
        for tick in range(3)
    ]
    hybrid_trace = [dict(row) for row in base_trace]
    hybrid_trace[1]["message_count"] = 4
    hybrid_trace[1]["add_count"] = 2
    hybrid_trace[1]["cancel_count"] = 2
    integrity = {
        "validated": True,
        "format": "lobster_parquet_v1",
        "row_count": 12,
        "paired_rows": 12,
        "output_sha256": {
            "events.parquet": sha_a,
            "book_snapshots.parquet": sha_b,
        },
    }
    order_id = "SYN:SCN-000001:seed:O:STUFF-1-0"
    ground_truth = {
        "scenario_id": "SCN-000001",
        "scenario_family": "quote_stuffing",
        "source": "synthetic_scenario",
        "has_attack": True,
        "start_tick": 1,
        "end_tick": 1,
        "order_ids": [order_id],
    }
    control = raw["control"]
    hybrid = raw["hybrid"]
    assert isinstance(control, dict)
    assert isinstance(hybrid, dict)
    control.update(
        {
            "historical_source_sequences": 12,
            "historical_snapshot_stream_hash": sha_b,
            "source_integrity": integrity,
            "validation_trace": base_trace,
            "synthetic_events": [],
        }
    )
    hybrid.update(
        {
            "historical_source_sequences": 12,
            "historical_snapshot_stream_hash": sha_b,
            "source_integrity": integrity,
            "validation_trace": hybrid_trace,
            "ground_truth": ground_truth,
            "synthetic_events": [
                {
                    "sequence": 1,
                    "tick": 1,
                    "scenario_id": "SCN-000001",
                    "event_type": "add",
                    "order_id": order_id,
                    "quantity": 10.0,
                },
                {
                    "sequence": 2,
                    "tick": 1,
                    "scenario_id": "SCN-000001",
                    "event_type": "cancel",
                    "order_id": order_id,
                    "quantity": 10.0,
                },
            ],
        }
    )
    raw.update(
        {
            "master_seed": 42,
            "determinism": {
                "control_stream_match": True,
                "hybrid_stream_match": True,
                "control_trace_match": True,
                "hybrid_trace_match": True,
                "historical_snapshot_match": True,
            },
        }
    )
    return raw
