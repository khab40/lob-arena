from typing import Any

import pytest

from app.calibration import simulation_capture


def test_capture_requires_repeatable_java_normal_and_attack_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def capture(*args: Any, attack: bool, ticks: int, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"tick": index + 1, "book": {}, "exchange_events": []} for index in range(ticks)]

    monkeypatch.setattr(simulation_capture, "_capture_trace", capture)

    result = simulation_capture.capture_simulation_runs(
        "http://arena.test",
        {"profile_id": "fixture-profile", "profile_sha256": "a" * 64},
        ticks=4,
        master_seed=99,
    )

    assert result["producer"] == "java_control_plane"
    assert result["master_seed"] == 99
    assert result["calibrated"]["profile_sha256"] == "a" * 64
    assert result["calibrated"]["trace_sha256"] == result["calibrated"]["repeat_trace_sha256"]
    assert result["hardcoded"]["attack_trace_sha256"] == result["hardcoded"]["repeat_attack_trace_sha256"]


def test_capture_rejects_a_repeat_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    call = 0

    def capture(*args: Any, attack: bool, ticks: int, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal call
        call += 1
        return [{"tick": index + call, "book": {}, "exchange_events": []} for index in range(ticks)]

    monkeypatch.setattr(simulation_capture, "_capture_trace", capture)

    with pytest.raises(ValueError, match="not repeat deterministic"):
        simulation_capture.capture_simulation_runs(
            "http://arena.test",
            {"profile_id": "fixture-profile", "profile_sha256": "a" * 64},
            ticks=4,
        )
