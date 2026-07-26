from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.exchange.schemas import (
    AddOrderEvent,
    CancelOrderEvent,
    CanonicalExchangeEvent,
    ExecuteOrderEvent,
    LobSnapshotEvent,
    ModifyOrderEvent,
    OrderBookSnapshot,
    PriceLevel,
)
from app.features.io import (
    feature_arrow_schema,
    fetch_events,
    load_events_jsonl,
    load_labels,
    load_run_metadata,
    write_feature_run,
)
from app.features.models import (
    FeaturePipelineConfig,
    FeatureRunMetadata,
    LabelSpec,
    LabelWindow,
    assign_label,
)
from app.features.pipeline import (
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    FeaturePipeline,
)
from scripts.generate_features import main as generate_features

BASE_TIMESTAMP_NS = 34_200_000_000_000


def metadata(
    *,
    source_type: str = "lobster",
    session_id: str = "SPY-2012-06-21-am",
    dataset_id: str = "fixture-v1",
    run_id: str = "feature-test",
) -> FeatureRunMetadata:
    return FeatureRunMetadata(
        run_id=run_id,
        dataset_id=dataset_id,
        source_type=source_type,  # type: ignore[arg-type]
        instrument="SPY",
        venue="LOBSTER",
        session_id=session_id,
        session_date=date(2012, 6, 21),
        seed=42 if source_type != "lobster" else None,
        price_tick_size=0.01,
        quantity_lot_size=1.0,
        tick_interval_ns=1_000_000_000,
    )


def config() -> FeaturePipelineConfig:
    return FeaturePipelineConfig(
        short_window_ns=2_000_000_000,
        long_window_ns=5_000_000_000,
        zscore_min_periods=3,
        rapid_cancel_ns=1_500_000_000,
        replenishment_ns=1_500_000_000,
        burst_gap_ns=1,
        large_order_quantity=1_000,
        depth_levels=4,
    )


