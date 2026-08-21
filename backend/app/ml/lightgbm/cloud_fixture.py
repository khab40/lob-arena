"""Small deterministic research fixture used only by the Wave 1 local gate."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.features.io import feature_arrow_schema
from app.features.pipeline import FEATURE_COLUMNS, FEATURE_SCHEMA_V2
from app.ml.lightgbm.data import GovernedFeatureDataset, GovernedFeatureFold, GovernedFeatureShard


def fixture_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_wave1_fixture_dataset(root: Path, *, access_mode: str) -> GovernedFeatureDataset:
    if access_mode not in {"development", "final_test"}:
        raise ValueError("fixture access mode must be development or final_test")
    folds = (
        (_fold(root, "train", 1), _fold(root, "validation", 3))
        if access_mode == "development"
        else (_fold(root, "test", 5),)
    )
    return GovernedFeatureDataset(
        access_mode=access_mode,
        protocol_id="wave1-fixture-protocol",
        protocol_hash=fixture_hash("wave1-fixture-protocol"),
        corpus_id="wave1-research-fixture",
        corpus_hash=fixture_hash("wave1-research-fixture"),
        split_id="wave1-fixture-split",
        assignment_hash=fixture_hash("wave1-fixture-assignment"),
        feature_schema_version=FEATURE_SCHEMA_V2,
        feature_config_hash=fixture_hash("wave1-fixture-feature-config"),
        feature_release_id="wave1-fixture-feature-release",
        feature_release_sha256=fixture_hash("wave1-fixture-feature-release"),
        ordered_feature_columns=tuple(FEATURE_COLUMNS),
        folds=folds,
    )


def _fold(root: Path, name: str, day_offset: int) -> GovernedFeatureFold:
    shards: list[GovernedFeatureShard] = []
    for offset, session in enumerate((f"{name}-a", f"{name}-b"), day_offset):
        shards.extend(
            (
                _shard(root, fold=name, session=session, day=offset, label=0, rows=12, family=None),
                _shard(
                    root,
                    fold=name,
                    session=session,
                    day=offset,
                    label=1,
                    rows=6,
                    family="liquidity_evaporation" if offset % 2 else "layering_like",
                ),
            )
        )
    positive = sum(item.positive_row_count for item in shards)
    negative = sum(item.negative_row_count for item in shards)
    return GovernedFeatureFold(
        fold=name,
        shards=tuple(shards),
        fold_membership_hash=fixture_hash(f"{name}-membership"),
        session_count=2,
        row_count=positive + negative,
        positive_row_count=positive,
        negative_row_count=negative,
    )


def _shard(
    root: Path,
    *,
    fold: str,
    session: str,
    day: int,
    label: int,
    rows: int,
    family: str | None,
) -> GovernedFeatureShard:
    domain = family or "control"
    run_id = f"{session}-{domain}"
    path = root / "fixture-features" / fold / session / f"{domain}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pq.write_table(
            pa.Table.from_pylist(
                [
                    _row(
                        run_id=run_id,
                        base_session_id=session,
                        label=label,
                        index=index,
                        day=day,
                        family=family,
                    )
                    for index in range(rows)
                ],
                schema=feature_arrow_schema(
                    fixture_hash("wave1-fixture-feature-config"),
                    FEATURE_SCHEMA_V2,
                ),
            ),
            path,
            compression="zstd",
        )
    content = path.read_bytes()
    return GovernedFeatureShard(
        fold=fold,
        base_session_id=session,
        campaign_id=f"campaign-{session}-{domain}" if label else None,
        run_id=run_id,
        source_type="hybrid" if label else "lobster",
        feature_path=path,
        feature_uri=path.relative_to(root).as_posix(),
        feature_sha256=hashlib.sha256(content).hexdigest(),
        feature_size_bytes=len(content),
        run_metadata_path=path,
        run_metadata_sha256=hashlib.sha256(content).hexdigest(),
        total_row_count=rows,
        supervised_row_count=rows,
        positive_row_count=rows if label else 0,
        negative_row_count=0 if label else rows,
        unlabeled_row_count=0,
        feature_columns=tuple(FEATURE_COLUMNS),
    )


def _row(
    *,
    run_id: str,
    base_session_id: str,
    label: int,
    index: int,
    day: int,
    family: str | None,
) -> dict[str, object]:
    signal = (3.0 if label else -3.0) + (index % 7) * 0.03
    row: dict[str, object] = {
        "feature_schema_version": FEATURE_SCHEMA_V2,
        "feature_config_hash": fixture_hash("wave1-fixture-feature-config"),
        "run_id": run_id,
        "dataset_id": f"dataset-{base_session_id}",
        "source_type": "hybrid" if label else "lobster",
        "instrument": "SPY",
        "venue": "FIXTURE",
        "session_id": base_session_id,
        "session_date": date(2026, 1, day),
        "seed": day if label else None,
        "prediction_timestamp_ns": day * 1_000_000 + index,
        "tick": index + 1,
        "sequence": index + 1,
        "split_group": f"SPY:{base_session_id}",
        "attack_family": family,
        "attack_phase": "pressure_build" if label else "none",
        "label": label,
        "label_source": "synthetic_scenario" if label else "independently_verified_clean",
        "row_valid": True,
        "invalid_reason": None,
    }
    for feature_index, name in enumerate(FEATURE_COLUMNS):
        row[name] = signal + feature_index * 0.0001
    row["spread"] = None if index == 0 else row["spread"]
    return row
