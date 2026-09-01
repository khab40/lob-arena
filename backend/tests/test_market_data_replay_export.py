import hashlib
import urllib.parse
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.data_ingestion.models import DatasetManifest
from app.market_data import replay_export


def _event(sequence: int, *, snapshot: bool = False) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": 1,
        "event_type": "snapshot" if snapshot else "add",
        "event_id": f"event-{sequence}",
        "sequence": sequence,
        "source": "historical",
        "source_sequence": sequence,
        "symbol": "AAPL",
        "venue": "XNAS",
        "tick": sequence,
        "exchange_timestamp_ns": sequence * 100,
        "received_timestamp_ns": sequence * 100,
    }
    if snapshot:
        event.update(
            {
                "depth": 1,
                "book": {
                    "bids": [{"price": 99.0, "quantity": 10.0}],
                    "asks": [{"price": 101.0, "quantity": 10.0}],
                    "best_bid": 99.0,
                    "best_ask": 101.0,
                    "mid": 100.0,
                    "spread": 2.0,
                },
            }
        )
    else:
        event.update(
            {
                "order_id": f"order-{sequence}",
                "agent_id": "historical",
                "side": "buy",
                "price": 99.0,
                "quantity": 10.0,
                "owner": "normal",
            }
        )
    return event


def test_stream_export_writes_one_parquet_row_group_per_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = {
        0: {
            "events": [_event(1), _event(2, snapshot=True)],
            "next_after_sequence": 2,
            "has_more": True,
        },
        2: {
            "events": [_event(3), _event(4, snapshot=True)],
            "next_after_sequence": 4,
            "has_more": False,
        },
    }
    requested_after: list[int] = []

    def request(url: str, **_: object) -> dict[str, object]:
        after = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["afterSequence"][0])
        requested_after.append(after)
        return responses[after]

    monkeypatch.setattr(replay_export, "_json_request", request)
    events_path = tmp_path / "events.jsonl"
    snapshots_path = tmp_path / "snapshots.parquet"

    result = replay_export._write_stream_artifacts(
        base_url="http://java",
        stream_id="stream-1",
        events_path=events_path,
        snapshots_path=snapshots_path,
        timeout_seconds=1,
    )

    assert result == (4, 2, 100, 400)
    assert requested_after == [0, 2]
    assert len(events_path.read_text(encoding="utf-8").splitlines()) == 4
    parquet = pq.ParquetFile(snapshots_path)
    assert parquet.metadata.num_rows == 2
    assert parquet.metadata.num_row_groups == 2


def test_stream_export_rejects_empty_nonterminal_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        replay_export,
        "_json_request",
        lambda *args, **kwargs: {
            "events": [],
            "next_after_sequence": 1,
            "has_more": True,
        },
    )

    with pytest.raises(ValueError, match="empty before the end"):
        replay_export._write_stream_artifacts(
            base_url="http://java",
            stream_id="stream-1",
            events_path=tmp_path / "events.jsonl",
            snapshots_path=tmp_path / "snapshots.parquet",
            timeout_seconds=1,
        )


def test_file_hashing_does_not_materialize_the_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b"bounded-memory" * 100_000
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("read_bytes was called"))

    assert replay_export._sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_comparison_release_deletes_primary_and_repeat_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []

    def request(url: str, **kwargs: object) -> dict[str, object]:
        assert kwargs["method"] == "DELETE"
        stream_id = urllib.parse.unquote(url.rsplit("/", maxsplit=1)[1])
        deleted.append(stream_id)
        return {"stream_id": stream_id, "released": True}

    monkeypatch.setattr(replay_export, "_json_request", request)

    replay_export._release_comparison_streams(
        "http://java",
        {
            "control": {"stream_id": "control"},
            "hybrid": {"stream_id": "hybrid"},
            "determinism": {
                "control_repeat_stream_id": "control-repeat",
                "hybrid_repeat_stream_id": "hybrid-repeat",
            },
        },
        1,
    )

    assert deleted == ["control", "hybrid", "control-repeat", "hybrid-repeat"]


