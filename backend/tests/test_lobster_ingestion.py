import csv
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.data_ingestion.lobster import convert_pair, discover_candidates, parse_message, validate_pair
from app.data_ingestion.service import DataIngestionService


def test_parser_preserves_price_and_maps_all_lobster_event_codes() -> None:
    expected = {
        1: "ADD",
        2: "PARTIAL_CANCEL",
        3: "DELETE",
        4: "VISIBLE_EXECUTION",
        5: "HIDDEN_EXECUTION",
        6: "CROSS_TRADE",
    }
    for code, kind in expected.items():
        event = parse_message(["34200.123456789", str(code), "42", "100", "911400", "1"], line_number=1)
        assert event.event_kind == kind
        assert event.price_x10000 == 911_400
        assert event.timestamp_ns_since_midnight == 34_200_123_456_789

    halt = parse_message(["34201", "7", "0", "0", "-1", "-1"], line_number=2)
    assert halt.event_kind == "TRADING_HALT"
    assert halt.halt_state == "HALTED"
    assert halt.price_x10000 == -1


def test_parser_rounds_lobster_subnanosecond_serialization_noise() -> None:
    rounded_down = parse_message(
        ["34903.864346888004", "1", "30731964", "500", "1354300", "1"],
        line_number=245_114,
    )
    rounded_up = parse_message(
        ["35053.714665770996", "1", "33493678", "800", "1353500", "1"],
        line_number=286_886,
    )

    assert rounded_down.timestamp_ns_since_midnight == 34_903_864_346_888
    assert rounded_up.timestamp_ns_since_midnight == 35_053_714_665_771


def test_parser_rejects_material_subnanosecond_precision() -> None:
    with pytest.raises(ValueError, match="timestamp precision exceeds nanoseconds"):
        parse_message(["34200.1234567891", "1", "42", "100", "911400", "1"], line_number=1)


def test_discovery_validation_and_parquet_conversion_are_aligned(tmp_path: Path) -> None:
    raw = tmp_path / "lobster"
    processed = tmp_path / "processed"
    source_dir = raw / "raw" / "aapl_2012-06-21_2"
    source_dir.mkdir(parents=True)
    message = source_dir / "AAPL_2012-06-21_34200000_57600000_message_2.csv"
    orderbook = source_dir / "AAPL_2012-06-21_34200000_57600000_orderbook_2.csv"
    _write_rows(
        message,
        [
            ["34200.000000001", "1", "1001", "100", "911400", "1"],
            ["34200.000000002", "2", "1001", "25", "911400", "1"],
            ["34200.000000003", "4", "1001", "75", "911400", "1"],
            ["34200.000000004", "5", "0", "10", "911500", "-1"],
            ["34200.000000005", "6", "0", "20", "911450", "1"],
            ["34200.000000006", "7", "0", "0", "-1", "-1"],
        ],
    )
    _write_rows(
        orderbook,
        [
            ["911500", "200", "911400", "100", "911600", "300", "911300", "400"],
            ["911500", "200", "911400", "75", "911600", "300", "911300", "400"],
            ["911500", "200", "911300", "400", "911600", "300", "-9999999999", "0"],
            ["911500", "200", "911300", "400", "911600", "300", "-9999999999", "0"],
            ["911500", "200", "911300", "400", "911600", "300", "-9999999999", "0"],
            ["911500", "200", "911300", "400", "911600", "300", "-9999999999", "0"],
        ],
    )

    candidates = discover_candidates(raw, processed)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "ready"
    assert candidate.symbol == "AAPL"
    assert candidate.depth == 2
    assert candidate.message_file == "raw/aapl_2012-06-21_2/AAPL_2012-06-21_34200000_57600000_message_2.csv"
    report = validate_pair(candidate, raw)
    assert report.valid
    assert report.row_count == 6

    manifest = convert_pair(candidate, raw, processed)
    dataset_dir = processed / manifest.dataset_id
    events = pq.read_table(dataset_dir / "events.parquet")
    books = pq.read_table(dataset_dir / "book_snapshots.parquet")

    assert events.num_rows == books.num_rows == manifest.row_count == 6
    assert events.column("price_x10000").to_pylist()[:2] == [911_400, 911_400]
    assert events.schema.field("price_x10000").type.bit_width == 64
    assert books.column("asks").to_pylist()[0][0] == {
        "level": 1,
        "price_x10000": 911_500,
        "quantity": 200,
    }
    payload = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    assert payload["price_scale"] == 10_000
    assert {item["name"] for item in payload["output_files"]} == {
        "events.parquet",
        "book_snapshots.parquet",
    }
    assert payload["source_files"][0]["name"].startswith("raw/aapl_2012-06-21_2/")

    second = convert_pair(candidate, raw, processed)
    assert second.dataset_id == manifest.dataset_id
    imported_candidate = discover_candidates(raw, processed)[0]
    assert imported_candidate.status == "imported"
    assert imported_candidate.dataset_id == manifest.dataset_id


