import json
import tracemalloc
from dataclasses import replace
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from app.features.io import (
    iter_events_jsonl,
    load_config,
    load_events_jsonl,
    load_labels,
    load_run_metadata,
)
from app.features.pipeline import FEATURE_COLUMNS, FeaturePipeline
from app.features.streaming import (
    StreamingQualityAccumulator,
    write_streaming_feature_run,
)
from app.exchange.stream_validation import DiskBackedUniqueIds
from scripts.benchmark_feature_streaming import main as benchmark_features
from scripts.generate_features import main as generate_features


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "features" / "fixture"
CONFIG = ROOT / "configs" / "features" / "lightgbm-v1.json"


def _inputs():
    config = load_config(CONFIG)
    metadata = load_run_metadata(FIXTURE / "run-metadata.json")
    labels = load_labels(FIXTURE / "labels.json")
    return config, metadata, labels


def test_streaming_rows_match_in_memory_pipeline_and_use_bounded_row_groups(tmp_path: Path) -> None:
    config, metadata, labels = _inputs()
    events = load_events_jsonl(FIXTURE / "events.jsonl")
    expected = FeaturePipeline(config, metadata, labels).generate(events)

    manifest = write_streaming_feature_run(
        tmp_path,
        events=iter_events_jsonl(FIXTURE / "events.jsonl"),
        pipeline=FeaturePipeline(config, metadata, labels),
        config=config,
        metadata=metadata,
        row_group_size=2,
        quantile_sample_size=128,
    )
    table = pq.read_table(tmp_path / "features.parquet")
    quality = json.loads((tmp_path / "feature-quality.json").read_text())

    assert table.to_pylist() == expected.rows
    assert pq.ParquetFile(tmp_path / "features.parquet").metadata.num_row_groups == 3
    assert manifest["input"]["canonical_event_stream_sha256"] == expected.input_sha256
    assert manifest["output"]["row_count"] == len(expected.rows)
    assert quality["invalid_row_count"] == expected.quality_report["invalid_row_count"]
    assert quality["missing_values"] == expected.quality_report["missing_values"]
    assert quality["class_balance"] == expected.quality_report["class_balance"]
    assert quality["quantiles"]["maximum_retained_per_feature"] <= 128


def test_logical_output_is_chunk_and_row_group_invariant(tmp_path: Path) -> None:
    config, metadata, labels = _inputs()
    events = load_events_jsonl(FIXTURE / "events.jsonl")
    first = write_streaming_feature_run(
        tmp_path / "one",
        events=(event for event in events),
        pipeline=FeaturePipeline(config, metadata, labels),
        config=config,
        metadata=metadata,
        row_group_size=1,
        quantile_sample_size=128,
    )
    second = write_streaming_feature_run(
        tmp_path / "four",
        events=iter(events),
        pipeline=FeaturePipeline(config, metadata, labels),
        config=config,
        metadata=metadata,
        row_group_size=4,
        quantile_sample_size=128,
    )

    assert first["output"]["logical_feature_rows_sha256"] == second["output"]["logical_feature_rows_sha256"]
    assert first["input"]["canonical_event_stream_sha256"] == second["input"]["canonical_event_stream_sha256"]
    assert pq.read_table(tmp_path / "one" / "features.parquet").to_pylist() == pq.read_table(
        tmp_path / "four" / "features.parquet"
    ).to_pylist()


def test_quality_accumulator_memory_is_bounded_by_configured_sample() -> None:
    accumulator = StreamingQualityAccumulator(sample_size=128)
    for index in range(10_000):
        row = {name: None for name in FEATURE_COLUMNS}
        row.update(
            {
                "spread": float(index),
                "row_valid": True,
                "label": None,
                "attack_family": None,
            }
        )
        accumulator.observe(row)

    report = accumulator.report()

    assert report["row_count"] == 10_000
    assert report["distributions"]["spread"]["count"] == 10_000
    assert report["quantiles"]["maximum_retained_per_feature"] == 128


def test_whole_stream_event_id_uniqueness_uses_bounded_process_memory() -> None:
    tracemalloc.start()
    with DiskBackedUniqueIds() as unique_ids:
        for index in range(50_000):
            unique_ids.add(f"event-{index}")
        _, peak = tracemalloc.get_traced_memory()
        with pytest.raises(ValueError, match="IDs must be unique"):
            unique_ids.add("event-1")
    tracemalloc.stop()

    assert peak < 8 * 1024 * 1024
    assert not unique_ids.path.exists()


def test_late_stream_validation_failure_does_not_publish_partial_artifacts(tmp_path: Path) -> None:
    config, metadata, labels = _inputs()
    events = load_events_jsonl(FIXTURE / "events.jsonl")
    events[-1] = replace(events[-1], sequence=events[-1].sequence + 1)

    with pytest.raises(ValueError, match="contiguous"):
        write_streaming_feature_run(
            tmp_path,
            events=iter(events),
            pipeline=FeaturePipeline(config, metadata, labels),
            config=config,
            metadata=metadata,
            row_group_size=1,
            quantile_sample_size=128,
        )

    assert not (tmp_path / "features.parquet").exists()
    assert not (tmp_path / "run-metadata.json").exists()
    assert not (tmp_path / ".feature-write.lock").exists()


def test_expected_full_stream_count_rejects_truncated_input() -> None:
    config, metadata, labels = _inputs()
    events = load_events_jsonl(FIXTURE / "events.jsonl")

    with pytest.raises(ValueError, match="expected full stream"):
        FeaturePipeline(
            config,
            metadata,
            labels,
            expected_event_count=len(events) + 1,
        ).generate(events)


def test_streaming_cli_generates_fixture_without_materializing_feature_rows(tmp_path: Path) -> None:
    result = generate_features(
        [
            "--events",
            str(FIXTURE / "events.jsonl"),
            "--metadata",
            str(FIXTURE / "run-metadata.json"),
            "--labels",
            str(FIXTURE / "labels.json"),
            "--config",
            str(CONFIG),
            "--output",
            str(tmp_path),
            "--streaming",
            "--row-group-size",
            "2",
            "--quantile-sample-size",
            "128",
        ]
    )

    assert result == 0
    assert pq.ParquetFile(tmp_path / "features.parquet").metadata.num_rows == 5


def test_streaming_benchmark_proves_row_group_logical_equivalence(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "streaming-report.json"

    result = benchmark_features(
        [
            "--events",
            str(FIXTURE / "events.jsonl"),
            "--metadata",
            str(FIXTURE / "run-metadata.json"),
            "--labels",
            str(FIXTURE / "labels.json"),
            "--config",
            str(CONFIG),
            "--output",
            str(tmp_path / "primary"),
            "--comparison-output",
            str(tmp_path / "comparison"),
            "--report",
            str(report_path),
            "--row-group-size",
            "2",
            "--comparison-row-group-size",
            "3",
        ]
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result == 0
    assert report["schema_version"] == "feature_streaming_benchmark_v2"
    assert report["verdict"] == "pass"
    assert report["full_session"] is False
    assert len(set(report["logical_hashes_by_chunk_size"].values())) == 1