def test_hybrid_ground_truth_is_validated_before_stream_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ground_truth = {
        "schema_version": "scenario_ground_truth_v1",
        "scenario_family": "quote_stuffing",
        "source": "synthetic_scenario",
        "has_attack": True,
        "start_tick": 2,
        "end_tick": 5,
        "phase_windows": {
            "pressure_phase": {"start_tick": 2, "end_tick": 2},
            "cancellation_phase": {"start_tick": 2, "end_tick": 5},
        },
    }
    comparison = {
        "schema_version": "historical_replay_comparison_v1",
        "control": {"stream_id": "control"},
        "hybrid": {"stream_id": "hybrid", "ground_truth": ground_truth},
        "determinism": {
            "control_stream_match": True,
            "hybrid_stream_match": True,
            "control_trace_match": True,
            "hybrid_trace_match": True,
            "historical_snapshot_match": True,
            "control_repeat_stream_id": "control-repeat",
            "hybrid_repeat_stream_id": "hybrid-repeat",
        },
    }

    def request(url: str, **kwargs: object) -> dict[str, object]:
        if kwargs["method"] == "POST":
            return comparison
        stream_id = urllib.parse.unquote(url.rsplit("/", maxsplit=1)[1])
        return {"stream_id": stream_id, "released": True}

    monkeypatch.setattr(replay_export, "_json_request", request)
    monkeypatch.setattr(
        replay_export,
        "_export_stream",
        lambda **kwargs: pytest.fail("canonical stream download started before label validation"),
    )
    dataset = DatasetManifest.model_construct(
        dataset_id="xnas-20190102-aapl",
        source_type="nasdaq_itch",
        symbol="AAPL",
        venue="XNAS",
        trade_date="2019-01-02",
    )

    with pytest.raises(ValueError, match="must not overlap"):
        replay_export.export_replay_comparison(
            base_url="http://java",
            dataset=dataset,
            attack_family="quote_stuffing",
            seed=41,
            output_root=tmp_path,
            timeout_seconds=1,
        )


def test_comparison_releases_streams_when_export_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    deleted: list[str] = []
    comparison = {
        "schema_version": "historical_replay_comparison_v1",
        "control": {"stream_id": "control"},
        "hybrid": {
            "stream_id": "hybrid",
            "ground_truth": {
                "scenario_family": "quote_stuffing",
                "source": "synthetic_scenario",
                "has_attack": True,
                "start_tick": 2,
                "end_tick": 5,
                "phase_windows": {
                    "pressure_phase": {"start_tick": 2, "end_tick": 5},
                },
            },
        },
        "determinism": {
            "control_stream_match": True,
            "hybrid_stream_match": True,
            "control_trace_match": True,
            "hybrid_trace_match": True,
            "historical_snapshot_match": True,
            "control_repeat_stream_id": "control-repeat",
            "hybrid_repeat_stream_id": "hybrid-repeat",
        },
    }

    def request(url: str, **kwargs: object) -> dict[str, object]:
        if kwargs["method"] == "POST":
            return comparison
        stream_id = urllib.parse.unquote(url.rsplit("/", maxsplit=1)[1])
        deleted.append(stream_id)
        return {"stream_id": stream_id, "released": True}

    monkeypatch.setattr(replay_export, "_json_request", request)
    def fail_export(**_: object) -> Path:
        raise ValueError("label validation failed")

    monkeypatch.setattr(replay_export, "_export_stream", fail_export)
    dataset = DatasetManifest.model_construct(
        dataset_id="xnas-20190102-aapl",
        source_type="nasdaq_itch",
        symbol="AAPL",
        venue="XNAS",
        trade_date="2019-01-02",
    )

    with pytest.raises(ValueError, match="label validation failed"):
        replay_export.export_replay_comparison(
            base_url="http://java",
            dataset=dataset,
            attack_family="quote_stuffing",
            seed=41,
            output_root=tmp_path,
            timeout_seconds=1,
        )

    assert deleted == ["control", "hybrid", "control-repeat", "hybrid-repeat"]
