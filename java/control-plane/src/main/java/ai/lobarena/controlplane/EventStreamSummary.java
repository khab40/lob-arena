package ai.lobarena.controlplane;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.kernel.hashing.CanonicalHashes;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Incremental full-stream state used by the long-running control plane.
 *
 * <p>The matching engine may evict old events from its live window, so every
 * summary that contributes to deterministic replay must be advanced here when
 * the canonical event is emitted.
 */
final class EventStreamSummary {
    private static final int CONTRACT_VERSION = 1;
    private static final int MAX_SCENARIO_EVENTS = 100_000;

    private final Map<EventSource, Long> sourceCounts = new EnumMap<>(EventSource.class);
    private final Map<ExchangeEvent.PayloadCase, Long> typeCounts =
            new EnumMap<>(ExchangeEvent.PayloadCase.class);
    private final Map<EventSource, MessageDigest> sourceDigests = new EnumMap<>(EventSource.class);
    private final MessageDigest historicalSnapshotDigest = sha256();
    private final List<ValidationPoint> validationPoints = new ArrayList<>();
    private final List<ExchangeEvent> scenarioEvents = new ArrayList<>();
    private final Map<String, Long> orderCreatedAtNs = new LinkedHashMap<>();
    private final Map<Long, Double> currentTickCancellationLifetimeMs = new LinkedHashMap<>();

    private byte[] streamHash = CanonicalHashes.initialStreamHash(CONTRACT_VERSION);
    private long eventCount;
    private long historicalSourceSequences;
    private long lastHistoricalSourceSequence = Long.MIN_VALUE;
    private long flowTick = Long.MIN_VALUE;
    private final long[] currentFlow = new long[4];

    EventStreamSummary() {
        sourceDigests.put(EventSource.EVENT_SOURCE_HISTORICAL, sha256());
        sourceDigests.put(EventSource.EVENT_SOURCE_SIMULATION, sha256());
    }

    void accept(ExchangeEvent event) {
        eventCount++;
        byte[] eventHash = CanonicalHashes.eventHash(event);
        streamHash = CanonicalHashes.advanceStreamHash(streamHash, eventHash);
        EventSource source = event.getMetadata().getSource();
        sourceCounts.merge(source, 1L, Long::sum);
        typeCounts.merge(event.getPayloadCase(), 1L, Long::sum);
        sourceDigests.computeIfAbsent(source, ignored -> sha256()).update(eventHash);

        long tick = event.getMetadata().getTick();
        if (tick != flowTick) {
            flowTick = tick;
            java.util.Arrays.fill(currentFlow, 0);
            currentTickCancellationLifetimeMs.clear();
        }
        updateOrderLifetimes(event);
        if (event.getPayloadCase() != ExchangeEvent.PayloadCase.SNAPSHOT) {
            currentFlow[0]++;
            switch (event.getPayloadCase()) {
                case ADD -> currentFlow[1]++;
                case CANCEL -> currentFlow[2]++;
                case EXECUTE -> currentFlow[3]++;
                default -> {
                    // Modify events contribute to message_count only.
                }
            }
        }

        if (source == EventSource.EVENT_SOURCE_HISTORICAL
                && event.getMetadata().hasSourceSequence()
                && event.getMetadata().getSourceSequence() != lastHistoricalSourceSequence) {
            lastHistoricalSourceSequence = event.getMetadata().getSourceSequence();
            historicalSourceSequences++;
        }
        if (source == EventSource.EVENT_SOURCE_HISTORICAL
                && event.getPayloadCase() == ExchangeEvent.PayloadCase.SNAPSHOT) {
            String identity = "%d|%d|".formatted(
                    event.getMetadata().hasSourceSequence()
                            ? event.getMetadata().getSourceSequence()
                            : 0,
                    event.getMetadata().hasExchangeTimestampNs()
                            ? event.getMetadata().getExchangeTimestampNs()
                            : 0);
            historicalSnapshotDigest.update(identity.getBytes(StandardCharsets.US_ASCII));
            historicalSnapshotDigest.update(CanonicalHashes.bookHash(event.getSnapshot().getBook()));
        }
        if (source == EventSource.EVENT_SOURCE_SIMULATION
                && event.getPayloadCase() == ExchangeEvent.PayloadCase.SNAPSHOT) {
            validationPoints.add(new ValidationPoint(
                    tick,
                    event.getMetadata().hasExchangeTimestampNs()
                            ? event.getMetadata().getExchangeTimestampNs()
                            : 0,
                    event.getSnapshot().getBook(),
                    currentFlow.clone()));
        }
        if (source == EventSource.EVENT_SOURCE_SIMULATION
                && event.getMetadata().hasScenarioId()) {
            if (scenarioEvents.size() >= MAX_SCENARIO_EVENTS) {
                throw new IllegalStateException(
                        "scenario event summary exceeded " + MAX_SCENARIO_EVENTS + " events");
            }
            scenarioEvents.add(event);
        }
    }