def canonical_stream(
    *,
    hybrid: bool = False,
    source: str = "historical",
    ticks: int = 16,
) -> list[CanonicalExchangeEvent]:
    events: list[CanonicalExchangeEvent] = []
    sequence = 1
    previous_order: str | None = None
    for tick in range(ticks):
        timestamp_ns = BASE_TIMESTAMP_NS + tick * 1_000_000_000
        if previous_order is not None:
            events.append(
                CancelOrderEvent(
                    event_id=f"hist-cancel-{tick}",
                    sequence=sequence,
                    source=source,  # type: ignore[arg-type]
                    source_sequence=tick * 2,
                    symbol="SPY",
                    venue="LOBSTER",
                    tick=tick,
                    exchange_timestamp_ns=timestamp_ns,
                    order_id=previous_order,
                    agent_id="HIST:participant",
                    side="buy",
                    price=99.99,
                    quantity=100,
                )
            )
            sequence += 1
        order_id = f"HIST:{tick}"
        events.append(
            AddOrderEvent(
                event_id=f"hist-add-{tick}",
                sequence=sequence,
                source=source,  # type: ignore[arg-type]
                source_sequence=tick * 2 + 1,
                symbol="SPY",
                venue="LOBSTER",
                tick=tick,
                exchange_timestamp_ns=timestamp_ns,
                order_id=order_id,
                agent_id="HIST:participant",
                side="buy",
                price=99.99,
                quantity=100,
            )
        )
        sequence += 1
        previous_order = order_id

        attack_quantities: tuple[float, ...] = ()
        if hybrid and tick == 5:
            attack_quantities = (3_000, 2_800, 2_600)
            for attack_index, (price, quantity) in enumerate(
                zip((99.99, 99.98, 99.97), attack_quantities, strict=True),
                1,
            ):
                events.append(
                    AddOrderEvent(
                        event_id=f"syn-add-{attack_index}",
                        sequence=sequence,
                        source="simulation",
                        source_sequence=attack_index,
                        symbol="SPY",
                        venue="LOBSTER",
                        tick=tick,
                        exchange_timestamp_ns=timestamp_ns,
                        scenario_id="layering-test",
                        scenario_name="Layering test",
                        scenario_family="layering",
                        order_id=f"SYN:42:{attack_index}",
                        agent_id="SYN:attacker",
                        side="buy",
                        price=price,
                        quantity=quantity,
                        owner="attacker",
                    )
                )
                sequence += 1
        if hybrid and tick == 6:
            for attack_index, (price, quantity) in enumerate(
                zip((99.99, 99.98, 99.97), (3_000, 2_800, 2_600), strict=True),
                1,
            ):
                events.append(
                    CancelOrderEvent(
                        event_id=f"syn-cancel-{attack_index}",
                        sequence=sequence,
                        source="simulation",
                        source_sequence=3 + attack_index,
                        symbol="SPY",
                        venue="LOBSTER",
                        tick=tick,
                        exchange_timestamp_ns=timestamp_ns,
                        scenario_id="layering-test",
                        scenario_name="Layering test",
                        scenario_family="layering",
                        order_id=f"SYN:42:{attack_index}",
                        agent_id="SYN:attacker",
                        side="buy",
                        price=price,
                        quantity=quantity,
                        owner="attacker",
                    )
                )
                sequence += 1

        bid_quantities = (
            [500, 400 + attack_quantities[0], 350 + attack_quantities[1], attack_quantities[2]]
            if attack_quantities
            else [500, 400, 350, 300]
        )
        bids = [
            PriceLevel(price=price, quantity=quantity)
            for price, quantity in zip(
                (100.00, 99.99, 99.98, 99.97),
                bid_quantities,
                strict=True,
            )
        ]
        asks = [
            PriceLevel(price=price, quantity=quantity)
            for price, quantity in zip(
                (100.02, 100.03, 100.04, 100.05),
                (450, 425, 375, 325),
                strict=True,
            )
        ]
        events.append(
            LobSnapshotEvent(
                event_id=f"snapshot-{tick}",
                sequence=sequence,
                source="simulation",
                source_sequence=None,
                symbol="SPY",
                venue="LOBSTER",
                tick=tick,
                exchange_timestamp_ns=timestamp_ns,
                depth=4,
                book=OrderBookSnapshot(
                    bids=bids,
                    asks=asks,
                    best_bid=100,
                    best_ask=100.02,
                    mid=100.01,
                    spread=0.02,
                ),
            )
        )
        sequence += 1
    return events


def features_by_tick(rows: list[dict[str, object]]) -> dict[int, tuple[object, ...]]:
    return {int(row["tick"]): tuple(row[name] for name in FEATURE_COLUMNS) for row in rows}


def test_feature_schema_has_stable_order_types_and_config_hash() -> None:
    pipeline_config = config()
    schema = feature_arrow_schema(pipeline_config.config_hash())

    assert schema.names == [*METADATA_COLUMNS, *FEATURE_COLUMNS]
    assert schema.field("prediction_timestamp_ns").type == pa.int64()
    assert schema.field("label").type == pa.int8()
    assert all(schema.field(name).type == pa.float64() for name in FEATURE_COLUMNS)
    assert schema.metadata[b"feature_config_hash"].decode() == pipeline_config.config_hash()
    assert (
        pipeline_config.config_hash()
        == FeaturePipelineConfig.model_validate(pipeline_config.model_dump()).config_hash()
    )


def test_future_events_cannot_change_past_rows_and_pipeline_reuse_is_clean() -> None:
    events = canonical_stream()
    cutoff_index = next(
        index for index, event in enumerate(events) if event.tick == 8 and isinstance(event, LobSnapshotEvent)
    )
    prefix = events[: cutoff_index + 1]
    pipeline = FeaturePipeline(config(), metadata())

    prefix_result = pipeline.generate(prefix)
    full_result = pipeline.generate(events)
    repeated_result = pipeline.generate(events)

    expected_prefix = [row for row in full_result.rows if row["tick"] <= 8]
    assert prefix_result.rows == expected_prefix
    assert repeated_result.rows == full_result.rows
    assert repeated_result.input_sha256 == full_result.input_sha256


