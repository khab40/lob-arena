from __future__ import annotations

import gzip
import hashlib
import json
import os
import resource
import shutil
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator
from uuid import uuid4

from app.data_ingestion.lobster import candidate_identifier, safe_child
from app.data_ingestion.models import DatasetFile, DatasetManifest, IngestionCandidate, format_milliseconds

PARSER_VERSION = "nasdaq_itch_5_0_v1"
FORMAT_VERSION = "itch_parquet_v1"
VENUE = "XNAS"
DEFAULT_DEPTH = 10
DEFAULT_MIN_FREE_BYTES = 20 * 1024**3
DEFAULT_MAX_WORKING_BYTES = 12 * 1024**3
CHUNK_ROWS = 50_000
RESOURCE_CHECK_RECORDS = 50_000
MESSAGE_LENGTHS = {
    "S": 12,
    "R": 39,
    "A": 36,
    "F": 40,
    "E": 31,
    "C": 36,
    "X": 23,
    "D": 19,
    "U": 35,
}
BOOK_MESSAGE_TYPES = frozenset("AFECXDU")
DATE_PATTERNS = (
    (r"(?<!\d)(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)", (1, 2, 3)),
    (r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)", (3, 1, 2)),
)


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str
    shares: int
    price_x10000: int
    mpid: str | None


@dataclass(frozen=True)
class ParsedRecord:
    source_sequence: int
    message_type: str
    stock_locate: int
    tracking_number: int
    timestamp_ns: int
    payload: bytes


@dataclass(frozen=True)
class NormalizationResult:
    row_count: int
    event_counts: dict[str, int]
    message_counts: dict[str, int]
    first_timestamp_ns: int
    last_timestamp_ns: int


def discover_candidates(raw_dir: Path, processed_dir: Path) -> list[IngestionCandidate]:
    raw_root = raw_dir.resolve()
    if not raw_root.exists():
        return []
    imported = list(_iter_itch_manifests(processed_dir))
    candidates: list[IngestionCandidate] = []
    for path in sorted(item for item in raw_root.rglob("*") if _is_itch_file(item)):
        relative = path.relative_to(raw_root).as_posix()
        trade_date = _trade_date_from_name(path.name)
        try:
            symbols = discover_symbols(path)
        except (OSError, ValueError) as exc:
            symbols = []
            discovery_error = str(exc)
        else:
            discovery_error = ""
        if not symbols:
            symbols = [""]
        for symbol in symbols:
            key = ("nasdaq_itch", relative, symbol, trade_date or "")
            candidate_id = candidate_identifier(key)
            errors = []
            if trade_date is None:
                errors.append("ITCH filename must contain YYYYMMDD, YYYY-MM-DD, or MMDDYYYY trade date")
            if not symbol:
                errors.append(discovery_error or "ITCH stream contains no Stock Directory messages")
            matching = next(
                (
                    manifest.dataset_id
                    for manifest in imported
                    if manifest.symbol == symbol
                    and manifest.trade_date == trade_date
                    and manifest.source_files
                    and manifest.source_files[0].name == relative
                    and manifest.source_files[0].size_bytes == path.stat().st_size
                    and manifest.start_time_ms == 0
                    and manifest.end_time_ms == 86_400_000
                    and manifest.depth == DEFAULT_DEPTH
                ),
                None,
            )
            candidates.append(
                IngestionCandidate(
                    candidate_id=candidate_id,
                    source_type="nasdaq_itch",
                    venue=VENUE,
                    symbol=symbol or "UNKNOWN",
                    trade_date=trade_date or "",
                    start_time_ms=0,
                    end_time_ms=86_400_000,
                    start_time=format_milliseconds(0),
                    end_time=format_milliseconds(86_400_000),
                    depth=DEFAULT_DEPTH,
                    source_file=relative,
                    source_file_size=path.stat().st_size,
                    status="invalid" if errors else "imported" if matching else "ready",
                    errors=errors,
                    dataset_id=matching,
                )
            )
    return candidates


