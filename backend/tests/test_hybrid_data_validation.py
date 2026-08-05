import csv
from pathlib import Path

import pyarrow.parquet as pq

from app.data_ingestion.lobster import convert_pair, discover_candidates, validate_pair
from app.evaluation.hybrid_validation import build_hybrid_validation, validate_normalized_lobster


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def test_public_lobster_fixture_passes_synchronization_lifecycle_and_volume_checks(
    tmp_path: Path,
) -> None:
    raw = Path(__file__).resolve().parents[2] / "data" / "lobster" / "fixture"
    candidate = discover_candidates(raw, tmp_path / "processed")[0]

    report = validate_pair(candidate, raw)

    assert report.valid, report.errors
    assert report.row_count == 12
    assert all(report.checks.values())
    assert report.statistics["source_row_count"] == 12
    assert report.statistics["price_transition_checks"] >= 5
    assert report.statistics["tracked_lifecycle_events"] == 9


def test_normalized_pair_preserves_sequence_timestamp_hashes_and_provenance(
    tmp_path: Path,
) -> None:
    raw = Path(__file__).resolve().parents[2] / "data" / "lobster" / "fixture"
    processed = tmp_path / "processed"
    manifest = convert_pair(discover_candidates(raw, processed)[0], raw, processed)

    report = validate_normalized_lobster(processed / manifest.dataset_id)

    assert report["verdict"] == "pass"
    assert all(check["status"] == "pass" for check in report["checks"].values())
    events = pq.read_table(processed / manifest.dataset_id / "events.parquet")
    books = pq.read_table(processed / manifest.dataset_id / "book_snapshots.parquet")
    assert events.column("source_sequence").to_pylist() == books.column("source_sequence").to_pylist()
    assert (
        events.column("timestamp_ns_since_midnight").to_pylist()
        == books.column("timestamp_ns_since_midnight").to_pylist()
    )


