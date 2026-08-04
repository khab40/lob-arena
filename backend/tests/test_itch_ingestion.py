import hashlib
import struct
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.data_ingestion.itch import (
    FORMAT_VERSION,
    PARSER_VERSION,
    ParsedRecord,
    _apply_book_message,
    _validate_book,
    convert_itch,
    discover_candidates,
    iter_records,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "nasdaq-itch" / "fixture"


def test_fixture_discovers_stock_directory_symbols() -> None:
    candidates = discover_candidates(FIXTURE_DIR, Path("/nonexistent/processed"))

    assert [(item.symbol, item.trade_date) for item in candidates] == [
        ("AAPL", "2026-01-02"),
        ("MSFT", "2026-01-02"),
    ]
    assert all(item.source_type == "nasdaq_itch" for item in candidates)
    assert all(item.venue == "XNAS" for item in candidates)


def test_fixture_normalizes_every_visible_lifecycle_transition(tmp_path: Path) -> None:
    candidate = next(
        item for item in discover_candidates(FIXTURE_DIR, tmp_path / "registry") if item.symbol == "AAPL"
    )

    manifest = convert_itch(
        candidate,
        FIXTURE_DIR,
        tmp_path / "registry",
        start_time_ms=34_200_000,
        end_time_ms=34_260_000,
        depth=2,
        min_free_bytes=0,
    )
    dataset = tmp_path / "registry" / manifest.dataset_id
    events = pq.read_table(dataset / "events.parquet")
    books = pq.read_table(dataset / "book_snapshots.parquet")

    assert manifest.source_type == "nasdaq_itch"
    assert manifest.format == FORMAT_VERSION
    assert manifest.venue == "XNAS"
    assert manifest.parser_version == PARSER_VERSION
    assert manifest.source_stream_sha256 == manifest.source_files[0].sha256
    assert manifest.parser_config_sha256
    assert manifest.row_count == events.num_rows == books.num_rows == 8
    assert manifest.event_counts == {
        "ADD": 2,
        "DELETE": 2,
        "PARTIAL_CANCEL": 1,
        "REPLACE": 1,
        "VISIBLE_EXECUTION": 2,
    }
    assert manifest.message_counts == {
        "A": 1,
        "C": 1,
        "D": 2,
        "E": 1,
        "F": 1,
        "H": 1,
        "R": 2,
        "S": 2,
        "U": 1,
        "X": 1,
    }
    assert events.column("source_sequence").to_pylist() == list(range(5, 13))
    assert events.column("raw_message_type").to_pylist() == list("AFECXUDD")
    assert events.column("trade_date").to_pylist() == ["2026-01-02"] * 8
    assert events.column("mpid").to_pylist()[1] == "ABCD"
    assert events.column("match_number").to_pylist()[2:4] == [101, 102]
    assert events.column("printable").to_pylist()[3] is True
    assert events.column("replacement_order_reference").to_pylist()[5] == 3
    assert books.column("bids").to_pylist()[0] == [
        {"level": 1, "price_x10000": 1_000_000, "quantity": 100}
    ]
    assert books.column("bids").to_pylist()[-2] == []
    assert books.column("asks").to_pylist()[-1] == []


def test_normalization_is_byte_deterministic_across_registries(tmp_path: Path) -> None:
    candidate = next(
        item for item in discover_candidates(FIXTURE_DIR, tmp_path / "unused") if item.symbol == "AAPL"
    )
    manifests = [
        convert_itch(
            candidate,
            FIXTURE_DIR,
            tmp_path / registry,
            start_time_ms=34_200_000,
            end_time_ms=34_260_000,
            min_free_bytes=0,
        )
        for registry in ("first", "second")
    ]

    assert manifests[0].dataset_id == manifests[1].dataset_id
    for filename in ("events.parquet", "book_snapshots.parquet", "manifest.json"):
        digests = []
        for registry, manifest in zip(("first", "second"), manifests, strict=True):
            payload = (tmp_path / registry / manifest.dataset_id / filename).read_bytes()
            digests.append(hashlib.sha256(payload).hexdigest())
        assert digests[0] == digests[1]


def test_selected_symbol_never_reads_other_symbol_orders(tmp_path: Path) -> None:
    candidate = next(
        item for item in discover_candidates(FIXTURE_DIR, tmp_path / "registry") if item.symbol == "MSFT"
    )

    try:
        convert_itch(
            candidate,
            FIXTURE_DIR,
            tmp_path / "registry",
            start_time_ms=34_200_000,
            end_time_ms=34_260_000,
            min_free_bytes=0,
        )
    except ValueError as exc:
        assert "contains no visible-order lifecycle events" in str(exc)
    else:  # pragma: no cover - the fixture intentionally has no MSFT lifecycle rows
        raise AssertionError("empty selected symbol should be rejected")


def test_lifecycle_validation_rejects_reuse_over_reduction_and_crossed_books() -> None:
    active = {}
    seen = set()
    book = {"BUY": {}, "SELL": {}}
    add_buy = _record(
        "A",
        1,
        struct.pack(">Q", 1) + b"B" + struct.pack(">I", 100) + b"AAPL    " + struct.pack(">I", 1_000_000),
    )
    _apply_book_message(add_buy, "AAPL", "2026-01-02", active, seen, book)

    with pytest.raises(ValueError, match="order reference is reused"):
        _apply_book_message(add_buy, "AAPL", "2026-01-02", active, seen, book)

    over_cancel = _record("X", 2, struct.pack(">QI", 1, 101))
    with pytest.raises(ValueError, match="invalid order reduction"):
        _apply_book_message(over_cancel, "AAPL", "2026-01-02", active, seen, book)

    replace_with_seen = _record("U", 3, struct.pack(">QQII", 1, 1, 50, 990_000))
    with pytest.raises(ValueError, match="replacement reference is reused"):
        _apply_book_message(replace_with_seen, "AAPL", "2026-01-02", active, seen, book)

    add_crossing_sell = _record(
        "A",
        4,
        struct.pack(">Q", 2) + b"S" + struct.pack(">I", 10) + b"AAPL    " + struct.pack(">I", 999_000),
    )
    _apply_book_message(add_crossing_sell, "AAPL", "2026-01-02", active, seen, book)
    with pytest.raises(ValueError, match="visible book is crossed"):
        _validate_book(book, 4)


def test_record_parser_rejects_timestamp_regression(tmp_path: Path) -> None:
    first = b"S" + struct.pack(">HH", 0, 1) + (2).to_bytes(6, "big") + b"O"
    second = b"S" + struct.pack(">HH", 0, 2) + (1).to_bytes(6, "big") + b"C"
    path = tmp_path / "2026-01-02.itch"
    path.write_bytes(struct.pack(">H", len(first)) + first + struct.pack(">H", len(second)) + second)

    with pytest.raises(ValueError, match="timestamp decreased"):
        list(iter_records(path))


def test_disk_reserve_fails_before_creating_a_temporary_dataset(tmp_path: Path) -> None:
    candidate = next(
        item for item in discover_candidates(FIXTURE_DIR, tmp_path / "registry") if item.symbol == "AAPL"
    )
    registry = tmp_path / "registry"

    with pytest.raises(ValueError, match="free disk"):
        convert_itch(candidate, FIXTURE_DIR, registry, min_free_bytes=2**63)

    assert list(registry.iterdir()) == []


def _record(message_type: str, sequence: int, body: bytes) -> ParsedRecord:
    expected_lengths = {"A": 36, "X": 23, "U": 35}
    payload = (
        message_type.encode("ascii")
        + struct.pack(">HH", 1, sequence)
        + (34_200_000_000_000 + sequence).to_bytes(6, "big")
        + body
    )
    assert len(payload) == expected_lengths[message_type]
    return ParsedRecord(sequence, message_type, 1, sequence, 34_200_000_000_000 + sequence, payload)
