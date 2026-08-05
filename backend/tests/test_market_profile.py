import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.calibration.market_profile import (
    CORE_METRICS,
    PROFILE_SCHEMA_VERSION,
    _pre_add_touch,
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
    simulation_runs = _simulation_runs(profile)

    first = build_realism_report(profile, held_out, simulation_runs=simulation_runs)
    second = build_realism_report(profile, held_out, simulation_runs=simulation_runs)

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
        build_realism_report(profile, training, simulation_runs={})


def test_report_rejects_non_deterministic_java_trace(tmp_path: Path) -> None:
    training = _dataset(tmp_path / "training", "training-window", price_offset=0)
    held_out = _dataset(tmp_path / "held-out", "held-out-window", price_offset=200)
    profile = extract_market_profile(training)
    simulation_runs = _simulation_runs(profile)
    simulation_runs["calibrated"]["repeat_trace_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="not repeat deterministic"):
        build_realism_report(profile, held_out, simulation_runs=simulation_runs)


def test_distance_from_touch_uses_book_before_price_improving_add() -> None:
    event = {"price_x10000": 1_000_010, "size": 100}
    post_event_levels = [
        {"price_x10000": 1_000_010, "quantity": 100},
        {"price_x10000": 1_000_000, "quantity": 500},
    ]

    assert _pre_add_touch(event, post_event_levels) == 1_000_000


def _simulation_runs(profile: dict[str, object]) -> dict[str, object]:
    calibrated = [_simulation_state(index, profile_sha256=str(profile["profile_sha256"])) for index in range(1, 21)]
    hardcoded = [_simulation_state(index, hardcoded=True) for index in range(1, 21)]
    calibrated_attack = [
        _simulation_state(
            index + 1,
            profile_sha256=str(profile["profile_sha256"]),
            attack_phase="before" if index < 20 else "during" if index < 30 else "after",
        )
        for index in range(40)
    ]
    hardcoded_attack = [_simulation_state(index + 1, hardcoded=True) for index in range(40)]

    def run(source_type: str, states: list[dict[str, object]], attack: list[dict[str, object]]) -> dict[str, object]:
        trace_sha = _json_sha(states)
        attack_sha = _json_sha(attack)
        return {
            "source_type": source_type,
            "dataset_id": profile["profile_id"] if source_type == "synthetic_profile" else "",
            "states": states,
            "trace_sha256": trace_sha,
            "repeat_trace_sha256": trace_sha,
            "attack_states": attack,
            "attack_trace_sha256": attack_sha,
            "repeat_attack_trace_sha256": attack_sha,
            "attack_windows": {"before": [0, 19], "during": [20, 29], "after": [30, 39]},
        }

    calibrated_run = run("synthetic_profile", calibrated, calibrated_attack)
    calibrated_run["profile_sha256"] = profile["profile_sha256"]
    return {
        "schema_version": "market_profile_simulation_runs_v1",
        "producer": "java_control_plane",
        "master_seed": 42,
        "calibrated": calibrated_run,
        "hardcoded": run("synthetic", hardcoded, hardcoded_attack),
    }


def _simulation_state(
    tick: int,
    *,
    profile_sha256: str | None = None,
    hardcoded: bool = False,
    attack_phase: str | None = None,
) -> dict[str, object]:
    bid = 68_124.0 if hardcoded else 100.0 + tick * 0.001
    spread = 2.0 if hardcoded else 0.01
    quantity = 10.0 if hardcoded else 500.0
    if attack_phase == "during":
        spread = 0.02
        quantity = 125.0
    elif attack_phase == "after":
        quantity = 450.0
    state: dict[str, object] = {
        "tick": tick,
        "book": {
            "bids": [
                {"price": bid, "quantity": quantity},
                {"price": bid - 0.01, "quantity": quantity},
            ],
            "asks": [
                {"price": bid + spread, "quantity": quantity},
                {"price": bid + spread + 0.01, "quantity": quantity},
            ],
        },
        "exchange_events": [
            {
                "tick": tick,
                "event_type": "add",
                "quantity": 1.5 if hardcoded else 100.0,
            }
        ],
    }
    if profile_sha256 is not None:
        state["market_data"] = {
            "source_type": "synthetic_profile",
            "profile_sha256": profile_sha256,
        }
    return state


def _json_sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


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
