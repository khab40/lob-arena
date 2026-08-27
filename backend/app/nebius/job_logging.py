from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterator


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SENSITIVE_FIELD_PARTS = ("credential", "password", "secret", "token")
_Scalar = str | int | float | bool | None


@dataclass(frozen=True)
class JobLogger:
    """Emit concise JSON lifecycle records suitable for Nebius Job logs."""

    job_type: str

    def __post_init__(self) -> None:
        if _IDENTIFIER_PATTERN.fullmatch(self.job_type) is None:
            raise ValueError("job type must be a bounded lowercase identifier")

    def info(self, event: str, description: str, **fields: _Scalar) -> None:
        self._emit("INFO", event, description, fields)

    def error(self, event: str, description: str, **fields: _Scalar) -> None:
        self._emit("ERROR", event, description, fields)

    @contextmanager
    def phase(self, event: str, description: str, **fields: _Scalar) -> Iterator[None]:
        started = time.perf_counter()
        self.info(f"{event}.started", description, **fields)
        try:
            yield
        except Exception as exc:
            self.error(
                f"{event}.failed",
                description,
                **fields,
                duration_ms=_duration_ms(started),
                error_type=type(exc).__name__,
            )
            raise
        self.info(
            f"{event}.completed",
            description,
            **fields,
            duration_ms=_duration_ms(started),
        )

    def _emit(
        self,
        level: str,
        event: str,
        description: str,
        fields: dict[str, _Scalar],
    ) -> None:
        if _IDENTIFIER_PATTERN.fullmatch(event) is None:
            raise ValueError("job log event must be a bounded lowercase identifier")
        if not description or "\n" in description or len(description) > 240:
            raise ValueError("job log description must be one bounded line")
        for name in fields:
            normalized = re.sub(r"[^a-z]", "", name.lower())
            if any(part in normalized for part in _SENSITIVE_FIELD_PARTS):
                raise ValueError(f"sensitive job log field is forbidden: {name}")
        payload: dict[str, _Scalar] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "job_type": self.job_type,
            "event": event,
            "description": description,
            **fields,
        }
        print(json.dumps(payload, sort_keys=True, allow_nan=False), flush=True)


def _duration_ms(started: float) -> float:
    return round(max(0.0, time.perf_counter() - started) * 1000, 3)
