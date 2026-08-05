"""Capture repeatable realism traces from the authoritative Java control plane."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib import request


RUN_SCHEMA_VERSION = "market_profile_simulation_runs_v1"


def capture_simulation_runs(
    base_url: str,
    profile: dict[str, Any],
    *,
    ticks: int = 120,
    master_seed: int = 42,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    if ticks < 4 or ticks > 10_000:
        raise ValueError("simulation ticks must be between 4 and 10000")
    endpoint = base_url.rstrip("/")
    calibrated = _capture_mode(
        endpoint,
        source_type="synthetic_profile",
        dataset_id=str(profile["profile_id"]),
        ticks=ticks,
        master_seed=master_seed,
        timeout_seconds=timeout_seconds,
    )
    calibrated["profile_sha256"] = profile["profile_sha256"]
    hardcoded = _capture_mode(
        endpoint,
        source_type="synthetic",
        dataset_id="",
        ticks=ticks,
        master_seed=master_seed,
        timeout_seconds=timeout_seconds,
    )
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "producer": "java_control_plane",
        "master_seed": master_seed,
        "calibrated": calibrated,
        "hardcoded": hardcoded,
    }


def _capture_mode(
    base_url: str,
    *,
    source_type: str,
    dataset_id: str,
    ticks: int,
    master_seed: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    first = _capture_trace(
        base_url,
        source_type=source_type,
        dataset_id=dataset_id,
        ticks=ticks,
        master_seed=master_seed,
        attack=False,
        timeout_seconds=timeout_seconds,
    )
    repeated = _capture_trace(
        base_url,
        source_type=source_type,
        dataset_id=dataset_id,
        ticks=ticks,
        master_seed=master_seed,
        attack=False,
        timeout_seconds=timeout_seconds,
    )
    attack = _capture_trace(
        base_url,
        source_type=source_type,
        dataset_id=dataset_id,
        ticks=40,
        master_seed=master_seed,
        attack=True,
        timeout_seconds=timeout_seconds,
    )
    repeated_attack = _capture_trace(
        base_url,
        source_type=source_type,
        dataset_id=dataset_id,
        ticks=40,
        master_seed=master_seed,
        attack=True,
        timeout_seconds=timeout_seconds,
    )
    trace_sha = _trace_sha256(first)
    repeat_sha = _trace_sha256(repeated)
    attack_sha = _trace_sha256(attack)
    repeat_attack_sha = _trace_sha256(repeated_attack)
    if trace_sha != repeat_sha or attack_sha != repeat_attack_sha:
        raise ValueError(f"Java {source_type} simulation was not repeat deterministic")
    return {
        "source_type": source_type,
        "dataset_id": dataset_id,
        "states": first,
        "trace_sha256": trace_sha,
        "repeat_trace_sha256": repeat_sha,
        "attack_states": attack,
        "attack_trace_sha256": attack_sha,
        "repeat_attack_trace_sha256": repeat_attack_sha,
        "attack_windows": {"before": [0, 19], "during": [20, 29], "after": [30, 39]},
    }


def _capture_trace(
    base_url: str,
    *,
    source_type: str,
    dataset_id: str,
    ticks: int,
    master_seed: int,
    attack: bool,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    loaded = _json_request(
        f"{base_url}/api/arena/data-source",
        {"source_type": source_type, "dataset_id": dataset_id, "master_seed": master_seed},
        timeout_seconds,
    )
    if source_type == "synthetic_profile":
        market_data = loaded.get("market_data") or {}
        if market_data.get("source_type") != "synthetic_profile":
            raise ValueError("Java control plane did not load the requested market profile")
    states: list[dict[str, Any]] = []
    for index in range(ticks):
        if attack and index == 20:
            _json_request(
                f"{base_url}/api/scenarios/liquidity_evaporation",
                None,
                timeout_seconds,
            )
            _json_request(f"{base_url}/api/simulation/pause", None, timeout_seconds)
        state = _json_request(f"{base_url}/internal/arena/step", None, timeout_seconds)
        states.append(_evidence_state(state))
    return states


def _evidence_state(state: dict[str, Any]) -> dict[str, Any]:
    tick = int(state["tick"])
    result: dict[str, Any] = {
        "tick": tick,
        "book": state.get("book") or {},
        "exchange_events": [
            {
                key: value
                for key, value in event.items()
                if key not in {"scenario_id", "scenario_name"}
            }
            for event in state.get("exchange_events", [])
            if int(event.get("tick") or -1) == tick
        ],
    }
    if state.get("market_data") is not None:
        result["market_data"] = state["market_data"]
    return result


def _json_request(url: str, payload: dict[str, Any] | None, timeout_seconds: float) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    call = request.Request(
        url,
        data=body if body is not None else b"",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with request.urlopen(call, timeout=timeout_seconds) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"Java control plane returned a non-object response from {url}")
    return decoded


def _trace_sha256(states: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        states,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()
