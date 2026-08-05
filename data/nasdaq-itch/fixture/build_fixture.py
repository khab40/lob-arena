"""Build the redistributable synthetic ITCH 5.0 lifecycle fixture."""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

OUTPUT = Path(__file__).with_name("2026-01-02.NASDAQ_ITCH50.fixture.gz")


def header(message_type: str, locate: int, tracking: int, timestamp_ns: int) -> bytes:
    return message_type.encode("ascii") + struct.pack(">HH", locate, tracking) + timestamp_ns.to_bytes(6, "big")


def framed(payload: bytes) -> bytes:
    return struct.pack(">H", len(payload)) + payload


def alpha(value: str, size: int) -> bytes:
    return value.encode("ascii").ljust(size, b" ")


def build() -> bytes:
    base = 34_200_000_000_000
    messages = [
        header("S", 0, 1, base) + b"O",
        header("R", 1, 2, base + 1)
        + alpha("AAPL", 8)
        + b"Q"
        + b"N"
        + struct.pack(">I", 100)
        + b"N"
        + b"C"
        + alpha("", 2)
        + b"P"
        + b"N"
        + b"N"
        + b"1"
        + b"Y"
        + struct.pack(">I", 10000)
        + b"N",
        header("R", 2, 3, base + 2)
        + alpha("MSFT", 8)
        + b"Q"
        + b"N"
        + struct.pack(">I", 100)
        + b"N"
        + b"C"
        + alpha("", 2)
        + b"P"
        + b"N"
        + b"N"
        + b"1"
        + b"Y"
        + struct.pack(">I", 10000)
        + b"N",
        header("H", 1, 4, base + 3) + alpha("AAPL", 8) + b"T " + alpha("", 4),
        header("A", 1, 5, base + 4)
        + struct.pack(">Q", 1)
        + b"B"
        + struct.pack(">I", 100)
        + alpha("AAPL", 8)
        + struct.pack(">I", 1_000_000),
        header("F", 1, 6, base + 5)
        + struct.pack(">Q", 2)
        + b"S"
        + struct.pack(">I", 200)
        + alpha("AAPL", 8)
        + struct.pack(">I", 1_010_000)
        + b"ABCD",
        header("E", 1, 7, base + 6) + struct.pack(">QI", 1, 10) + struct.pack(">Q", 101),
        header("C", 1, 8, base + 7)
        + struct.pack(">QI", 2, 20)
        + struct.pack(">Q", 102)
        + b"Y"
        + struct.pack(">I", 1_005_000),
        header("X", 1, 9, base + 8) + struct.pack(">QI", 1, 10),
        header("U", 1, 10, base + 9)
        + struct.pack(">QQI", 1, 3, 50)
        + struct.pack(">I", 995_000),
        header("D", 1, 11, base + 10) + struct.pack(">Q", 3),
        header("D", 1, 12, base + 11) + struct.pack(">Q", 2),
        header("S", 0, 13, base + 12) + b"C",
    ]
    return b"".join(framed(message) for message in messages)


if __name__ == "__main__":
    OUTPUT.write_bytes(gzip.compress(build(), compresslevel=9, mtime=0))
