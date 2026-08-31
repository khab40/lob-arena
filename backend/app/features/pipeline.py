from __future__ import annotations

import hashlib
import json
import math
import statistics
import struct
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

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
from app.exchange.stream_validation import DiskBackedUniqueIds
from app.features.models import (
    FeaturePipelineConfig,
    FeatureRunMetadata,
    LabelSpec,
    assign_label,
)

FEATURE_SCHEMA_V1 = "lob_features_v1"
FEATURE_SCHEMA_V2 = "lob_features_v2"
FEATURE_SCHEMA_VERSION = FEATURE_SCHEMA_V2
SUPPORTED_FEATURE_SCHEMA_VERSIONS = frozenset(
    {FEATURE_SCHEMA_V1, FEATURE_SCHEMA_V2}
)

FEATURE_COLUMNS = (
    "spread",
    "spread_bps",
    "mid_price",
    "microprice",
    "microprice_mid_delta_bps",
    "log_return_1",
    "mid_return_short",
    "mid_return_long",
    "bid_depth_top_n",
    "ask_depth_top_n",
    "total_depth_top_n",
    "top_level_depth",
    "level_count",
    "depth_imbalance",
    "queue_imbalance_l1",
    "message_rate_short",
    "add_rate_short",
    "cancel_rate_short",
    "trade_rate_short",
    "message_rate_long",
    "add_rate_long",
    "cancel_rate_long",
    "trade_rate_long",
    "cancel_add_ratio_short",
    "cancel_trade_ratio_short",
    "trade_add_ratio_short",
    "signed_order_flow_imbalance_short",
    "cancel_quantity_ratio_short",
    "add_volume_short",
    "cancel_volume_short",
    "trade_volume_short",
    "mean_order_lifetime_ms_short",
    "mean_cancel_lifetime_ms_short",
    "rapid_cancel_share_short",
    "large_order_rate_short",
    "large_order_quantity_share_short",
    "wall_level_count",
    "largest_level_share",
    "wall_side_imbalance",
    "layering_score",
    "replenishment_rate_short",
    "burst_message_share_short",
    "message_rate_ratio_short_long",
    "quote_stuffing_score",
    "realized_volatility_short",
    "realized_volatility_long",
    "return_volatility_ratio",
    "liquidity_score",
    "amihud_illiquidity_short",
    "spread_change_short_long",
    "depth_change_short_long",
    "imbalance_change_short_long",
    "order_flow_change_short_long",
    "spread_zscore_long",
    "depth_zscore_long",
    "imbalance_zscore_long",
    "message_rate_zscore_long",
    "return_zscore_long",
    "volatility_regime",
    "liquidity_regime",
)

METADATA_COLUMNS = (
    "feature_schema_version",
    "feature_config_hash",
    "run_id",
    "dataset_id",
    "source_type",
    "historical_source_type",
    "instrument",
    "venue",
    "session_id",
    "session_date",
    "seed",
    "prediction_timestamp_ns",
    "tick",
    "sequence",
    "split_group",
    "attack_family",
    "attack_phase",
    "label",
    "label_source",
    "row_valid",
    "invalid_reason",
)


@dataclass(frozen=True)
class EventFact:
    timestamp_ns: int
    event_type: str
    quantity: float
    signed_quantity: float
    lifetime_ms: float | None
    cancel_lifetime_ms: float | None
    rapid_cancel: bool
    large_order: bool
    replenishment: bool
    burst: bool


@dataclass(frozen=True)
class SnapshotFact:
    timestamp_ns: int
    spread: float
    depth: float
    imbalance: float
    mid: float
    log_return: float | None
    message_rate: float
    liquidity: float


@dataclass(frozen=True)
class FeatureRunResult:
    rows: list[dict[str, Any]]
    quality_report: dict[str, Any]
    input_sha256: str
    input_provenance: dict[str, Any]


