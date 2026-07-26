from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Literal

import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.corpus.governance import ArtifactReference, GovernedSession, SHA256_PATTERN
from app.contracts.generated.lob.exchange.v1 import exchange_pb2
from app.contracts.hashing import advance_stream_hash, event_hash, initial_stream_hash
from app.exchange.schemas import (
    AddOrderEvent,
    CancelOrderEvent,
    CanonicalExchangeEvent,
    ExecuteOrderEvent,
    LobSnapshotEvent,
    ModifyOrderEvent,
)
from app.exchange.stream_validation import DiskBackedUniqueIds
from app.features.io import iter_events_jsonl, load_labels
from app.features.models import FeatureRunMetadata, LabelSpec


REPLAY_BUNDLE_SCHEMA_VERSION = "canonical_java_replay_bundle_v1"


class CanonicalJavaReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["canonical_java_replay_bundle_v1"] = REPLAY_BUNDLE_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    base_session_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    mode: Literal["historical_control", "synthetic", "hybrid"]
    campaign_id: str | None = None
    attack_family: str | None = None
    instrument: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    session_date: date
    seed: int | None = Field(default=None, ge=0)
    price_tick_size: float = Field(gt=0, allow_inf_nan=False)
    quantity_lot_size: float = Field(gt=0, allow_inf_nan=False)
    tick_interval_ns: int = Field(gt=0)
    java_engine_version: str = Field(min_length=1)
    canonical_event_schema_version: int = Field(default=1, ge=1)
    canonical_event_stream_hash: str = Field(pattern=SHA256_PATTERN)
    event_count: int = Field(ge=1)
    snapshot_count: int = Field(ge=1)
    alert_count: int = Field(ge=0)
    label_count: int = Field(ge=0)
    first_sequence: Literal[1] = 1
    last_sequence: int = Field(ge=1)
    first_timestamp_ns: int = Field(ge=0)
    last_timestamp_ns: int = Field(ge=0)
    events: ArtifactReference
    snapshots: ArtifactReference
    alerts: ArtifactReference
    ground_truth: ArtifactReference | None = None
    validation: ArtifactReference

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "CanonicalJavaReplayManifest":
        if self.first_timestamp_ns > self.last_timestamp_ns:
            raise ValueError("replay timestamp range is inverted")
        if self.last_sequence != self.event_count:
            raise ValueError("last sequence must equal event count for a complete canonical stream")
        if self.mode == "historical_control":
            if (
                self.campaign_id is not None
                or self.attack_family is not None
                or self.seed is not None
                or self.ground_truth is not None
                or self.label_count != 0
            ):
                raise ValueError("historical control bundles cannot contain synthetic campaign ground truth")
        elif (
            not self.campaign_id
            or not self.attack_family
            or self.seed is None
            or self.ground_truth is None
            or self.label_count != 1
        ):
            raise ValueError("synthetic and hybrid bundles require campaign ground truth")
        return self


@dataclass(frozen=True)
class CanonicalEvaluationInput:
    manifest: CanonicalJavaReplayManifest
    events: list[CanonicalExchangeEvent]
    labels: LabelSpec
    alerts: list[dict[str, Any]]
    feature_input_sha256: str

    def feature_metadata(self) -> FeatureRunMetadata:
        source_type = {
            "historical_control": "lobster",
            "synthetic": "synthetic",
            "hybrid": "hybrid",
        }[self.manifest.mode]
        return FeatureRunMetadata(
            run_id=self.manifest.run_id,
            dataset_id=self.manifest.dataset_id,
            source_type=source_type,
            instrument=self.manifest.instrument,
            venue=self.manifest.venue,
            session_id=self.manifest.session_id,
            session_date=self.manifest.session_date,
            seed=self.manifest.seed,
            price_tick_size=self.manifest.price_tick_size,
            quantity_lot_size=self.manifest.quantity_lot_size,
            tick_interval_ns=self.manifest.tick_interval_ns,
        )