def test_validator_rejects_row_mismatch_and_wrong_depth(tmp_path: Path) -> None:
    raw = tmp_path / "lobster"
    raw.mkdir()
    _write_rows(
        raw / "MSFT_2012-06-21_34200000_57600000_message_2.csv",
        [["34200", "1", "1", "100", "100000", "1"], ["34201", "3", "1", "100", "100000", "1"]],
    )
    _write_rows(
        raw / "MSFT_2012-06-21_34200000_57600000_orderbook_2.csv",
        [["100100", "10", "100000", "10"]],
    )
    candidate = discover_candidates(raw, tmp_path / "processed")[0]

    report = validate_pair(candidate, raw)

    assert not report.valid
    assert any("expected 8 columns" in error for error in report.errors)
    assert "message and orderbook row counts differ" in report.errors


def test_conversion_can_register_a_selected_one_minute_window(tmp_path: Path) -> None:
    raw = tmp_path / "lobster"
    processed = tmp_path / "processed"
    raw.mkdir()
    _write_rows(
        raw / "SPY_2012-06-21_34200000_37800000_message_1.csv",
        [
            ["34200.000000000004", "1", "1", "100", "100000", "1"],
            ["34260", "2", "1", "10", "100000", "1"],
            ["34320", "3", "1", "90", "100000", "1"],
        ],
    )
    _write_rows(
        raw / "SPY_2012-06-21_34200000_37800000_orderbook_1.csv",
        [
            ["100100", "10", "100000", "100"],
            ["100100", "10", "100000", "90"],
            ["100100", "10", "99900", "50"],
        ],
    )
    candidate = discover_candidates(raw, processed)[0]

    manifest = convert_pair(
        candidate,
        raw,
        processed,
        start_time_ms=34_260_000,
        end_time_ms=34_320_000,
    )
    events = pq.read_table(processed / manifest.dataset_id / "events.parquet")

    assert manifest.start_time_ms == 34_260_000
    assert manifest.end_time_ms == 34_320_000
    assert manifest.row_count == 1
    assert events.column("source_sequence").to_pylist() == [2]
    assert events.column("event_kind").to_pylist() == ["PARTIAL_CANCEL"]


def test_committed_lobster_fixture_converts_without_losing_messages(tmp_path: Path) -> None:
    raw = Path(__file__).resolve().parents[2] / "data" / "lobster" / "fixture"
    candidates = discover_candidates(raw, tmp_path)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.symbol == "SPY"
    assert candidate.depth == 2
    manifest = convert_pair(candidate, raw, tmp_path)
    events = pq.read_table(tmp_path / manifest.dataset_id / "events.parquet")
    books = pq.read_table(tmp_path / manifest.dataset_id / "book_snapshots.parquet")

    assert manifest.row_count == 12
    assert events.num_rows == books.num_rows == 12
    assert events.column("source_sequence").to_pylist() == list(range(1, 13))
    assert events.column("timestamp_ns_since_midnight").to_pylist() == sorted(
        events.column("timestamp_ns_since_midnight").to_pylist()
    )


def test_background_import_status_is_visible_and_failure_can_be_retried(tmp_path: Path) -> None:
    raw = tmp_path / "lobster"
    raw.mkdir()
    message = raw / "SPY_2012-06-21_34200000_37800000_message_1.csv"
    orderbook = raw / "SPY_2012-06-21_34200000_37800000_orderbook_1.csv"
    message.touch()
    orderbook.touch()
    service = DataIngestionService(raw, tmp_path / "processed")
    candidate = service.candidates()[0]

    def fail_import(_candidate, **_kwargs) -> None:
        raise ValueError("bad source")

    service.lobster.import_candidate = fail_import  # type: ignore[method-assign]

    accepted, started = service.begin_import(candidate.candidate_id)

    assert accepted.status == "importing"
    assert started
    assert service.candidates()[0].status == "importing"
    service.execute_import(candidate.candidate_id)
    failed = service.candidates()[0]
    assert failed.status == "failed"
    assert failed.errors == ["bad source"]
    _, retried = service.begin_import(candidate.candidate_id)
    assert retried


def test_imported_dataset_can_be_deleted(tmp_path: Path) -> None:
    raw = Path(__file__).resolve().parents[2] / "data" / "lobster" / "fixture"
    processed = tmp_path / "processed"
    service = DataIngestionService(raw, processed)
    candidate = service.candidates()[0]
    manifest = service.import_candidate(candidate.candidate_id)

    service.delete_dataset(manifest.dataset_id)

    assert service.dataset(manifest.dataset_id) is None
    assert not (processed / manifest.dataset_id).exists()
    with pytest.raises(LookupError):
        service.delete_dataset(manifest.dataset_id)


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