class FeaturePipeline:
    """Single-pass causal features over the Java-authoritative event stream."""

    def __init__(
        self,
        config: FeaturePipelineConfig,
        metadata: FeatureRunMetadata,
        labels: LabelSpec | None = None,
        expected_event_count: int | None = None,
    ) -> None:
        self.config = config
        self.metadata = metadata
        self.labels = labels or LabelSpec()
        if expected_event_count is not None and expected_event_count < 1:
            raise ValueError("expected event count must be positive")
        self.expected_event_count = expected_event_count
        self._reset_state()

    def _reset_state(self) -> None:
        self._event_facts: deque[EventFact] = deque()
        self._snapshot_facts: deque[SnapshotFact] = deque()
        self._semantic_errors: deque[tuple[int, str]] = deque()
        self._order_birth_ns: dict[str, int] = {}
        self._last_cancel_ns: dict[tuple[str, int], int] = {}
        self._last_message_ns: int | None = None
        self._previous_mid: float | None = None
        self._input_digest = hashlib.sha256()
        self._source_counts: Counter[str] = Counter()
        self._event_type_counts: Counter[str] = Counter()
        self._event_count = 0
        self._feature_checkpoint_count = 0
        self._historical_snapshot_count = 0
        self._first_sequence: int | None = None
        self._last_sequence: int | None = None
        self._first_timestamp_ns: int | None = None
        self._last_timestamp_ns: int | None = None
        self._previous_sequence: int | None = None
        self._previous_validation_time = -1
        self._previous_validation_tick = -1
        self._stream_complete = False
        self._first_half_state_peak = 0
        self._second_half_state_peak = 0

    def generate(self, events: Iterable[CanonicalExchangeEvent]) -> FeatureRunResult:
        rows = list(self.iter_rows(events))
        return self.finish(rows)

    def iter_rows(
        self,
        events: Iterable[CanonicalExchangeEvent],
    ) -> Iterable[dict[str, Any]]:
        """Yield causal feature rows while retaining only rolling exchange state."""
        self._reset_state()
        with DiskBackedUniqueIds() as unique_ids:
            for event in events:
                self._validate_next_event(event, unique_ids=unique_ids)
                canonical_line = json.dumps(
                    event.to_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._input_digest.update(canonical_line + b"\n")
                timestamp_ns = self._event_timestamp_ns(event)
                self._event_count += 1
                self._source_counts[event.source] += 1
                self._event_type_counts[event.event_type] += 1
                if self._first_sequence is None:
                    self._first_sequence = event.sequence
                    self._first_timestamp_ns = timestamp_ns
                self._last_sequence = event.sequence
                self._last_timestamp_ns = timestamp_ns
                if isinstance(event, LobSnapshotEvent):
                    if event.source == "historical":
                        self._historical_snapshot_count += 1
                        self._observe_historical_snapshot(event, timestamp_ns)
                    else:
                        row = self._snapshot_row(event, timestamp_ns)
                        self._feature_checkpoint_count += 1
                        yield row
                else:
                    self._observe_event(event, timestamp_ns)
                self._observe_bounded_state()
        if self._event_count == 0:
            raise ValueError("feature input requires at least one canonical event")
        if (
            self.expected_event_count is not None
            and self._event_count != self.expected_event_count
        ):
            raise ValueError("feature input event count does not match expected full stream")
        self._stream_complete = True

    def finish(self, rows: list[dict[str, Any]]) -> FeatureRunResult:
        """Finalize a fully consumed feature stream using collected output rows."""
        if not self._stream_complete:
            raise ValueError("feature stream must be consumed completely before finalization")
        quality = feature_quality_report(rows, FEATURE_COLUMNS)
        return FeatureRunResult(
            rows=rows,
            quality_report=quality,
            input_sha256=self._input_digest.hexdigest(),
            input_provenance=self.stream_provenance(),
        )

    def stream_provenance(self) -> dict[str, Any]:
        if not self._stream_complete:
            raise ValueError("feature stream must be consumed completely before reading provenance")
        return {
            "canonical_event_count": self._event_count,
            "source_event_counts": dict(sorted(self._source_counts.items())),
            "event_type_counts": dict(sorted(self._event_type_counts.items())),
            "feature_label_schema_version": self.labels.schema_version,
            "feature_label_spec_sha256": self.labels.spec_hash(),
            "feature_label_window_count": len(self.labels.labels),
            "feature_checkpoint_count": self._feature_checkpoint_count,
            "historical_source_snapshot_count": self._historical_snapshot_count,
            "first_sequence": self._first_sequence,
            "last_sequence": self._last_sequence,
            "first_timestamp_ns": self._first_timestamp_ns,
            "last_timestamp_ns": self._last_timestamp_ns,
            "bounded_state_first_half_peak": self._first_half_state_peak,
            "bounded_state_second_half_peak": self._second_half_state_peak,
            "bounded_state_growth_fraction": self._bounded_state_growth_fraction(),
        }

    @property
    def input_sha256(self) -> str:
        if not self._stream_complete:
            raise ValueError("feature stream must be consumed completely before reading its digest")
        return self._input_digest.hexdigest()

    def _validate_next_event(
        self,
        event: CanonicalExchangeEvent,
        *,
        unique_ids: DiskBackedUniqueIds,
    ) -> None:
        unique_ids.add(event.event_id)
        if event.sequence is None:
            raise ValueError("feature input requires assigned canonical sequences")
        if self._previous_sequence is None and event.sequence != 1:
            raise ValueError("canonical feature input must start at sequence 1")
        if self._previous_sequence is not None and event.sequence != self._previous_sequence + 1:
            raise ValueError("canonical event sequences must be contiguous and strictly increasing")
        timestamp_ns = self._event_timestamp_ns(event)
        if timestamp_ns < self._previous_validation_time:
            raise ValueError("canonical event timestamps must not regress")
        if event.tick is not None:
            if event.tick < self._previous_validation_tick:
                raise ValueError("canonical event ticks must not regress")
            self._previous_validation_tick = event.tick
        if isinstance(event, LobSnapshotEvent) and event.tick is None:
            raise ValueError("snapshot events require a tick for typed feature output")
        if event.symbol != self.metadata.instrument or event.venue != self.metadata.venue:
            raise ValueError("event instrument/venue does not match run metadata")
        self._previous_sequence = event.sequence
        self._previous_validation_time = timestamp_ns

    def _observe_bounded_state(self) -> None:
        state_size = (
            len(self._event_facts)
            + len(self._snapshot_facts)
            + len(self._semantic_errors)
            + len(self._order_birth_ns)
            + len(self._last_cancel_ns)
        )
        midpoint = (
            self.expected_event_count // 2
            if self.expected_event_count is not None
            else None
        )
        if midpoint is None or self._event_count <= midpoint:
            self._first_half_state_peak = max(self._first_half_state_peak, state_size)
        else:
            self._second_half_state_peak = max(self._second_half_state_peak, state_size)

    def _bounded_state_growth_fraction(self) -> float | None:
        if self.expected_event_count is None or self._second_half_state_peak == 0:
            return None
        baseline = max(self._first_half_state_peak, 1)
        return max(0.0, (self._second_half_state_peak - baseline) / baseline)

    def _event_timestamp_ns(self, event: CanonicalExchangeEvent) -> int:
        if event.exchange_timestamp_ns is not None:
            return event.exchange_timestamp_ns
        if event.tick is None:
            raise ValueError("event requires exchange_timestamp_ns or tick")
        return event.tick * self.metadata.tick_interval_ns

    def _observe_event(self, event: CanonicalExchangeEvent, timestamp_ns: int) -> None:
        self._semantic_errors.extend((timestamp_ns, error) for error in self._event_semantic_errors(event))
        burst = self._last_message_ns is not None and timestamp_ns - self._last_message_ns <= self.config.burst_gap_ns
        self._last_message_ns = timestamp_ns
        quantity = float(getattr(event, "quantity", 0.0))
        side = getattr(event, "side", None)
        side_sign = 1.0 if side == "buy" else -1.0 if side == "sell" else 0.0
        lifetime_ms: float | None = None
        cancel_lifetime_ms: float | None = None
        rapid_cancel = False
        replenishment = False
        large_order = False
        signed_quantity = 0.0

        if isinstance(event, AddOrderEvent):
            self._order_birth_ns[event.order_id] = timestamp_ns
            price_key = self._price_key(event.price)
            cancelled_at = self._last_cancel_ns.get((event.side, price_key))
            replenishment = (
                cancelled_at is not None and 0 <= timestamp_ns - cancelled_at <= self.config.replenishment_ns
            )
            large_order = event.quantity >= self.config.large_order_quantity
            signed_quantity = side_sign * event.quantity
        elif isinstance(event, ModifyOrderEvent):
            price_key = self._price_key(event.price)
            cancelled_at = self._last_cancel_ns.get((event.side, price_key))
            replenishment = (
                event.quantity > event.previous_quantity
                and cancelled_at is not None
                and 0 <= timestamp_ns - cancelled_at <= self.config.replenishment_ns
            )
            large_order = event.quantity >= self.config.large_order_quantity
            signed_quantity = side_sign * (event.quantity - event.previous_quantity)
        elif isinstance(event, CancelOrderEvent):
            birth = self._order_birth_ns.pop(event.order_id, None)
            if birth is not None:
                lifetime_ms = (timestamp_ns - birth) / 1_000_000.0
                cancel_lifetime_ms = lifetime_ms
                rapid_cancel = timestamp_ns - birth <= self.config.rapid_cancel_ns
            self._last_cancel_ns[(event.side, self._price_key(event.price))] = timestamp_ns
            signed_quantity = -side_sign * event.quantity
        elif isinstance(event, ExecuteOrderEvent):
            signed_quantity = side_sign * event.quantity
            lifetimes: list[float] = []
            for order_id, remaining in (
                (event.aggressor_order_id, event.aggressor_remaining_quantity),
                (event.resting_order_id, event.resting_remaining_quantity),
            ):
                birth = self._order_birth_ns.get(order_id)
                if birth is not None:
                    if remaining == 0:
                        lifetimes.append((timestamp_ns - birth) / 1_000_000.0)
                        self._order_birth_ns.pop(order_id, None)
            lifetime_ms = statistics.fmean(lifetimes) if lifetimes else None

        self._event_facts.append(
            EventFact(
                timestamp_ns=timestamp_ns,
                event_type=event.event_type,
                quantity=quantity,
                signed_quantity=signed_quantity,
                lifetime_ms=lifetime_ms,
                cancel_lifetime_ms=cancel_lifetime_ms,
                rapid_cancel=rapid_cancel,
                large_order=large_order,
                replenishment=replenishment,
                burst=burst,
            )
        )
        self._evict(timestamp_ns)

    def _observe_historical_snapshot(
        self,
        event: LobSnapshotEvent,
        timestamp_ns: int,
    ) -> None:
        self._semantic_errors.extend(
            (timestamp_ns, f"historical source snapshot: {error}") for error in self._book_errors(event.book)
        )
        self._evict(timestamp_ns)

    def _snapshot_row(self, event: LobSnapshotEvent, timestamp_ns: int) -> dict[str, Any]:
        if event.tick is None:
            raise AssertionError("validated snapshot tick is unexpectedly missing")
        prediction_tick = event.tick
        self._evict(timestamp_ns)
        book = event.book
        invalid = self._book_errors(book)
        bids = list(book.bids[: self.config.depth_levels])
        asks = list(book.asks[: self.config.depth_levels])
        invalid.extend(error for _, error in self._semantic_errors)
        bid_depth = sum(level.quantity for level in bids)
        ask_depth = sum(level.quantity for level in asks)
        total_depth = bid_depth + ask_depth
        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
        mid = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
        top_bid_quantity = bids[0].quantity if bids else 0.0
        top_ask_quantity = asks[0].quantity if asks else 0.0
        top_depth = top_bid_quantity + top_ask_quantity
        microprice = (
            (best_ask * top_bid_quantity + best_bid * top_ask_quantity) / top_depth
            if best_bid is not None and best_ask is not None and top_depth > 0
            else None
        )
        log_return = (
            math.log(mid / self._previous_mid)
            if mid is not None and self._previous_mid is not None and mid > 0 and self._previous_mid > 0
            else None
        )
        if mid is not None:
            self._previous_mid = mid

        short_events = self._events_within(timestamp_ns, self.config.short_window_ns)
        long_events = self._events_within(timestamp_ns, self.config.long_window_ns)
        short_seconds = self.config.short_window_ns / 1_000_000_000
        long_seconds = self.config.long_window_ns / 1_000_000_000
        short_stats = self._event_window_stats(short_events, short_seconds)
        long_stats = self._event_window_stats(long_events, long_seconds)
        depth_imbalance = _safe_ratio(bid_depth - ask_depth, total_depth)
        queue_imbalance = _safe_ratio(top_bid_quantity - top_ask_quantity, top_depth)
        liquidity = _safe_ratio(total_depth, spread) if spread is not None and spread > 0 else None

        provisional = SnapshotFact(
            timestamp_ns=timestamp_ns,
            spread=spread or 0.0,
            depth=total_depth,
            imbalance=depth_imbalance or 0.0,
            mid=mid or 0.0,
            log_return=log_return,
            message_rate=short_stats["message_rate"],
            liquidity=liquidity or 0.0,
        )
        self._snapshot_facts.append(provisional)
        self._evict(timestamp_ns)
        short_snapshots = self._snapshots_within(timestamp_ns, self.config.short_window_ns)
        long_snapshots = self._snapshots_within(timestamp_ns, self.config.long_window_ns)
        short_returns = [item.log_return for item in short_snapshots if item.log_return is not None]
        long_returns = [item.log_return for item in long_snapshots if item.log_return is not None]
        short_volatility = _realized_volatility(short_returns)
        long_volatility = _realized_volatility(long_returns)
        wall = self._wall_features(bids, asks, total_depth)
        message_rate_ratio = _safe_ratio(short_stats["message_rate"], long_stats["message_rate"])
        cancel_add_ratio = _safe_ratio(short_stats["cancel_count"], short_stats["add_count"])
        rapid_share = _safe_ratio(short_stats["rapid_cancel_count"], short_stats["cancel_count"])
        burst_share = _safe_ratio(short_stats["burst_count"], short_stats["message_count"])
        quote_stuffing_score = _bounded_mean(
            (
                _ratio_or_zero(short_stats["cancel_count"], short_stats["add_count"]),
                rapid_share or 0.0,
                min(message_rate_ratio or 0.0, 5.0) / 5.0,
                burst_share or 0.0,
            )
        )

        features: dict[str, float | None] = {
            "spread": spread,
            "spread_bps": _bps(spread, mid),
            "mid_price": mid,
            "microprice": microprice,
            "microprice_mid_delta_bps": _bps(
                microprice - mid if microprice is not None and mid is not None else None,
                mid,
            ),
            "log_return_1": log_return,
            "mid_return_short": sum(short_returns) if short_returns else None,
            "mid_return_long": sum(long_returns) if long_returns else None,
            "bid_depth_top_n": bid_depth,
            "ask_depth_top_n": ask_depth,
            "total_depth_top_n": total_depth,
            "top_level_depth": top_depth,
            "level_count": float(len(bids) + len(asks)),
            "depth_imbalance": depth_imbalance,
            "queue_imbalance_l1": queue_imbalance,
            "message_rate_short": short_stats["message_rate"],
            "add_rate_short": short_stats["add_rate"],
            "cancel_rate_short": short_stats["cancel_rate"],
            "trade_rate_short": short_stats["trade_rate"],
            "message_rate_long": long_stats["message_rate"],
            "add_rate_long": long_stats["add_rate"],
            "cancel_rate_long": long_stats["cancel_rate"],
            "trade_rate_long": long_stats["trade_rate"],
            "cancel_add_ratio_short": cancel_add_ratio,
            "cancel_trade_ratio_short": _safe_ratio(short_stats["cancel_count"], short_stats["trade_count"]),
            "trade_add_ratio_short": _safe_ratio(short_stats["trade_count"], short_stats["add_count"]),
            "signed_order_flow_imbalance_short": _safe_ratio(
                short_stats["signed_quantity"], short_stats["absolute_signed_quantity"]
            ),
            "cancel_quantity_ratio_short": _safe_ratio(short_stats["cancel_volume"], short_stats["add_volume"]),
            "add_volume_short": short_stats["add_volume"],
            "cancel_volume_short": short_stats["cancel_volume"],
            "trade_volume_short": short_stats["trade_volume"],
            "mean_order_lifetime_ms_short": _mean_or_none(short_stats["lifetimes"]),
            "mean_cancel_lifetime_ms_short": _mean_or_none(short_stats["cancel_lifetimes"]),
            "rapid_cancel_share_short": rapid_share,
            "large_order_rate_short": short_stats["large_order_count"] / short_seconds,
            "large_order_quantity_share_short": _safe_ratio(
                short_stats["large_order_volume"], short_stats["add_volume"]
            ),
            **wall,
            "replenishment_rate_short": _safe_ratio(short_stats["replenishment_count"], short_stats["add_count"]),
            "burst_message_share_short": burst_share,
            "message_rate_ratio_short_long": message_rate_ratio,
            "quote_stuffing_score": quote_stuffing_score,
            "realized_volatility_short": short_volatility,
            "realized_volatility_long": long_volatility,
            "return_volatility_ratio": _safe_ratio(short_volatility, long_volatility),
            "liquidity_score": liquidity,
            "amihud_illiquidity_short": _safe_ratio(abs(sum(short_returns)), short_stats["trade_volume"]),
            "spread_change_short_long": _mean_difference(
                [item.spread for item in short_snapshots],
                [item.spread for item in long_snapshots],
            ),
            "depth_change_short_long": _relative_mean_change(
                [item.depth for item in short_snapshots],
                [item.depth for item in long_snapshots],
            ),
            "imbalance_change_short_long": _mean_difference(
                [item.imbalance for item in short_snapshots],
                [item.imbalance for item in long_snapshots],
            ),
            "order_flow_change_short_long": (short_stats["signed_flow_rate"] - long_stats["signed_flow_rate"]),
            "spread_zscore_long": _zscore(
                spread, [item.spread for item in long_snapshots], self.config.zscore_min_periods
            ),
            "depth_zscore_long": _zscore(
                total_depth,
                [item.depth for item in long_snapshots],
                self.config.zscore_min_periods,
            ),
            "imbalance_zscore_long": _zscore(
                depth_imbalance,
                [item.imbalance for item in long_snapshots],
                self.config.zscore_min_periods,
            ),
            "message_rate_zscore_long": _zscore(
                short_stats["message_rate"],
                [item.message_rate for item in long_snapshots],
                self.config.zscore_min_periods,
            ),
            "return_zscore_long": _zscore(log_return, long_returns, self.config.zscore_min_periods),
            "volatility_regime": _safe_ratio(short_volatility, long_volatility),
            "liquidity_regime": _zscore(
                liquidity,
                [item.liquidity for item in long_snapshots],
                self.config.zscore_min_periods,
            ),
        }
        missing_features = [name for name in FEATURE_COLUMNS if name not in features]
        if missing_features:
            raise AssertionError(f"feature implementation is incomplete: {missing_features}")
        invalid.extend(name for name, value in features.items() if value is not None and not math.isfinite(value))
        if self.config.schema_version == FEATURE_SCHEMA_V2:
            for name, value in features.items():
                if value is None or not math.isfinite(value):
                    continue
                try:
                    features[name] = struct.unpack("!f", struct.pack("!f", value))[0]
                except OverflowError:
                    features[name] = None
                    invalid.append(f"{name}: outside float32 range")
        label = assign_label(
            self.labels,
            tick=prediction_tick,
            prediction_timestamp_ns=timestamp_ns,
        )
        split_group = feature_split_group(self.metadata)
        row: dict[str, Any] = {
            "feature_schema_version": self.config.schema_version,
            "feature_config_hash": self.config.config_hash(),
            "run_id": self.metadata.run_id,
            "dataset_id": self.metadata.dataset_id,
            "source_type": self.metadata.source_type,
            "historical_source_type": self.metadata.historical_source_type,
            "instrument": self.metadata.instrument,
            "venue": self.metadata.venue,
            "session_id": self.metadata.session_id,
            "session_date": self.metadata.session_date,
            "seed": self.metadata.seed,
            "prediction_timestamp_ns": timestamp_ns,
            "tick": prediction_tick,
            "sequence": event.sequence,
            "split_group": split_group,
            "attack_family": label.attack_family,
            "attack_phase": label.attack_phase,
            "label": label.label,
            "label_source": label.label_source,
            "row_valid": not invalid,
            "invalid_reason": "; ".join(sorted(set(invalid))) if invalid else None,
        }
        row.update({name: features[name] for name in FEATURE_COLUMNS})
        return row

    def _event_window_stats(self, facts: Sequence[EventFact], seconds: float) -> dict[str, Any]:
        counts = {kind: sum(fact.event_type == kind for fact in facts) for kind in ("add", "cancel", "execute")}
        add_volume = sum(fact.quantity for fact in facts if fact.event_type == "add")
        cancel_volume = sum(fact.quantity for fact in facts if fact.event_type == "cancel")
        trade_volume = sum(fact.quantity for fact in facts if fact.event_type == "execute")
        signed_quantity = sum(fact.signed_quantity for fact in facts)
        return {
            "message_count": len(facts),
            "add_count": counts["add"],
            "cancel_count": counts["cancel"],
            "trade_count": counts["execute"],
            "message_rate": len(facts) / seconds,
            "add_rate": counts["add"] / seconds,
            "cancel_rate": counts["cancel"] / seconds,
            "trade_rate": counts["execute"] / seconds,
            "add_volume": add_volume,
            "cancel_volume": cancel_volume,
            "trade_volume": trade_volume,
            "signed_quantity": signed_quantity,
            "absolute_signed_quantity": sum(abs(fact.signed_quantity) for fact in facts),
            "signed_flow_rate": signed_quantity / seconds,
            "lifetimes": [fact.lifetime_ms for fact in facts if fact.lifetime_ms is not None],
            "cancel_lifetimes": [fact.cancel_lifetime_ms for fact in facts if fact.cancel_lifetime_ms is not None],
            "rapid_cancel_count": sum(fact.rapid_cancel for fact in facts),
            "large_order_count": sum(fact.large_order and fact.event_type == "add" for fact in facts),
            "large_order_volume": sum(fact.quantity for fact in facts if fact.large_order and fact.event_type == "add"),
            "replenishment_count": sum(fact.replenishment for fact in facts),
            "burst_count": sum(fact.burst for fact in facts),
        }

    def _wall_features(
        self,
        bids: Sequence[PriceLevel],
        asks: Sequence[PriceLevel],
        total_depth: float,
    ) -> dict[str, float | None]:
        quantities = [level.quantity for level in (*bids, *asks)]
        median = statistics.median(quantities) if quantities else 0.0
        threshold = median * self.config.wall_size_multiple
        bid_walls = sum(level.quantity >= threshold for level in bids) if threshold > 0 else 0
        ask_walls = sum(level.quantity >= threshold for level in asks) if threshold > 0 else 0
        wall_count = bid_walls + ask_walls
        layering = max(bid_walls, ask_walls) / self.config.layering_min_levels
        return {
            "wall_level_count": float(wall_count),
            "largest_level_share": _safe_ratio(max(quantities, default=0.0), total_depth),
            "wall_side_imbalance": _safe_ratio(bid_walls - ask_walls, wall_count),
            "layering_score": min(layering, 1.0),
        }

    def _book_errors(
        self,
        book: OrderBookSnapshot,
    ) -> list[str]:
        bids: Sequence[PriceLevel] = book.bids
        asks: Sequence[PriceLevel] = book.asks
        errors: list[str] = []
        if not bids or not asks:
            errors.append("book side missing")
        if any(level.price <= 0 or level.quantity <= 0 for level in (*bids, *asks)):
            errors.append("non-positive price or quantity")
        if [level.price for level in bids] != sorted((level.price for level in bids), reverse=True):
            errors.append("bid levels not descending")
        if [level.price for level in asks] != sorted(level.price for level in asks):
            errors.append("ask levels not ascending")
        if bids and asks and bids[0].price >= asks[0].price:
            errors.append("locked or crossed book")
        if bids and book.best_bid is not None and not _equivalent(book.best_bid, bids[0].price):
            errors.append("snapshot best bid inconsistent with levels")
        if asks and book.best_ask is not None and not _equivalent(book.best_ask, asks[0].price):
            errors.append("snapshot best ask inconsistent with levels")
        if bids and asks:
            expected_mid = (bids[0].price + asks[0].price) / 2
            expected_spread = asks[0].price - bids[0].price
            if book.mid is not None and not _equivalent(book.mid, expected_mid):
                errors.append("snapshot mid inconsistent with levels")
            if book.spread is not None and not _equivalent(book.spread, expected_spread):
                errors.append("snapshot spread inconsistent with levels")
        for level in (*bids, *asks):
            if not _aligned(level.price, self.metadata.price_tick_size):
                errors.append("price not aligned to tick size")
            if not _aligned(level.quantity, self.metadata.quantity_lot_size):
                errors.append("quantity not aligned to lot size")
        return errors

    def _event_semantic_errors(self, event: CanonicalExchangeEvent) -> list[str]:
        if isinstance(event, LobSnapshotEvent):
            return []
        values: list[tuple[str, float, float]] = []
        price = getattr(event, "price", None)
        quantity = getattr(event, "quantity", None)
        if isinstance(price, (int, float)):
            values.append(("event price not aligned to tick size", float(price), self.metadata.price_tick_size))
        if isinstance(quantity, (int, float)):
            values.append(
                (
                    "event quantity not aligned to lot size",
                    float(quantity),
                    self.metadata.quantity_lot_size,
                )
            )
        if isinstance(event, ModifyOrderEvent):
            values.extend(
                (
                    (
                        "previous event price not aligned to tick size",
                        event.previous_price,
                        self.metadata.price_tick_size,
                    ),
                    (
                        "previous event quantity not aligned to lot size",
                        event.previous_quantity,
                        self.metadata.quantity_lot_size,
                    ),
                )
            )
        if isinstance(event, ExecuteOrderEvent):
            values.extend(
                (
                    (
                        "aggressor remaining quantity not aligned to lot size",
                        event.aggressor_remaining_quantity,
                        self.metadata.quantity_lot_size,
                    ),
                    (
                        "resting remaining quantity not aligned to lot size",
                        event.resting_remaining_quantity,
                        self.metadata.quantity_lot_size,
                    ),
                )
            )
        return [message for message, value, increment in values if not _aligned(value, increment)]

    def _price_key(self, price: float) -> int:
        return round(price / self.metadata.price_tick_size)

    def _events_within(self, now_ns: int, window_ns: int) -> list[EventFact]:
        cutoff = now_ns - window_ns
        return [fact for fact in self._event_facts if fact.timestamp_ns > cutoff]

    def _snapshots_within(self, now_ns: int, window_ns: int) -> list[SnapshotFact]:
        cutoff = now_ns - window_ns
        return [fact for fact in self._snapshot_facts if fact.timestamp_ns > cutoff]

    def _evict(self, now_ns: int) -> None:
        cutoff = now_ns - self.config.long_window_ns
        while self._event_facts and self._event_facts[0].timestamp_ns <= cutoff:
            self._event_facts.popleft()
        while self._snapshot_facts and self._snapshot_facts[0].timestamp_ns <= cutoff:
            self._snapshot_facts.popleft()
        while self._semantic_errors and self._semantic_errors[0][0] <= cutoff:
            self._semantic_errors.popleft()
        stale_cancels = [key for key, value in self._last_cancel_ns.items() if value <= cutoff]
        for key in stale_cancels:
            self._last_cancel_ns.pop(key, None)


def feature_quality_report(
    rows: Sequence[dict[str, Any]],
    feature_columns: Sequence[str],
) -> dict[str, Any]:
    invalid = [
        {
            "row_index": index,
            "tick": row.get("tick"),
            "prediction_timestamp_ns": row.get("prediction_timestamp_ns"),
            "reason": row.get("invalid_reason"),
        }
        for index, row in enumerate(rows)
        if not row.get("row_valid", False)
    ]
    distributions = {name: _distribution([row.get(name) for row in rows]) for name in feature_columns}
    labels = [row.get("label") for row in rows]
    attack_families: dict[str, int] = {}
    for row in rows:
        family = row.get("attack_family")
        if family:
            attack_families[str(family)] = attack_families.get(str(family), 0) + 1
    return {
        "schema_version": "feature_quality_report_v1",
        "row_count": len(rows),
        "valid_row_count": len(rows) - len(invalid),
        "invalid_row_count": len(invalid),
        "invalid_rows": invalid[:100],
        "missing_values": {name: sum(row.get(name) is None for row in rows) for name in feature_columns},
        "distributions": distributions,
        "class_balance": {
            "positive": sum(value == 1 for value in labels),
            "negative": sum(value == 0 for value in labels),
            "unlabeled": sum(value is None for value in labels),
            "attack_family_rows": dict(sorted(attack_families.items())),
        },
    }


def _distribution(values: Iterable[object]) -> dict[str, float | int | None]:
    numeric = sorted(
        float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(float(value))
    )
    if not numeric:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "stddev": None,
            "p01": None,
            "p50": None,
            "p99": None,
        }
    return {
        "count": len(numeric),
        "min": numeric[0],
        "max": numeric[-1],
        "mean": statistics.fmean(numeric),
        "stddev": statistics.pstdev(numeric),
        "p01": _percentile(numeric, 0.01),
        "p50": _percentile(numeric, 0.50),
        "p99": _percentile(numeric, 0.99),
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def feature_split_group(metadata: FeatureRunMetadata) -> str:
    identity = "|".join(
        (
            metadata.instrument,
            metadata.venue,
            metadata.session_id,
            metadata.session_date.isoformat(),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _aligned(value: float, increment: float) -> bool:
    units = value / increment
    return math.isclose(units, round(units), rel_tol=0.0, abs_tol=1e-7)


def _equivalent(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _safe_ratio(numerator: float, denominator: float | None) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _ratio_or_zero(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _bps(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference == 0:
        return None
    return value / reference * 10_000


def _mean_or_none(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _realized_volatility(values: Sequence[float]) -> float | None:
    return math.sqrt(sum(value * value for value in values)) if values else None


def _bounded_mean(values: Sequence[float]) -> float:
    return max(0.0, min(1.0, statistics.fmean(values)))


def _mean_difference(short: Sequence[float], long: Sequence[float]) -> float | None:
    if not short or not long:
        return None
    return statistics.fmean(short) - statistics.fmean(long)


def _relative_mean_change(short: Sequence[float], long: Sequence[float]) -> float | None:
    if not short or not long:
        return None
    long_mean = statistics.fmean(long)
    return _safe_ratio(statistics.fmean(short) - long_mean, abs(long_mean))


def _zscore(
    current: float | None,
    values: Sequence[float],
    minimum_periods: int,
) -> float | None:
    if current is None or len(values) < minimum_periods:
        return None
    mean = statistics.fmean(values)
    stddev = statistics.pstdev(values)
    if stddev == 0:
        return 0.0
    return (current - mean) / stddev