@dataclass(frozen=True)
class CanonicalEvaluationStream:
    manifest: CanonicalJavaReplayManifest
    event_path: Path
    labels: LabelSpec
    alerts: list[dict[str, Any]]

    def iter_events(self) -> Iterator[CanonicalExchangeEvent]:
        return _iter_validated_events(self.event_path, self.manifest)

    def feature_metadata(self) -> FeatureRunMetadata:
        source_type = {
            "historical_control": "lobster",
            "synthetic": "synthetic",
            "hybrid": "hybrid",
        }[self.manifest.mode]
        return FeatureRunMetadata(
            run_id=self.manifest.run_id,
            dataset_id=self.manifest.dataset_id,
            source_type=source_type,
            instrument=self.manifest.instrument,
            venue=self.manifest.venue,
            session_id=self.manifest.session_id,
            session_date=self.manifest.session_date,
            seed=self.manifest.seed,
            price_tick_size=self.manifest.price_tick_size,
            quantity_lot_size=self.manifest.quantity_lot_size,
            tick_interval_ns=self.manifest.tick_interval_ns,
        )


def load_canonical_evaluation_input(
    manifest_path: Path,
    *,
    artifact_root: Path | None = None,
) -> CanonicalEvaluationInput:
    stream = open_canonical_evaluation_stream(manifest_path, artifact_root=artifact_root)
    events = list(stream.iter_events())
    return CanonicalEvaluationInput(
        manifest=stream.manifest,
        events=events,
        labels=stream.labels,
        alerts=stream.alerts,
        feature_input_sha256=_feature_input_hash(events),
    )


def open_canonical_evaluation_stream(
    manifest_path: Path,
    *,
    artifact_root: Path | None = None,
) -> CanonicalEvaluationStream:
    manifest = CanonicalJavaReplayManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    root = (artifact_root or manifest_path.parent).resolve()
    resolved = {
        name: _verify_and_resolve(reference, root)
        for name, reference in (
            ("events", manifest.events),
            ("snapshots", manifest.snapshots),
            ("alerts", manifest.alerts),
            ("validation", manifest.validation),
        )
    }
    ground_truth_path = (
        _verify_and_resolve(manifest.ground_truth, root)
        if manifest.ground_truth is not None
        else None
    )
    _validate_snapshots(resolved["snapshots"], manifest)
    alerts = _load_identity_jsonl(
        resolved["alerts"],
        run_id=manifest.run_id,
        campaign_id=manifest.campaign_id,
        expected_count=manifest.alert_count,
        artifact_name="alerts",
    )
    ground_truth_rows: list[dict[str, Any]] = []
    if ground_truth_path is not None:
        ground_truth_rows = _load_identity_jsonl(
            ground_truth_path,
            run_id=manifest.run_id,
            campaign_id=manifest.campaign_id,
            expected_count=manifest.label_count,
            artifact_name="ground truth",
        )
    labels = load_labels(ground_truth_path) if ground_truth_path is not None else LabelSpec()
    if manifest.mode != "historical_control":
        if (
            len(labels.labels) != manifest.label_count
            or len(ground_truth_rows) != manifest.label_count
            or any(window.label != 1 for window in labels.labels)
            or any(window.attack_family != manifest.attack_family for window in labels.labels)
        ):
            raise ValueError("canonical attack ground truth does not match replay manifest")
    _validate_validation_report(resolved["validation"], manifest)
    return CanonicalEvaluationStream(
        manifest=manifest,
        event_path=resolved["events"],
        labels=labels,
        alerts=alerts,
    )


def bind_replay_manifest_to_corpus_session(
    replay: CanonicalJavaReplayManifest,
    session: GovernedSession,
) -> None:
    if (
        replay.base_session_id != session.base_session_id
        or replay.dataset_id != session.dataset_id
        or replay.instrument != session.instrument
        or replay.venue != session.venue
        or replay.session_id != session.session_id
        or replay.session_date != session.session_date
    ):
        raise ValueError("canonical replay identity does not match governed corpus session")
    if replay.mode == "historical_control":
        if replay.events.sha256 != session.canonical_control_events.sha256:
            raise ValueError("historical control event artifact is not bound to the governed corpus")
        if replay.validation.sha256 != session.control_validation.sha256:
            raise ValueError("historical control validation is not bound to the governed corpus")
        return
    campaigns = {
        campaign.campaign_id: campaign
        for campaign in session.campaigns
    }
    campaign = campaigns.get(replay.campaign_id or "")
    if campaign is None:
        raise ValueError("canonical replay campaign is not registered in the governed corpus")
    if (
        replay.events.sha256 != campaign.canonical_events.sha256
        or replay.ground_truth is None
        or replay.ground_truth.sha256 != campaign.ground_truth.sha256
        or replay.validation.sha256 != campaign.validation.sha256
        or replay.seed != campaign.derived_seed
        or replay.attack_family != campaign.attack_family
    ):
        raise ValueError("canonical replay campaign artifacts or seed do not match governed corpus")


