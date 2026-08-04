import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.calibration.market_profile import (
    CORE_METRICS,
    PROFILE_SCHEMA_VERSION,
    build_realism_report,
    extract_market_profile,
    write_json_artifact,
)
from app.data_ingestion.itch import convert_itch, discover_candidates

ITCH_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "nasdaq-itch" / "fixture"
COMMITTED_FIXTURE_PROFILE = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "market-profiles"
    / "fixture-aapl-itch-v1.json"
)


def test_fixture_profile_is_deterministic_versioned_and_source_bound(tmp_path: Path) -> None:
    candidate = next(
        item for item in discover_candidates(ITCH_FIXTURE, tmp_path / "registry") if item.symbol == "AAPL"
    )
    manifest = convert_itch(
        candidate,
        ITCH_FIXTURE,
        tmp_path / "registry",
        start_time_ms=34_200_000,
        end_time_ms=34_260_000,
        depth=2,
        min_free_bytes=0,
    )
    dataset = tmp_path / "registry" / manifest.dataset_id

    first = extract_market_profile(dataset, profile_id="fixture-aapl-itch-v1")
    second = extract_market_profile(dataset, profile_id="fixture-aapl-itch-v1")

    assert first == second
    assert first == json.loads(COMMITTED_FIXTURE_PROFILE.read_text(encoding="utf-8"))
    assert first["schema_version"] == PROFILE_SCHEMA_VERSION
    assert len(first["profile_sha256"]) == 64
    assert first["source"]["source_stream_sha256"] == manifest.source_stream_sha256
    assert first["source"]["parser_config_sha256"] == manifest.parser_config_sha256
    assert {
        "arrival_intensity_events_per_second",
        "inter_event_time_ns",
        "order_size",
        "distance_from_touch_x10000",
        "order_lifetime_ns",
        "cancellation_ratio",
        "execution_ratio",
        "spread_x10000",
        "top_depth",
        "imbalance",
        "mid_volatility_bps",
        "refill_time_ns",
        "resilience_time_ns",
    } <= first["distributions"].keys()
    assert first["simulation_parameters"]["reference_price_ticks"] > 0
    assert first["simulation_parameters"]["level_spacing_ticks"] > 0


def test_held_out_report_is_checksummed_and_calibration_improves_median_distance(
    tmp_path: Path,
) -> None:
    training = _dataset(tmp_path / "training", "training-window", price_offset=0)
    held_out = _dataset(tmp_path / "held-out", "held-out-window", price_offset=200)
    profile = extract_market_profile(training, profile_id="stable-stock-v1")

    first = build_realism_report(profile, held_out)
    second = build_realism_report(profile, held_out)

    assert first == second
    assert first["preregistered_core_metrics"] == list(CORE_METRICS)
    assert first["completion_gate_passed"] is True
    assert (
        first["median_realism_distance"]["calibrated"]
        < first["median_realism_distance"]["hardcoded"]
    )
    assert first["attack_response"]["depth_top_n"]["during"] < first["attack_response"]["depth_top_n"]["before"]
    assert len(first["report_sha256"]) == 64

    output = tmp_path / "profiles" / "stable-stock-v1.json"
    write_json_artifact(profile, output)
    first_bytes = output.read_bytes()
    write_json_artifact(profile, output)
    assert output.read_bytes() == first_bytes


def test_report_rejects_training_window_reused_as_holdout(tmp_path: Path) -> None:
    training = _dataset(tmp_path / "training", "same-window", price_offset=0)
    profile = extract_market_profile(training)

    with pytest.raises(ValueError, match="must be distinct"):
        build_realism_report(profile, training)


def _dataset(root: Path, dataset_id: str, *, price_offset: int) -> Path:
    root.mkdir(parents=True)
    event_rows = []
    book_rows = []
    for index in range(20):
        timestamp = 34_200_000_000_000 + index * 100_000_000
        bid = 1_000_000 + price_offset + index * 10
        ask = bid + 100
        event_rows.append(
            {
                "source_sequence": index + 1,
                "timestamp_ns_since_midnight": timestamp,
                "event_kind": "ADD",
                "source_event_code": 65,
                "source_order_id": index + 1,
                "size": 100,
                "price_x10000": bid,
                "direction": 1,
                "book_side": "BUY",
                "symbol": "TEST",
                "trade_date": "2026-01-02",
                "raw_message_type": "A",
            }
        )
        book_rows.append(
            {
                "source_sequence": index + 1,
                "timestamp_ns_since_midnight": timestamp,
                "depth": 2,
                "bids": [
                    {"level": 1, "price_x10000": bid, "quantity": 500},
                    {"level": 2, "price_x10000": bid - 100, "quantity": 500},
                ],
                "asks": [
                    {"level": 1, "price_x10000": ask, "quantity": 500},
                    {"level": 2, "price_x10000": ask + 100, "quantity": 500},
                ],
            }
        )
    events_path = root / "events.parquet"
    books_path = root / "book_snapshots.parquet"
    pq.write_table(pa.Table.from_pylist(event_rows), events_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(book_rows), books_path, compression="zstd")
    manifest = {
        "dataset_id": dataset_id,
        "source_type": "nasdaq_itch",
        "format": "itch_parquet_v1",
        "venue": "XNAS",
        "symbol": "TEST",
        "trade_date": "2026-01-02",
        "start_time_ms": 34_200_000,
        "end_time_ms": 34_260_000,
        "depth": 2,
        "row_count": len(event_rows),
        "source_stream_sha256": hashlib.sha256(dataset_id.encode()).hexdigest(),
        "parser_config_sha256": hashlib.sha256(f"config:{dataset_id}".encode()).hexdigest(),
        "output_files": [
            {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (events_path, books_path)
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root