def test_labels_and_synthetic_metadata_never_enter_feature_calculation() -> None:
    events = canonical_stream(hybrid=True)
    contaminated = [
        replace(
            event,
            scenario_id="hidden-label",
            scenario_name="Do not expose",
            scenario_family="spoofing",
        )
        for event in events
    ]
    positive_labels = LabelSpec(labels=[LabelWindow(attack_family="layering", start_tick=5, end_tick=6)])
    clean = FeaturePipeline(config(), metadata(source_type="hybrid")).generate(events)
    labeled = FeaturePipeline(
        config(),
        metadata(source_type="hybrid"),
        positive_labels,
    ).generate(contaminated)

    assert features_by_tick(clean.rows) == features_by_tick(labeled.rows)
    assert all(row["label"] is None for row in clean.rows)
    assert [row["label"] for row in labeled.rows if 5 <= row["tick"] <= 6] == [1, 1]
    assert not any(field in FEATURE_COLUMNS for field in ("scenario_id", "scenario_name", "scenario_family", "label"))


def test_explicit_negative_windows_are_typed_bounded_and_do_not_change_features() -> None:
    events = canonical_stream()
    labels = LabelSpec(
        labels=[
            LabelWindow(
                label=0,
                attack_family=None,
                label_source="independently_verified_clean",
                provenance_id="clean-window-1",
                start_timestamp_ns=BASE_TIMESTAMP_NS + 4_000_000_000,
                end_timestamp_ns=BASE_TIMESTAMP_NS + 7_000_000_000,
                end_inclusive=False,
            )
        ]
    )

    unlabeled = FeaturePipeline(config(), metadata()).generate(events)
    governed = FeaturePipeline(config(), metadata(), labels).generate(events)

    assert features_by_tick(unlabeled.rows) == features_by_tick(governed.rows)
    assert [row["label"] for row in governed.rows if 4 <= row["tick"] < 7] == [0, 0, 0]
    assert next(row for row in governed.rows if row["tick"] == 7)["label"] is None
    assert all(
        row["attack_family"] is None and row["attack_phase"] == "none"
        for row in governed.rows
        if row["label"] == 0
    )
    assert governed.input_provenance["feature_label_window_count"] == 1
    assert governed.input_provenance["feature_label_spec_sha256"] == labels.spec_hash()


def test_mixed_coordinate_ground_truth_fails_closed_when_windows_match_same_row() -> None:
    labels = LabelSpec(
        labels=[
            LabelWindow(attack_family="layering", start_tick=5, end_tick=6),
            LabelWindow(
                label=0,
                label_source="independently_verified_clean",
                provenance_id="clean-overlap",
                start_timestamp_ns=BASE_TIMESTAMP_NS + 5_000_000_000,
                end_timestamp_ns=BASE_TIMESTAMP_NS + 7_000_000_000,
                end_inclusive=False,
            ),
        ]
    )

    with pytest.raises(ValueError, match="multiple ground-truth windows"):
        assign_label(
            labels,
            tick=5,
            prediction_timestamp_ns=BASE_TIMESTAMP_NS + 5_000_000_000,
        )


def test_hybrid_changes_only_causal_windows_and_converges_to_control() -> None:
    control_events = canonical_stream()
    hybrid_events = canonical_stream(hybrid=True)
    control = FeaturePipeline(config(), metadata()).generate(control_events)
    hybrid = FeaturePipeline(config(), metadata(source_type="hybrid")).generate(hybrid_events)
    control_features = features_by_tick(control.rows)
    hybrid_features = features_by_tick(hybrid.rows)

    assert all(control_features[tick] == hybrid_features[tick] for tick in range(0, 5))
    assert any(control_features[tick] != hybrid_features[tick] for tick in range(5, 11))
    assert all(control_features[tick] == hybrid_features[tick] for tick in range(12, 16))
    assert hybrid.rows[5]["layering_score"] > control.rows[5]["layering_score"]
    assert hybrid.rows[6]["mean_cancel_lifetime_ms_short"] == pytest.approx(1_000)
    assert control.rows[1]["rapid_cancel_share_short"] == pytest.approx(1)
    assert control.rows[1]["replenishment_rate_short"] == pytest.approx(0.5)
    assert {event.event_id for event in control_events if event.source == "historical"} == {
        event.event_id for event in hybrid_events if event.source == "historical"
    }