    long eventCount() {
        return eventCount;
    }

    long sourceCount(EventSource source) {
        return sourceCounts.getOrDefault(source, 0L);
    }

    long typeCount(ExchangeEvent.PayloadCase type) {
        return typeCounts.getOrDefault(type, 0L);
    }

    String streamHashHex() {
        return java.util.HexFormat.of().formatHex(streamHash);
    }

    String sourceHashHex(EventSource source) {
        MessageDigest digest = sourceDigests.get(source);
        return java.util.HexFormat.of().formatHex(digest == null ? sha256().digest() : digestSnapshot(digest));
    }

    String historicalSnapshotHashHex() {
        return java.util.HexFormat.of().formatHex(digestSnapshot(historicalSnapshotDigest));
    }

    long historicalSourceSequences() {
        return historicalSourceSequences;
    }

    List<ValidationPoint> validationPoints() {
        return List.copyOf(validationPoints);
    }

    List<ExchangeEvent> scenarioEvents() {
        return List.copyOf(scenarioEvents);
    }

    double averageCancellationLifetimeMs(List<ExchangeEvent> events) {
        double total = 0;
        int count = 0;
        for (ExchangeEvent event : events) {
            if (event.getPayloadCase() != ExchangeEvent.PayloadCase.CANCEL) {
                continue;
            }
            Double lifetime = currentTickCancellationLifetimeMs.get(
                    event.getMetadata().getSequence());
            if (lifetime != null) {
                total += lifetime;
                count++;
            }
        }
        return count == 0 ? 0 : total / count;
    }

    private void updateOrderLifetimes(ExchangeEvent event) {
        switch (event.getPayloadCase()) {
            case ADD -> orderCreatedAtNs.putIfAbsent(
                    event.getAdd().getOrderId(), eventTimeNs(event));
            case CANCEL -> {
                Long created = orderCreatedAtNs.remove(event.getCancel().getOrderId());
                if (created != null) {
                    currentTickCancellationLifetimeMs.put(
                            event.getMetadata().getSequence(),
                            Math.max(0, eventTimeNs(event) - created) / 1_000_000.0);
                }
            }
            case EXECUTE -> {
                if (event.getExecute().getRestingRemainingQuantityLots() == 0) {
                    orderCreatedAtNs.remove(event.getExecute().getRestingOrderId());
                }
                if (event.getExecute().getAggressorRemainingQuantityLots() == 0) {
                    orderCreatedAtNs.remove(event.getExecute().getAggressorOrderId());
                }
            }
            default -> {
                // Modify and snapshot events do not change order birth time.
            }
        }
    }

    private static long eventTimeNs(ExchangeEvent event) {
        if (event.getMetadata().hasExchangeTimestampNs()) {
            return event.getMetadata().getExchangeTimestampNs();
        }
        return event.getMetadata().getTick() * 500_000_000L;
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
    }

    private static byte[] digestSnapshot(MessageDigest digest) {
        try {
            return ((MessageDigest) digest.clone()).digest();
        } catch (CloneNotSupportedException exception) {
            throw new IllegalStateException("SHA-256 provider must support digest snapshots", exception);
        }
    }

    record ValidationPoint(
            long tick,
            long exchangeTimestampNs,
            BookSnapshot book,
            long[] eventFlow) {
        ValidationPoint {
            eventFlow = eventFlow.clone();
        }

        @Override
        public long[] eventFlow() {
            return eventFlow.clone();
        }
    }
}