def discover_symbols(path: Path) -> list[str]:
    symbols: dict[int, str] = {}
    for record in iter_records(path):
        if record.message_type == "R":
            symbol = _alpha(record.payload[11:19])
            if not symbol:
                raise ValueError(f"ITCH message {record.source_sequence}: empty Stock Directory symbol")
            previous = symbols.setdefault(record.stock_locate, symbol)
            if previous != symbol:
                raise ValueError(f"ITCH stock locate {record.stock_locate} maps to multiple symbols")
        elif record.message_type in BOOK_MESSAGE_TYPES:
            break
    return sorted(set(symbols.values()))


def convert_itch(
    candidate: IngestionCandidate,
    raw_dir: Path,
    destination: Path,
    *,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
    depth: int | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
    max_working_bytes: int = DEFAULT_MAX_WORKING_BYTES,
) -> DatasetManifest:
    import pyarrow.parquet as pq

    if candidate.source_type != "nasdaq_itch" or not candidate.source_file:
        raise ValueError("candidate is not a Nasdaq ITCH source")
    effective_start = candidate.start_time_ms if start_time_ms is None else start_time_ms
    effective_end = candidate.end_time_ms if end_time_ms is None else end_time_ms
    effective_depth = candidate.depth if depth is None else depth
    if not 0 <= effective_start < effective_end <= 86_400_000:
        raise ValueError("selected ITCH window must be within one trading day")
    if not 1 <= effective_depth <= 100:
        raise ValueError("ITCH depth must be between 1 and 100")
    source_path = safe_child(raw_dir, candidate.source_file)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    _check_disk_quota(destination, min_free_bytes=min_free_bytes)
    _check_source_quota(source_path, max_working_bytes=max_working_bytes)
    source_file = _file_metadata(source_path, candidate.source_file)
    config = {
        "depth": effective_depth,
        "end_time_ms": effective_end,
        "format": FORMAT_VERSION,
        "max_working_bytes": max_working_bytes,
        "min_free_bytes": min_free_bytes,
        "parser_version": PARSER_VERSION,
        "start_time_ms": effective_start,
        "symbol": candidate.symbol,
    }
    config_sha256 = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity = hashlib.sha256(f"{source_file.sha256}:{config_sha256}".encode()).hexdigest()[:12]
    dataset_id = (
        f"itch-{candidate.symbol.lower()}-{candidate.trade_date}-{effective_start}-"
        f"{effective_end}-d{effective_depth}-{identity}"
    )
    final_dir = destination / dataset_id
    if (final_dir / "manifest.json").is_file():
        return DatasetManifest.model_validate_json((final_dir / "manifest.json").read_text(encoding="utf-8"))
    temporary = destination / f".{dataset_id}.tmp-{uuid4().hex}"
    temporary.mkdir()
    try:
        result = _normalize(
            source_path,
            temporary,
            symbol=candidate.symbol,
            trade_date=candidate.trade_date,
            start_ns=effective_start * 1_000_000,
            end_ns=effective_end * 1_000_000,
            depth=effective_depth,
            min_free_bytes=min_free_bytes,
            max_working_bytes=max_working_bytes,
        )
        _check_working_set(
            temporary,
            source_path=source_path,
            min_free_bytes=min_free_bytes,
            max_working_bytes=max_working_bytes,
        )
        events_path = temporary / "events.parquet"
        books_path = temporary / "book_snapshots.parquet"
        pq.read_metadata(events_path)
        pq.read_metadata(books_path)
        output_files = [_file_metadata(events_path), _file_metadata(books_path)]
        manifest = DatasetManifest(
            dataset_schema_version=1,
            dataset_id=dataset_id,
            source_type="nasdaq_itch",
            format=FORMAT_VERSION,
            venue=VENUE,
            parser_version=PARSER_VERSION,
            ingestion_mode="streaming",
            symbol=candidate.symbol,
            trade_date=candidate.trade_date,
            start_time_ms=effective_start,
            end_time_ms=effective_end,
            depth=effective_depth,
            row_count=result.row_count,
            event_counts=result.event_counts,
            imported_at=datetime.strptime(candidate.trade_date, "%Y-%m-%d").replace(tzinfo=timezone.utc),
            source_files=[source_file],
            output_files=output_files,
            source_name=candidate.source_file,
            source_stream_sha256=source_file.sha256,
            parser_config_sha256=config_sha256,
            filters={
                "symbol": candidate.symbol,
                "start_time_ms": effective_start,
                "end_time_ms": effective_end,
                "depth": effective_depth,
            },
            message_counts=result.message_counts,
            truncation_limits={
                "max_working_bytes": max_working_bytes,
                "min_free_bytes": min_free_bytes,
            },
        )
        (temporary / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        _check_working_set(
            temporary,
            source_path=source_path,
            min_free_bytes=min_free_bytes,
            max_working_bytes=max_working_bytes,
        )
        temporary.rename(final_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def iter_records(path: Path) -> Iterator[ParsedRecord]:
    with path.open("rb") as compressed:
        stream: BinaryIO
        if path.name.lower().endswith(".gz"):
            stream = gzip.GzipFile(fileobj=compressed, mode="rb")
        else:
            stream = compressed
        sequence = 0
        previous_timestamp = -1
        while True:
            length_bytes = stream.read(2)
            if not length_bytes:
                break
            if len(length_bytes) != 2:
                raise ValueError("truncated ITCH message length prefix")
            length = struct.unpack(">H", length_bytes)[0]
            if length == 0:
                raise ValueError("ITCH message length must be positive")
            payload = stream.read(length)
            if len(payload) != length:
                raise ValueError(f"truncated ITCH message {sequence + 1}")
            sequence += 1
            message_type = chr(payload[0])
            expected = MESSAGE_LENGTHS.get(message_type)
            if expected is not None and length != expected:
                raise ValueError(
                    f"ITCH message {sequence} type {message_type}: expected {expected} bytes, found {length}"
                )
            if length < 11:
                raise ValueError(f"ITCH message {sequence}: header is shorter than 11 bytes")
            stock_locate = struct.unpack_from(">H", payload, 1)[0]
            tracking_number = struct.unpack_from(">H", payload, 3)[0]
            timestamp_ns = int.from_bytes(payload[5:11], "big")
            if not 0 <= timestamp_ns < 86_400 * 1_000_000_000:
                raise ValueError(f"ITCH message {sequence}: timestamp is outside the trading day")
            if timestamp_ns < previous_timestamp:
                raise ValueError(f"ITCH message {sequence}: timestamp decreased")
            previous_timestamp = timestamp_ns
            yield ParsedRecord(
                source_sequence=sequence,
                message_type=message_type,
                stock_locate=stock_locate,
                tracking_number=tracking_number,
                timestamp_ns=timestamp_ns,
                payload=payload,
            )


def _normalize(
    source_path: Path,
    directory: Path,
    *,
    symbol: str,
    trade_date: str,
    start_ns: int,
    end_ns: int,
    depth: int,
    min_free_bytes: int,
    max_working_bytes: int,
) -> NormalizationResult:
    import pyarrow as pa
    import pyarrow.parquet as pq

    locate_by_symbol: dict[str, int] = {}
    symbol_by_locate: dict[int, str] = {}
    active: dict[int, Order] = {}
    seen_references: set[int] = set()
    book: dict[str, dict[int, int]] = {"BUY": {}, "SELL": {}}
    counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    event_rows: list[dict[str, object]] = []
    book_rows: list[dict[str, object]] = []
    event_writer: pq.ParquetWriter | None = None
    book_writer: pq.ParquetWriter | None = None
    selected_locate: int | None = None
    first_timestamp = -1
    last_timestamp = -1
    try:
        for record in iter_records(source_path):
            counts[record.message_type] += 1
            if record.source_sequence % RESOURCE_CHECK_RECORDS == 0:
                _check_working_set(
                    directory,
                    source_path=source_path,
                    min_free_bytes=min_free_bytes,
                    max_working_bytes=max_working_bytes,
                )
            if record.message_type == "R":
                directory_symbol = _alpha(record.payload[11:19])
                previous_symbol = symbol_by_locate.setdefault(record.stock_locate, directory_symbol)
                previous_locate = locate_by_symbol.setdefault(directory_symbol, record.stock_locate)
                if previous_symbol != directory_symbol or previous_locate != record.stock_locate:
                    raise ValueError("ITCH Stock Directory mappings are not one-to-one")
                if directory_symbol == symbol:
                    selected_locate = record.stock_locate
                continue
            if record.message_type not in BOOK_MESSAGE_TYPES:
                continue
            if selected_locate is None:
                selected_locate = locate_by_symbol.get(symbol)
                if selected_locate is None:
                    raise ValueError(f"ITCH book message appeared before Stock Directory entry for {symbol}")
            if record.stock_locate != selected_locate:
                continue
            event = _apply_book_message(record, symbol, trade_date, active, seen_references, book)
            _validate_book(book, record.source_sequence)
            if not start_ns <= record.timestamp_ns < end_ns:
                continue
            if first_timestamp < 0:
                first_timestamp = record.timestamp_ns
            last_timestamp = record.timestamp_ns
            event_counts[str(event["event_kind"])] += 1
            event_rows.append(event)
            book_rows.append(
                {
                    "source_sequence": record.source_sequence,
                    "timestamp_ns_since_midnight": record.timestamp_ns,
                    "depth": depth,
                    "asks": _levels(book["SELL"], side="SELL", depth=depth),
                    "bids": _levels(book["BUY"], side="BUY", depth=depth),
                }
            )
            if len(event_rows) >= CHUNK_ROWS:
                event_writer, book_writer = _write_chunks(
                    pa, pq, directory, event_rows, book_rows, event_writer, book_writer
                )
                event_rows.clear()
                book_rows.clear()
                _check_working_set(
                    directory,
                    source_path=source_path,
                    min_free_bytes=min_free_bytes,
                    max_working_bytes=max_working_bytes,
                )
        if selected_locate is None:
            raise ValueError(f"symbol {symbol} is absent from ITCH Stock Directory messages")
        if event_rows:
            event_writer, book_writer = _write_chunks(
                pa, pq, directory, event_rows, book_rows, event_writer, book_writer
            )
        if event_writer is None or book_writer is None:
            raise ValueError("selected ITCH window contains no visible-order lifecycle events")
    finally:
        if event_writer is not None:
            event_writer.close()
        if book_writer is not None:
            book_writer.close()
    return NormalizationResult(
        row_count=sum(event_counts.values()),
        event_counts=dict(sorted(event_counts.items())),
        message_counts=dict(sorted(counts.items())),
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
    )


def _apply_book_message(
    record: ParsedRecord,
    symbol: str,
    trade_date: str,
    active: dict[int, Order],
    seen_references: set[int],
    book: dict[str, dict[int, int]],
) -> dict[str, object]:
    payload = record.payload
    message_type = record.message_type
    match_number: int | None = None
    printable: bool | None = None
    replacement_reference: int | None = None
    mpid: str | None = None
    if message_type in {"A", "F"}:
        order_reference = struct.unpack_from(">Q", payload, 11)[0]
        side = _side(payload[19:20], record.source_sequence)
        size = struct.unpack_from(">I", payload, 20)[0]
        message_symbol = _alpha(payload[24:32])
        price = struct.unpack_from(">I", payload, 32)[0]
        mpid = _alpha(payload[36:40]) if message_type == "F" else None
        if message_symbol != symbol:
            raise ValueError(f"ITCH message {record.source_sequence}: symbol does not match Stock Directory")
        if not 0 < order_reference <= 2**63 - 1 or order_reference in seen_references:
            raise ValueError(f"ITCH message {record.source_sequence}: order reference is reused")
        _require_positive(size, price, record.source_sequence)
        order = Order(symbol=symbol, side=side, shares=size, price_x10000=price, mpid=mpid)
        active[order_reference] = order
        seen_references.add(order_reference)
        _adjust_level(book, side, price, size, record.source_sequence)
        event_kind = "ADD"
    else:
        order_reference = struct.unpack_from(">Q", payload, 11)[0]
        if order_reference > 2**63 - 1:
            raise ValueError(f"ITCH message {record.source_sequence}: order reference exceeds int64")
        order = active.get(order_reference)
        if order is None:
            raise ValueError(f"ITCH message {record.source_sequence}: unknown active order reference")
        side = order.side
        price = order.price_x10000
        mpid = order.mpid
        if message_type in {"E", "C", "X"}:
            size = struct.unpack_from(">I", payload, 19)[0]
            if size <= 0 or size > order.shares:
                raise ValueError(f"ITCH message {record.source_sequence}: invalid order reduction")
            remaining = order.shares - size
            _adjust_level(book, side, order.price_x10000, -size, record.source_sequence)
            if remaining:
                active[order_reference] = Order(symbol, side, remaining, order.price_x10000, order.mpid)
            else:
                active.pop(order_reference)
            if message_type in {"E", "C"}:
                event_kind = "VISIBLE_EXECUTION"
                match_number = struct.unpack_from(">Q", payload, 23)[0]
                if message_type == "C":
                    printable = payload[31:32] == b"Y"
                    price = struct.unpack_from(">I", payload, 32)[0]
                    if price <= 0:
                        raise ValueError(f"ITCH message {record.source_sequence}: execution price must be positive")
            else:
                event_kind = "PARTIAL_CANCEL"
        elif message_type == "D":
            size = order.shares
            _adjust_level(book, side, price, -size, record.source_sequence)
            active.pop(order_reference)
            event_kind = "DELETE"
        elif message_type == "U":
            replacement_reference = struct.unpack_from(">Q", payload, 19)[0]
            size = struct.unpack_from(">I", payload, 27)[0]
            price = struct.unpack_from(">I", payload, 31)[0]
            if not 0 < replacement_reference <= 2**63 - 1 or replacement_reference in seen_references:
                raise ValueError(f"ITCH message {record.source_sequence}: replacement reference is reused")
            _require_positive(size, price, record.source_sequence)
            _adjust_level(book, side, order.price_x10000, -order.shares, record.source_sequence)
            _adjust_level(book, side, price, size, record.source_sequence)
            active.pop(order_reference)
            active[replacement_reference] = Order(symbol, side, size, price, order.mpid)
            seen_references.add(replacement_reference)
            event_kind = "REPLACE"
        else:  # pragma: no cover - guarded by BOOK_MESSAGE_TYPES
            raise AssertionError(message_type)
    return {
        "source_sequence": record.source_sequence,
        "timestamp_ns_since_midnight": record.timestamp_ns,
        "event_kind": event_kind,
        "source_event_code": ord(message_type),
        "source_order_id": order_reference,
        "size": size,
        "price_x10000": price,
        "direction": 1 if side == "BUY" else -1,
        "book_side": side,
        "aggressor_side": (
            "SELL" if side == "BUY" else "BUY"
        ) if message_type in {"E", "C"} else None,
        "halt_state": None,
        "symbol": symbol,
        "trade_date": trade_date,
        "raw_message_type": message_type,
        "stock_locate": record.stock_locate,
        "tracking_number": record.tracking_number,
        "match_number": match_number,
        "mpid": mpid,
        "printable": printable,
        "replacement_order_reference": replacement_reference,
    }


def _write_chunks(pa, pq, directory, event_rows, book_rows, event_writer, book_writer):
    event_table = pa.Table.from_pylist(event_rows, schema=_event_schema(pa))
    book_table = pa.Table.from_pylist(book_rows, schema=_book_schema(pa))
    if event_writer is None:
        event_writer = pq.ParquetWriter(directory / "events.parquet", event_table.schema, compression="zstd")
        book_writer = pq.ParquetWriter(
            directory / "book_snapshots.parquet", book_table.schema, compression="zstd"
        )
    event_writer.write_table(event_table)
    book_writer.write_table(book_table)
    return event_writer, book_writer


def _event_schema(pa):
    return pa.schema(
        [
            ("source_sequence", pa.int64()),
            ("timestamp_ns_since_midnight", pa.int64()),
            ("event_kind", pa.string()),
            ("source_event_code", pa.int8()),
            ("source_order_id", pa.int64()),
            ("size", pa.int64()),
            ("price_x10000", pa.int64()),
            ("direction", pa.int8()),
            ("book_side", pa.string()),
            ("aggressor_side", pa.string()),
            ("halt_state", pa.string()),
            ("symbol", pa.string()),
            ("trade_date", pa.string()),
            ("raw_message_type", pa.string()),
            ("stock_locate", pa.int32()),
            ("tracking_number", pa.int32()),
            ("match_number", pa.uint64()),
            ("mpid", pa.string()),
            ("printable", pa.bool_()),
            ("replacement_order_reference", pa.uint64()),
        ]
    )


def _book_schema(pa):
    level = pa.struct(
        [("level", pa.int16()), ("price_x10000", pa.int64()), ("quantity", pa.int64())]
    )
    return pa.schema(
        [
            ("source_sequence", pa.int64()),
            ("timestamp_ns_since_midnight", pa.int64()),
            ("depth", pa.int16()),
            ("asks", pa.list_(level)),
            ("bids", pa.list_(level)),
        ]
    )


def _levels(levels: dict[int, int], *, side: str, depth: int) -> list[dict[str, int]]:
    prices = sorted(levels, reverse=side == "BUY")[:depth]
    return [
        {"level": index, "price_x10000": price, "quantity": levels[price]}
        for index, price in enumerate(prices, start=1)
    ]


def _adjust_level(
    book: dict[str, dict[int, int]], side: str, price: int, delta: int, sequence: int
) -> None:
    new_quantity = book[side].get(price, 0) + delta
    if new_quantity < 0:
        raise ValueError(f"ITCH message {sequence}: visible depth became negative")
    if new_quantity:
        book[side][price] = new_quantity
    else:
        book[side].pop(price, None)


def _validate_book(book: dict[str, dict[int, int]], sequence: int) -> None:
    if any(quantity <= 0 for side in book.values() for quantity in side.values()):
        raise ValueError(f"ITCH message {sequence}: visible depth must be positive")
    if book["BUY"] and book["SELL"] and max(book["BUY"]) > min(book["SELL"]):
        raise ValueError(f"ITCH message {sequence}: visible book is crossed")


def _check_source_quota(source_path: Path, *, max_working_bytes: int) -> None:
    if source_path.stat().st_size > max_working_bytes:
        raise ValueError("ITCH source exceeds the configured maximum working set")


def _check_working_set(
    directory: Path,
    *,
    source_path: Path,
    min_free_bytes: int,
    max_working_bytes: int,
) -> None:
    output_bytes = sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
    working_bytes = source_path.stat().st_size + output_bytes + _process_resident_bytes()
    if working_bytes > max_working_bytes:
        raise ValueError("ITCH normalization exceeded the configured maximum working set")
    _check_disk_quota(directory, min_free_bytes=min_free_bytes)


def _process_resident_bytes() -> int:
    statm = Path("/proc/self/statm")
    if statm.is_file():
        fields = statm.read_text(encoding="ascii").split()
        if len(fields) >= 2:
            return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")
    maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(maximum_rss if sys.platform == "darwin" else maximum_rss * 1024)


def _check_disk_quota(directory: Path, *, min_free_bytes: int) -> None:
    if shutil.disk_usage(directory).free < min_free_bytes:
        raise ValueError("ITCH normalization stopped before free disk fell below the configured reserve")


def _file_metadata(path: Path, name: str | None = None) -> DatasetFile:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return DatasetFile(name=name or path.name, size_bytes=path.stat().st_size, sha256=digest.hexdigest())


def _iter_itch_manifests(processed_dir: Path) -> Iterator[DatasetManifest]:
    root = processed_dir.resolve()
    if not root.exists():
        return
    for path in root.glob("*/manifest.json"):
        try:
            manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.status == "ready" and manifest.source_type == "nasdaq_itch":
            yield manifest


def _is_itch_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name.lower()
    return name.endswith((".itch", ".itch.gz", ".bin", ".bin.gz")) or "itch" in name and name.endswith(".gz")


def _trade_date_from_name(name: str) -> str | None:
    import re

    for pattern, positions in DATE_PATTERNS:
        match = re.search(pattern, name)
        if match:
            year, month, day = (int(match.group(position)) for position in positions)
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                continue
    return None


def _alpha(value: bytes) -> str:
    try:
        return value.decode("ascii").rstrip(" ")
    except UnicodeDecodeError as exc:
        raise ValueError("ITCH alpha field is not ASCII") from exc


def _side(value: bytes, sequence: int) -> str:
    if value == b"B":
        return "BUY"
    if value == b"S":
        return "SELL"
    raise ValueError(f"ITCH message {sequence}: invalid buy/sell indicator")


def _require_positive(size: int, price: int, sequence: int) -> None:
    if size <= 0 or price <= 0:
        raise ValueError(f"ITCH message {sequence}: size and price must be positive")