def test_features_are_source_agnostic_and_validate_price_volume_semantics() -> None:
    historical_events = canonical_stream(ticks=4)
    synthetic_events = [
        replace(
            event,
            source="simulation",
            source_sequence=event.sequence,
            exchange_timestamp_ns=None,
        )
        for event in historical_events
    ]
    historical = FeaturePipeline(config(), metadata()).generate(historical_events)
    synthetic = FeaturePipeline(config(), metadata(source_type="synthetic")).generate(synthetic_events)

    assert features_by_tick(historical.rows) == features_by_tick(synthetic.rows)
    misaligned = list(historical_events)
    misaligned[0] = replace(misaligned[0], price=99.995)
    invalid = FeaturePipeline(config(), metadata()).generate(misaligned)
    assert invalid.rows[0]["row_valid"] is False
    assert "event price not aligned to tick size" in invalid.rows[0]["invalid_reason"]
    inconsistent = list(historical_events)
    snapshot_index = next(index for index, event in enumerate(inconsistent) if isinstance(event, LobSnapshotEvent))
    snapshot = inconsistent[snapshot_index]
    assert isinstance(snapshot, LobSnapshotEvent)
    inconsistent[snapshot_index] = replace(
        snapshot,
        book=replace(snapshot.book, mid=200),
    )
    invalid_snapshot = FeaturePipeline(config(), metadata()).generate(inconsistent)
    assert "snapshot mid inconsistent with levels" in invalid_snapshot.rows[0]["invalid_reason"]


def test_split_group_prevents_adjacent_random_splits() -> None:
    first = FeaturePipeline(config(), metadata()).generate(canonical_stream(ticks=3))
    duplicate_import = FeaturePipeline(
        config(),
        metadata(dataset_id="duplicate-import", run_id="another-run"),
    ).generate(canonical_stream(ticks=3))
    second = FeaturePipeline(
        config(),
        metadata(session_id="SPY-2012-06-21-pm"),
    ).generate(canonical_stream(ticks=3))

    assert len({row["split_group"] for row in first.rows}) == 1
    assert first.rows[0]["split_group"] == duplicate_import.rows[0]["split_group"]
    assert first.rows[0]["split_group"] != second.rows[0]["split_group"]


def test_partial_fills_are_not_reported_as_terminal_order_lifetimes() -> None:
    base = canonical_stream(ticks=1)
    add = base[0]
    snapshot = base[1]
    assert isinstance(add, AddOrderEvent)
    assert isinstance(snapshot, LobSnapshotEvent)
    first_execution = ExecuteOrderEvent(
        event_id="execution-1",
        sequence=2,
        source="historical",
        source_sequence=2,
        symbol="SPY",
        venue="LOBSTER",
        tick=1,
        exchange_timestamp_ns=BASE_TIMESTAMP_NS + 1_000_000_000,
        execution_id="HIST:execution:1",
        aggressor_order_id="HIST:market:1",
        resting_order_id=add.order_id,
        aggressor_agent_id="HIST:participant",
        resting_agent_id=add.agent_id,
        side="sell",
        price=add.price,
        quantity=50,
        aggressor_remaining_quantity=0,
        resting_remaining_quantity=50,
    )
    second_execution = replace(
        first_execution,
        event_id="execution-2",
        execution_id="HIST:execution:2",
        sequence=4,
        source_sequence=3,
        tick=2,
        exchange_timestamp_ns=BASE_TIMESTAMP_NS + 2_000_000_000,
        resting_remaining_quantity=0,
    )
    events = [
        add,
        first_execution,
        replace(
            snapshot,
            sequence=3,
            tick=1,
            exchange_timestamp_ns=BASE_TIMESTAMP_NS + 1_000_000_000,
        ),
        second_execution,
        replace(
            snapshot,
            event_id="snapshot-2",
            sequence=5,
            tick=2,
            exchange_timestamp_ns=BASE_TIMESTAMP_NS + 2_000_000_000,
        ),
    ]

    result = FeaturePipeline(config(), metadata()).generate(events)

    assert result.rows[0]["mean_order_lifetime_ms_short"] is None
    assert result.rows[1]["mean_order_lifetime_ms_short"] == pytest.approx(2_000)


