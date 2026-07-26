from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path


class DiskBackedUniqueIds:
    """Exact whole-stream uniqueness with bounded process memory."""

    def __init__(self, *, prefix: str = "lob-arena-event-ids-") -> None:
        handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".sqlite3", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=OFF")
        self._connection.execute("PRAGMA synchronous=OFF")
        self._connection.execute("PRAGMA temp_store=FILE")
        self._connection.execute(
            "CREATE TABLE event_ids (event_id TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._closed = False

    def add(self, event_id: str) -> None:
        if self._closed:
            raise RuntimeError("event ID validator is closed")
        try:
            self._connection.execute(
                "INSERT INTO event_ids(event_id) VALUES (?)",
                (event_id,),
            )
        except sqlite3.IntegrityError as exception:
            raise ValueError("canonical event IDs must be unique") from exception

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> "DiskBackedUniqueIds":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