def _verify_and_resolve(reference: ArtifactReference, root: Path) -> Path:
    path = (root / reference.uri).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"replay artifact escapes the configured root: {reference.name}")
    if not path.is_file():
        raise ValueError(f"replay artifact is missing: {reference.name}")
    if path.stat().st_size != reference.size_bytes:
        raise ValueError(f"replay artifact size mismatch: {reference.name}")
    if _sha256(path) != reference.sha256:
        raise ValueError(f"replay artifact SHA-256 mismatch: {reference.name}")
    return path


def _validate_events(
    events: list[CanonicalExchangeEvent],
    manifest: CanonicalJavaReplayManifest,
) -> None:
    if len(events) != manifest.event_count:
        raise ValueError("canonical event count does not match replay manifest")
    previous_timestamp = -1
    with DiskBackedUniqueIds() as event_ids:
        for expected_sequence, event in enumerate(events, 1):
            if event.sequence != expected_sequence:
                raise ValueError("canonical Java event sequences must be complete and contiguous")
            if event.schema_version != manifest.canonical_event_schema_version:
                raise ValueError("canonical Java event schema version does not match replay manifest")
            event_ids.add(event.event_id)
            if event.symbol != manifest.instrument or event.venue != manifest.venue:
                raise ValueError("canonical Java event identity does not match replay manifest")
            timestamp = event.exchange_timestamp_ns
            if timestamp is None:
                timestamp = event.received_timestamp_ns
            if timestamp is None or timestamp < previous_timestamp:
                raise ValueError("canonical Java event timestamps must be present and non-regressing")
            previous_timestamp = timestamp
    first_timestamp = _event_timestamp(events[0])
    last_timestamp = _event_timestamp(events[-1])
    if (
        first_timestamp != manifest.first_timestamp_ns
        or last_timestamp != manifest.last_timestamp_ns
    ):
        raise ValueError("canonical event timestamp bounds do not match replay manifest")
    observed_snapshots = sum(isinstance(event, LobSnapshotEvent) for event in events)
    if observed_snapshots != manifest.snapshot_count:
        raise ValueError("canonical snapshot count does not match replay manifest")


def _iter_validated_events(
    path: Path,
    manifest: CanonicalJavaReplayManifest,
) -> Iterator[CanonicalExchangeEvent]:
    count = 0
    snapshot_count = 0
    previous_timestamp = -1
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    stream_digest = initial_stream_hash(manifest.canonical_event_schema_version)
    with DiskBackedUniqueIds() as event_ids:
        for event in iter_events_jsonl(path):
            count += 1
            if event.sequence != count:
                raise ValueError("canonical Java event sequences must be complete and contiguous")
            if event.schema_version != manifest.canonical_event_schema_version:
                raise ValueError("canonical Java event schema version does not match replay manifest")
            event_ids.add(event.event_id)
            if event.symbol != manifest.instrument or event.venue != manifest.venue:
                raise ValueError("canonical Java event identity does not match replay manifest")
            timestamp = _event_timestamp(event)
            if timestamp < previous_timestamp:
                raise ValueError("canonical Java event timestamps must be present and non-regressing")
            if first_timestamp is None:
                first_timestamp = timestamp
            last_timestamp = timestamp
            previous_timestamp = timestamp
            stream_digest = advance_stream_hash(
                stream_digest,
                event_hash(
                    _canonical_proto_event(
                        event,
                        price_tick_size=manifest.price_tick_size,
                        quantity_lot_size=manifest.quantity_lot_size,
                    )
                ),
            )
            if isinstance(event, LobSnapshotEvent):
                snapshot_count += 1
            yield event
    if count != manifest.event_count:
        raise ValueError("canonical event count does not match replay manifest")
    if snapshot_count != manifest.snapshot_count:
        raise ValueError("canonical snapshot count does not match replay manifest")
    if (
        first_timestamp != manifest.first_timestamp_ns
        or last_timestamp != manifest.last_timestamp_ns
    ):
        raise ValueError("canonical event timestamp bounds do not match replay manifest")
    if stream_digest.hex() != manifest.canonical_event_stream_hash:
        raise ValueError("canonical Java event stream hash does not match replay events")