def test_large_order_share_uses_large_adds_not_modification_quantity() -> None:
    base = canonical_stream(ticks=1)
    add = base[0]
    snapshot = base[1]
    assert isinstance(add, AddOrderEvent)
    assert isinstance(snapshot, LobSnapshotEvent)
    modification = ModifyOrderEvent(
        event_id="modify-1",
        sequence=2,
        source="historical",
        source_sequence=2,
        symbol="SPY",
        venue="LOBSTER",
        tick=0,
        exchange_timestamp_ns=BASE_TIMESTAMP_NS,
        order_id=add.order_id,
        agent_id=add.agent_id,
        side=add.side,
        previous_price=add.price,
        previous_quantity=add.quantity,
        price=add.price,
        quantity=2_000,
        priority_preserved=True,
    )

    result = FeaturePipeline(config(), metadata()).generate([add, modification, replace(snapshot, sequence=3)])

    assert result.rows[0]["large_order_rate_short"] == 0
    assert result.rows[0]["large_order_quantity_share_short"] == 0


def test_parquet_metadata_quality_and_fixture_cli_inputs(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    fixture = repository_root / "data" / "features" / "fixture"
    events = load_events_jsonl(fixture / "events.jsonl")
    run_metadata = load_run_metadata(fixture / "run-metadata.json")
    labels = load_labels(fixture / "labels.json")
    pipeline_config = config()
    result = FeaturePipeline(pipeline_config, run_metadata, labels).generate(events)

    manifest = write_feature_run(
        tmp_path,
        result=result,
        config=pipeline_config,
        metadata=run_metadata,
    )
    table = pq.read_table(tmp_path / "features.parquet")

    assert table.schema.names == [*METADATA_COLUMNS, *FEATURE_COLUMNS]
    assert table.schema.metadata[b"feature_schema_version"] == b"lob_features_v1"
    assert manifest["input"]["canonical_event_stream_sha256"] == result.input_sha256
    assert manifest["input"]["source_event_counts"] == {
        "historical": 4,
        "simulation": 11,
    }
    assert manifest["input"]["event_type_counts"]["snapshot"] == 5
    assert manifest["input"]["feature_checkpoint_count"] == 5
    assert manifest["output"]["row_count"] == 5
    assert result.quality_report["class_balance"] == {
        "positive": 2,
        "negative": 0,
        "unlabeled": 3,
        "attack_family_rows": {"layering": 2},
    }
    assert result.quality_report["invalid_row_count"] == 0
    assert result.quality_report["missing_values"]["log_return_1"] == 1
    assert result.quality_report["distributions"]["spread"]["count"] == 5
    assert [row["attack_phase"] for row in result.rows] == [
        None,
        None,
        "placement",
        "cancellation",
        None,
    ]
    assert (tmp_path / "feature-quality.json").is_file()
    assert (tmp_path / "run-metadata.json").is_file()
    repeated_dir = tmp_path / "repeated"
    repeated_manifest = write_feature_run(
        repeated_dir,
        result=result,
        config=pipeline_config,
        metadata=run_metadata,
    )
    assert repeated_manifest["output"]["feature_file_sha256"] == manifest["output"]["feature_file_sha256"]
    with pytest.raises(ValueError, match="already exists"):
        write_feature_run(
            tmp_path,
            result=result,
            config=pipeline_config,
            metadata=run_metadata,
        )


def test_cli_generates_fixture_artifacts(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    fixture = repository_root / "data" / "features" / "fixture"

    exit_code = generate_features(
        [
            "--events",
            str(fixture / "events.jsonl"),
            "--metadata",
            str(fixture / "run-metadata.json"),
            "--labels",
            str(fixture / "labels.json"),
            "--config",
            str(repository_root / "configs" / "features" / "lightgbm-v1.json"),
            "--output",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert pq.read_table(tmp_path / "features.parquet").num_rows == 5


def test_java_event_endpoint_pagination_is_strict_and_deterministic(monkeypatch) -> None:
    expected = canonical_stream(ticks=1)
    pages = iter(
        (
            {
                "events": [expected[0].to_dict()],
                "next_after_sequence": 1,
                "has_more": True,
            },
            {
                "events": [expected[1].to_dict()],
                "next_after_sequence": 2,
                "has_more": False,
            },
        )
    )
    requested_urls: list[str] = []

    def urlopen(url: str, timeout: float) -> BytesIO:
        requested_urls.append(url)
        assert timeout == 5
        return BytesIO(json.dumps(next(pages)).encode("utf-8"))

    monkeypatch.setattr("app.features.io.urllib.request.urlopen", urlopen)

    actual = fetch_events(
        "http://java:8081/api/arena/exchange-events",
        page_size=1,
        timeout=5,
    )

    assert actual == expected
    assert "afterSequence=0&limit=1" in requested_urls[0]
    assert "afterSequence=1&limit=1" in requested_urls[1]
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        fetch_events("file:///tmp/events.json")


def test_historical_source_snapshots_are_validated_but_not_prediction_rows() -> None:
    base = canonical_stream(ticks=1)
    add = base[0]
    checkpoint = base[1]
    assert isinstance(checkpoint, LobSnapshotEvent)
    source_snapshot = replace(
        checkpoint,
        event_id="historical-source-snapshot",
        sequence=2,
        source="historical",
        source_sequence=1,
        book=replace(checkpoint.book, mid=200),
    )

    result = FeaturePipeline(config(), metadata()).generate([add, source_snapshot, replace(checkpoint, sequence=3)])

    assert len(result.rows) == 1
    assert result.input_provenance["historical_source_snapshot_count"] == 1
    assert "historical source snapshot: snapshot mid inconsistent" in result.rows[0]["invalid_reason"]


def test_native_scenario_jsonl_and_unlabeled_control_are_supported(tmp_path: Path) -> None:
    label_path = tmp_path / "scenario_labels.jsonl"
    labels = [
        {
            "schema_version": "scenario_ground_truth_v1",
            "scenario_family": "spoofing_like_wall",
            "source": "synthetic_scenario",
            "has_attack": True,
            "start_tick": 2,
            "end_tick": 4,
            "phase_windows": {
                "pressure_phase": {"start_tick": 2, "end_tick": 3},
                "cancellation_phase": {"start_tick": 4, "end_tick": 4},
            },
        },
        {
            "schema_version": "scenario_ground_truth_v1",
            "scenario_family": "layering_like",
            "source": "synthetic_scenario",
            "has_attack": True,
            "start_tick": 8,
            "end_tick": 9,
        },
    ]
    label_path.write_text(
        "\n".join(json.dumps(item) for item in labels) + "\n",
        encoding="utf-8",
    )
    control_path = tmp_path / "control.json"
    control_path.write_text('{"ground_truth": null}\n', encoding="utf-8")

    loaded = load_labels(label_path)

    assert [window.attack_family for window in loaded.labels] == [
        "spoofing_like_wall",
        "layering_like",
    ]
    assert loaded.labels[0].phases["cancellation_phase"] == (4, 4)
    assert load_labels(control_path) == LabelSpec()


def test_ground_truth_and_artifact_contracts_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        LabelSpec(
            labels=[
                LabelWindow(attack_family="spoofing", start_tick=2, end_tick=4),
                LabelWindow(attack_family="layering", start_tick=4, end_tick=6),
            ]
        )
    with pytest.raises(ValueError, match="within the label tick range"):
        LabelWindow(
            attack_family="spoofing",
            start_tick=2,
            end_tick=4,
            phases={"invalid": (1, 3)},
        )
    with pytest.raises(ValueError, match="finite number"):
        FeatureRunMetadata(
            run_id="invalid",
            source_type="lobster",
            instrument="SPY",
            venue="LOBSTER",
            session_id="session",
            session_date=date(2012, 6, 21),
            price_tick_size=float("inf"),
            quantity_lot_size=1,
        )

    malformed_labels = tmp_path / "malformed-labels.json"
    malformed_labels.write_text(
        json.dumps(
            {
                "scenario_family": "spoofing",
                "has_attack": "yes",
                "start_tick": 2,
                "end_tick": 4,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="has_attack must be a boolean"):
        load_labels(malformed_labels)

    pipeline_config = config()
    run_metadata = metadata()
    result = FeaturePipeline(pipeline_config, run_metadata).generate(canonical_stream(ticks=2))
    changed_config = pipeline_config.model_copy(update={"large_order_quantity": 2_000})
    with pytest.raises(ValueError, match="feature_config_hash"):
        write_feature_run(
            tmp_path / "wrong-config",
            result=result,
            config=changed_config,
            metadata=run_metadata,
        )
    with pytest.raises(ValueError, match="run_id"):
        write_feature_run(
            tmp_path / "wrong-run",
            result=result,
            config=pipeline_config,
            metadata=metadata(run_id="different-run"),
        )
    locked_output = tmp_path / "locked"
    locked_output.mkdir()
    (locked_output / ".feature-write.lock").mkdir()
    with pytest.raises(ValueError, match="locked by another writer"):
        write_feature_run(
            locked_output,
            result=result,
            config=pipeline_config,
            metadata=run_metadata,
        )


def test_ordering_and_window_configuration_fail_closed() -> None:
    events = canonical_stream(ticks=2)
    with pytest.raises(ValueError, match="strictly increasing"):
        FeaturePipeline(config(), metadata()).generate([events[0], events[2], events[1]])
    with pytest.raises(ValueError, match="at least one"):
        FeaturePipeline(config(), metadata()).generate([])
    truncated = [replace(event, sequence=event.sequence + 10) for event in events]
    with pytest.raises(ValueError, match="start at sequence 1"):
        FeaturePipeline(config(), metadata()).generate(truncated)
    gap = list(events)
    gap[1] = replace(gap[1], sequence=3)
    with pytest.raises(ValueError, match="contiguous"):
        FeaturePipeline(config(), metadata()).generate(gap)
    duplicate_id = list(events)
    duplicate_id[1] = replace(duplicate_id[1], event_id=duplicate_id[0].event_id)
    with pytest.raises(ValueError, match="IDs must be unique"):
        FeaturePipeline(config(), metadata()).generate(duplicate_id)
    regressing = list(events)
    regressing[1] = replace(regressing[1], exchange_timestamp_ns=BASE_TIMESTAMP_NS - 1)
    with pytest.raises(ValueError, match="timestamps must not regress"):
        FeaturePipeline(config(), metadata()).generate(regressing)
    tick_regression = canonical_stream(ticks=3)
    tick_regression[-2] = replace(tick_regression[-2], tick=0)
    with pytest.raises(ValueError, match="ticks must not regress"):
        FeaturePipeline(config(), metadata()).generate(tick_regression)
    missing_tick = list(events)
    snapshot_index = next(index for index, event in enumerate(missing_tick) if isinstance(event, LobSnapshotEvent))
    missing_tick[snapshot_index] = replace(missing_tick[snapshot_index], tick=None)
    with pytest.raises(ValueError, match="snapshot events require a tick"):
        FeaturePipeline(config(), metadata()).generate(missing_tick)
    with pytest.raises(ValueError, match="must not exceed"):
        FeaturePipelineConfig(
            short_window_ns=10,
            long_window_ns=20,
            rapid_cancel_ns=21,
        )