def test_validator_rejects_crossed_book_bad_lifecycle_and_volume_nonconservation(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_rows(
        raw / "SPY_2012-06-21_34200000_34260000_message_1.csv",
        [
            ["34200.000000001", "1", "1", "100", "1000000", "1"],
            ["34200.000000002", "2", "1", "120", "1000000", "1"],
        ],
    )
    _write_rows(
        raw / "SPY_2012-06-21_34200000_34260000_orderbook_1.csv",
        [
            ["999000", "100", "1000000", "100"],
            ["999000", "100", "1000000", "90"],
        ],
    )

    report = validate_pair(discover_candidates(raw, tmp_path / "processed")[0], raw)

    assert not report.valid
    assert not report.checks["valid_uncrossed_books"]
    assert not report.checks["price_level_consistency"]
    assert not report.checks["order_lifecycle_consistency"]
    assert any("book is crossed" in error for error in report.errors)
    assert any("visible quantity delta" in error for error in report.errors)
    assert any("over-consumed" in error for error in report.errors)


def test_validator_rejects_timestamp_regression_and_session_boundary_violation(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_rows(
        raw / "SPY_2012-06-21_34200000_34260000_message_1.csv",
        [
            ["34200.000000002", "1", "1", "10", "1000000", "1"],
            ["34199.999999999", "1", "2", "10", "999000", "1"],
        ],
    )
    _write_rows(
        raw / "SPY_2012-06-21_34200000_34260000_orderbook_1.csv",
        [
            ["1001000", "10", "1000000", "10"],
            ["1001000", "10", "1000000", "10"],
        ],
    )

    report = validate_pair(discover_candidates(raw, tmp_path / "processed")[0], raw)

    assert not report.valid
    assert not report.checks["sequence_and_timestamp_integrity"]
    assert not report.checks["trading_session_boundaries"]


def test_hybrid_is_equivalent_outside_attack_causal_neighbourhood() -> None:
    raw = _hybrid_comparison()

    report = build_hybrid_validation(raw)

    assert report["verdict"] == "pass"
    locality = report["checks"]["outside_causal_neighbourhood_equivalence"]
    assert locality["status"] == "pass"
    assert locality["result"]["exact_book_match_rate"] == 1.0
    assert locality["result"]["statistically_equivalent"] is True
    assert report["causal_neighbourhood"]["phases"]["during"]["exact_book_match_rate"] == 0.0
    assert report["checks"]["injected_order_lifecycle"]["status"] == "pass"
    assert report["checks"]["attack_localisation"]["observed_event_ticks"] == [2, 3]


def test_hybrid_validation_detects_post_attack_corruption() -> None:
    raw = _hybrid_comparison()
    post_attack = next(row for row in raw["hybrid"]["validation_trace"] if row["tick"] == 5)
    post_attack["book_hash"] = SHA_D
    post_attack["depth_top_n"] = 800.0

    report = build_hybrid_validation(raw)

    assert report["verdict"] == "fail"
    assert report["checks"]["outside_causal_neighbourhood_equivalence"]["status"] == "fail"
    assert report["causal_neighbourhood"]["phases"]["after"]["exact_book_match_rate"] < 1.0


def test_quote_stuffing_impact_is_proven_by_event_flow_when_books_reconverge() -> None:
    raw = _hybrid_comparison()
    for tick in (2, 3):
        raw["hybrid"]["validation_trace"][tick] = {
            **raw["control"]["validation_trace"][tick],
            "message_count": 14,
            "add_count": 7,
            "cancel_count": 7,
        }

    report = build_hybrid_validation(raw)

    impact = report["checks"]["intended_market_impact"]
    assert report["verdict"] == "pass"
    assert impact["status"] == "pass"
    assert impact["book_divergence"] is False
    assert impact["event_flow_divergence"] is True
    assert impact["result"]["exact_book_match_rate"] == 1.0


def test_attack_execution_semantics_conserve_injected_order_volume() -> None:
    raw = _hybrid_comparison()
    order_id = raw["hybrid"]["ground_truth"]["order_ids"][0]
    raw["hybrid"]["synthetic_events"][1] = {
        "sequence": 20,
        "tick": 3,
        "source": "simulation",
        "scenario_id": "SCN-000001",
        "event_type": "execute",
        "aggressor_order_id": "HIST:fixture:O:100",
        "resting_order_id": order_id,
        "quantity": 300.0,
        "aggressor_remaining_quantity": 0.0,
        "resting_remaining_quantity": 0.0,
    }

    report = build_hybrid_validation(raw)
    lifecycle = report["checks"]["injected_order_lifecycle"]

    assert lifecycle["status"] == "pass"
    assert lifecycle["execution_quantity_by_order"] == {order_id: 300.0}
    assert lifecycle["terminal_state_by_order"] == {order_id: "executed"}


def test_attack_lifecycle_rejects_duplicate_cancellation() -> None:
    raw = _hybrid_comparison()
    raw["hybrid"]["synthetic_events"].append(
        {
            **raw["hybrid"]["synthetic_events"][1],
            "sequence": 21,
        }
    )

    report = build_hybrid_validation(raw)

    assert report["verdict"] == "fail"
    assert report["checks"]["injected_order_lifecycle"]["status"] == "fail"
    assert any("duplicate cancel" in error for error in report["checks"]["injected_order_lifecycle"]["errors"])


def test_scheduled_itch_injection_binds_trigger_parameters_and_source_provenance() -> None:
    raw = _hybrid_comparison()
    schedule = {
        "schema_version": "historical_injection_schedule_v1",
        "scenario_family": "spoofing_like_wall",
        "schedule_sha256": SHA_D,
        "triggered": True,
        "requested_source_sequence": 3,
        "requested_timestamp_ns": None,
        "actual_source_sequence": 3,
        "actual_timestamp_ns": 34_200_000_000_002,
        "parameters": {"quantity_lots": 30_000, "duration_ticks": 3, "distance_levels": 2},
    }
    raw["scheduled_injection"] = True
    raw["injection_schedule"] = schedule
    raw["control"]["injection_schedule"] = schedule
    raw["hybrid"]["injection_schedule"] = schedule
    raw["hybrid"]["ground_truth"].update(
        {
            "trigger_source_sequence": 3,
            "trigger_timestamp_ns": 34_200_000_000_002,
            "start_exchange_timestamp_ns": 34_200_000_000_002,
            "end_exchange_timestamp_ns": 34_200_000_000_003,
            "schedule_sha256": SHA_D,
            "parameters": schedule["parameters"],
        }
    )
    itch_provenance = {
        "source_type": "nasdaq_itch",
        "venue": "XNAS",
        "parser_version": "nasdaq_itch_5_0_v1",
        "source_stream_sha256": SHA_A,
        "parser_config_sha256": SHA_B,
        "filters": {"symbol": "AAPL", "depth": 10},
        "message_counts": {"A": 1, "D": 1},
        "truncation_limits": {"max_working_bytes": 12 * 1024**3},
    }
    for run in (raw["control"], raw["hybrid"]):
        run["source_integrity"] = {
            **run["source_integrity"],
            **itch_provenance,
            "format": "itch_parquet_v1",
        }

    report = build_hybrid_validation(raw)

    assert report["verdict"] == "pass"
    assert report["checks"]["deterministic_injection_schedule"]["status"] == "pass"
    assert report["checks"]["historical_source_immutability"]["status"] == "pass"


def _hybrid_comparison() -> dict:
    control_trace = [_trace(tick, SHA_A, 10.0, 500.0, 0.0, 4) for tick in range(7)]
    hybrid_trace = [dict(row) for row in control_trace]
    for tick in (2, 3):
        hybrid_trace[tick] = _trace(tick, SHA_B, 10.0, 800.0, -0.25, 5)
    ground_truth = {
        "schema_version": "scenario_ground_truth_v1",
        "scenario_id": "SCN-000001",
        "scenario_family": "spoofing_like_wall",
        "source": "synthetic_scenario",
        "has_attack": True,
        "start_tick": 2,
        "end_tick": 3,
        "order_ids": ["SYN:SCN-000001:seed:O:WALL"],
    }
    synthetic_events = [
        {
            "sequence": 10,
            "tick": 2,
            "source": "simulation",
            "scenario_id": "SCN-000001",
            "event_type": "add",
            "order_id": ground_truth["order_ids"][0],
            "quantity": 300.0,
        },
        {
            "sequence": 20,
            "tick": 3,
            "source": "simulation",
            "scenario_id": "SCN-000001",
            "event_type": "cancel",
            "order_id": ground_truth["order_ids"][0],
            "quantity": 300.0,
        },
    ]
    control = {
        "source_row_count": 6,
        "source_rows_replayed": 6,
        "historical_source_sequences": 6,
        "events_sha256": SHA_A,
        "stream_hash": SHA_B,
        "historical_snapshot_stream_hash": SHA_C,
        "source_integrity": {
            "validated": True,
            "format": "lobster_parquet_v1",
            "row_count": 6,
            "paired_rows": 6,
            "output_sha256": {
                "events.parquet": SHA_A,
                "book_snapshots.parquet": SHA_B,
            },
        },
        "validation_trace": control_trace,
        "synthetic_events": [],
        "ground_truth": None,
    }
    hybrid = {
        "source_row_count": 6,
        "source_rows_replayed": 6,
        "historical_source_sequences": 6,
        "events_sha256": SHA_A,
        "stream_hash": SHA_D,
        "historical_snapshot_stream_hash": SHA_C,
        "source_integrity": {
            "validated": True,
            "format": "lobster_parquet_v1",
            "row_count": 6,
            "paired_rows": 6,
            "output_sha256": {
                "events.parquet": SHA_A,
                "book_snapshots.parquet": SHA_B,
            },
        },
        "validation_trace": hybrid_trace,
        "synthetic_events": synthetic_events,
        "ground_truth": ground_truth,
    }
    return {
        "dataset_id": "lobster-spy-fixture",
        "master_seed": 42,
        "events_sha256": SHA_A,
        "determinism": {
            "control_stream_match": True,
            "hybrid_stream_match": True,
            "control_trace_match": True,
            "hybrid_trace_match": True,
            "historical_snapshot_match": True,
            "control_repeat_stream_hash": SHA_B,
            "hybrid_repeat_stream_hash": SHA_D,
        },
        "control": control,
        "hybrid": hybrid,
    }


def _trace(
    tick: int,
    book_hash: str,
    spread: float,
    depth: float,
    imbalance: float,
    levels: int,
) -> dict:
    return {
        "tick": tick,
        "exchange_timestamp_ns": 34_200_000_000_000 + tick,
        "book_hash": book_hash,
        "spread": spread,
        "depth_top_n": depth,
        "imbalance": imbalance,
        "level_count": levels,
        "message_count": 2,
        "add_count": 1,
        "cancel_count": 1,
        "execute_count": 0,
    }


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