def _validate_snapshots(path: Path, manifest: CanonicalJavaReplayManifest) -> None:
    try:
        row_count = pq.ParquetFile(path).metadata.num_rows
    except (OSError, ValueError) as exception:
        raise ValueError(f"invalid canonical Java snapshot Parquet: {exception}") from exception
    if row_count != manifest.snapshot_count:
        raise ValueError("snapshot Parquet row count does not match replay manifest")


def _load_identity_jsonl(
    path: Path,
    *,
    run_id: str,
    campaign_id: str | None,
    expected_count: int,
    artifact_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exception:
            raise ValueError(f"invalid {artifact_name} JSONL at line {line_number}") from exception
        if not isinstance(payload, dict):
            raise ValueError(f"{artifact_name} records must be JSON objects")
        if payload.get("run_id") != run_id:
            raise ValueError(f"{artifact_name} run identity does not match replay manifest")
        if campaign_id is not None and payload.get("campaign_id") != campaign_id:
            raise ValueError(f"{artifact_name} campaign identity does not match replay manifest")
        rows.append(payload)
    if len(rows) != expected_count:
        raise ValueError(f"{artifact_name} count does not match replay manifest")
    return rows


def _validate_validation_report(path: Path, manifest: CanonicalJavaReplayManifest) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exception:
        raise ValueError("canonical replay validation report is invalid JSON") from exception
    if not isinstance(payload, dict) or payload.get("verdict") != "pass":
        raise ValueError("canonical replay validation report must have a pass verdict")
    for field_name, expected in (
        ("run_id", manifest.run_id),
        ("base_session_id", manifest.base_session_id),
    ):
        if payload.get(field_name) != expected:
            raise ValueError(f"canonical replay validation {field_name} does not match manifest")
    observed_stream_hash = payload.get("canonical_event_stream_hash")
    if observed_stream_hash != manifest.canonical_event_stream_hash:
        raise ValueError("Java canonical event stream hash does not match validation report")


def _feature_input_hash(events: list[CanonicalExchangeEvent]) -> str:
    digest = hashlib.sha256()
    for event in events:
        digest.update(
            json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
    return digest.hexdigest()


def _event_timestamp(event: CanonicalExchangeEvent) -> int:
    value = event.exchange_timestamp_ns
    if value is None:
        value = event.received_timestamp_ns
    if value is None:
        raise ValueError("canonical event timestamp is missing")
    return value


def canonical_java_event_stream_hash(
    events: list[CanonicalExchangeEvent],
    *,
    price_tick_size: float,
    quantity_lot_size: float,
    contract_version: int = 1,
) -> str:
    digest = initial_stream_hash(contract_version)
    for event in events:
        digest = advance_stream_hash(
            digest,
            event_hash(
                _canonical_proto_event(
                    event,
                    price_tick_size=price_tick_size,
                    quantity_lot_size=quantity_lot_size,
                )
            ),
        )
    return digest.hex()


def _canonical_proto_event(
    event: CanonicalExchangeEvent,
    *,
    price_tick_size: float,
    quantity_lot_size: float,
) -> exchange_pb2.ExchangeEvent:
    if event.sequence is None:
        raise ValueError("canonical hashing requires assigned event sequences")
    metadata = exchange_pb2.EventMetadata(
        schema_version=event.schema_version,
        event_id=event.event_id,
        sequence=event.sequence,
        source=(
            exchange_pb2.EVENT_SOURCE_SIMULATION
            if event.source == "simulation"
            else exchange_pb2.EVENT_SOURCE_HISTORICAL
        ),
        symbol=event.symbol,
        venue=event.venue,
    )
    for name in (
        "source_sequence",
        "tick",
        "exchange_timestamp_ns",
        "received_timestamp_ns",
        "scenario_id",
        "scenario_name",
        "scenario_family",
    ):
        value = getattr(event, name)
        if value is not None:
            setattr(metadata, name, value)
    proto = exchange_pb2.ExchangeEvent(metadata=metadata)

    def side(value: str) -> int:
        return exchange_pb2.SIDE_BUY if value == "buy" else exchange_pb2.SIDE_SELL

    if isinstance(event, AddOrderEvent):
        proto.add.CopyFrom(
            exchange_pb2.AddOrder(
                order_id=event.order_id,
                agent_id=event.agent_id,
                side=side(event.side),
                price_ticks=_scaled_int(event.price, price_tick_size),
                quantity_lots=_scaled_int(event.quantity, quantity_lot_size),
                owner=event.owner,
            )
        )
    elif isinstance(event, ModifyOrderEvent):
        proto.modify.CopyFrom(
            exchange_pb2.ModifyOrder(
                order_id=event.order_id,
                agent_id=event.agent_id,
                side=side(event.side),
                previous_price_ticks=_scaled_int(event.previous_price, price_tick_size),
                previous_quantity_lots=_scaled_int(event.previous_quantity, quantity_lot_size),
                price_ticks=_scaled_int(event.price, price_tick_size),
                quantity_lots=_scaled_int(event.quantity, quantity_lot_size),
                priority_preserved=event.priority_preserved,
                owner=event.owner,
            )
        )
    elif isinstance(event, CancelOrderEvent):
        proto.cancel.CopyFrom(
            exchange_pb2.CancelOrder(
                order_id=event.order_id,
                agent_id=event.agent_id,
                side=side(event.side),
                price_ticks=_scaled_int(event.price, price_tick_size),
                quantity_lots=_scaled_int(event.quantity, quantity_lot_size),
                owner=event.owner,
            )
        )
    elif isinstance(event, ExecuteOrderEvent):
        proto.execute.CopyFrom(
            exchange_pb2.ExecuteOrder(
                execution_id=event.execution_id,
                aggressor_order_id=event.aggressor_order_id,
                resting_order_id=event.resting_order_id,
                aggressor_agent_id=event.aggressor_agent_id,
                resting_agent_id=event.resting_agent_id,
                aggressor_side=side(event.side),
                price_ticks=_scaled_int(event.price, price_tick_size),
                quantity_lots=_scaled_int(event.quantity, quantity_lot_size),
                aggressor_remaining_quantity_lots=_scaled_int(
                    event.aggressor_remaining_quantity,
                    quantity_lot_size,
                ),
                resting_remaining_quantity_lots=_scaled_int(
                    event.resting_remaining_quantity,
                    quantity_lot_size,
                ),
            )
        )
    elif isinstance(event, LobSnapshotEvent):
        book = exchange_pb2.BookSnapshot()
        for level in event.book.bids:
            item = book.bids.add(
                price_ticks=_scaled_int(level.price, price_tick_size),
                quantity_lots=_scaled_int(level.quantity, quantity_lot_size),
            )
            if level.owner is not None:
                item.owner = level.owner
        for level in event.book.asks:
            item = book.asks.add(
                price_ticks=_scaled_int(level.price, price_tick_size),
                quantity_lots=_scaled_int(level.quantity, quantity_lot_size),
            )
            if level.owner is not None:
                item.owner = level.owner
        if event.book.best_bid is not None:
            book.best_bid_ticks = _scaled_int(event.book.best_bid, price_tick_size)
        if event.book.best_ask is not None:
            book.best_ask_ticks = _scaled_int(event.book.best_ask, price_tick_size)
        if event.book.mid is not None:
            book.mid_price_ticks_x2 = _scaled_int(event.book.mid * 2, price_tick_size)
        if event.book.spread is not None:
            book.spread_ticks = _scaled_int(event.book.spread, price_tick_size)
        proto.snapshot.CopyFrom(exchange_pb2.LobSnapshot(depth=event.depth, book=book))
    else:
        raise TypeError(f"unsupported canonical event type: {type(event).__name__}")
    return proto


def _scaled_int(value: float, unit: float) -> int:
    scaled = Decimal(str(value)) / Decimal(str(unit))
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"value {value} is not aligned to canonical unit {unit}")
    return int(integral)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
