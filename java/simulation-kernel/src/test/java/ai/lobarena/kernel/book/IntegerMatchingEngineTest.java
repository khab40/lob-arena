package ai.lobarena.kernel.book;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.exchange.v1.PriceLevel;
import ai.lobarena.exchange.v1.Side;
import ai.lobarena.kernel.hashing.CanonicalHashes;
import java.util.List;
import org.junit.jupiter.api.Test;

final class IntegerMatchingEngineTest {
    @Test
    void limitMatchEmitsExecutionThenRestsExactRemainder() {
        IntegerMatchingEngine engine = engine();
        engine.submit(KernelOrder.limit("ask", "maker", Side.SIDE_SELL, 600, 100, 1));

        List<ExchangeEvent> events = engine.submit(
                KernelOrder.limit("buy", "taker", Side.SIDE_BUY, 1_000, 101, 2));

        assertEquals(List.of("execute", "add"), events.stream().map(this::payload).toList());
        assertEquals(600, events.get(0).getExecute().getQuantityLots());
        assertEquals(400, events.get(1).getAdd().getQuantityLots());
        assertEquals(List.of(2L, 3L), events.stream().map(event -> event.getMetadata().getSequence()).toList());
        assertEquals("SIM:execute:2", events.get(0).getMetadata().getEventId());
        assertEquals(400, engine.book().snapshot(5).getBids(0).getQuantityLots());
    }

    @Test
    void cancelAndModifyEventsUseActualRestingState() {
        IntegerMatchingEngine engine = engine();
        engine.submit(KernelOrder.limit("bid", "maker", Side.SIDE_BUY, 2_500, 99, 1));

        ExchangeEvent modify = engine.submit(
                KernelOrder.modify("bid", "maker", Side.SIDE_BUY, 4_000, 99L, 3)).getFirst();
        ExchangeEvent cancel = engine.submit(
                KernelOrder.cancel("bid", "requester", Side.SIDE_SELL, 4)).getFirst();

        assertEquals(2_500, modify.getModify().getPreviousQuantityLots());
        assertEquals(4_000, modify.getModify().getQuantityLots());
        assertTrue(modify.getModify().getPriorityPreserved());
        assertEquals("maker", cancel.getCancel().getAgentId());
        assertEquals(Side.SIDE_BUY, cancel.getCancel().getSide());
        assertEquals(4_000, cancel.getCancel().getQuantityLots());
        assertEquals(4, cancel.getMetadata().getTick());
        assertEquals(0, engine.book().snapshot(5).getBidsCount());
    }

    @Test
    void allPayloadsAndSnapshotProduceContiguousCanonicallyHashableStream() {
        IntegerMatchingEngine engine = engine();
        engine.submit(KernelOrder.limit("bid", "maker", Side.SIDE_BUY, 5, 99, 1));
        engine.submit(KernelOrder.modify("bid", "maker", Side.SIDE_BUY, 6, 99L, 2));
        engine.submit(KernelOrder.cancel("bid", "requester", Side.SIDE_SELL, 3));
        engine.submit(KernelOrder.limit("ask", "maker", Side.SIDE_SELL, 2, 101, 4));
        engine.submit(KernelOrder.market("buy", "taker", Side.SIDE_BUY, 2, 5));
        ExchangeEvent snapshot = engine.recordSnapshot(5, 3, null, null, "scenario-1", "test", "test");

        assertEquals(
                List.of("add", "modify", "cancel", "add", "execute", "snapshot"),
                engine.events().stream().map(this::payload).toList());
        assertEquals(3, snapshot.getSnapshot().getDepth());
        assertEquals(
                List.of(1L, 2L, 3L, 4L, 5L, 6L),
                engine.events().stream().map(event -> event.getMetadata().getSequence()).toList());
        assertEquals(32, CanonicalHashes.eventStreamHash(engine.events(), 1).length);
    }

    @Test
    void initializationAfterListenerProducesDeterministicBaselineAdds() {
        IntegerMatchingEngine engine = engine();

        engine.book().initialize(100, 2, 1, 1_500, "normal");
        ExchangeEvent snapshot = engine.recordSnapshot(7, 1, null, null, null, null, null);

        assertEquals(List.of("add", "add", "add", "add", "snapshot"),
                engine.events().stream().map(this::payload).toList());
        assertEquals(5, snapshot.getMetadata().getSequence());
        assertEquals(1, snapshot.getSnapshot().getBook().getBidsCount());
        assertEquals(1, snapshot.getSnapshot().getBook().getAsksCount());
    }

    @Test
    void unknownCancelModifyAndUnfilledMarketEmitNothing() {
        IntegerMatchingEngine engine = engine();

        assertTrue(engine.submit(KernelOrder.cancel("missing", "maker", Side.SIDE_BUY, 0)).isEmpty());
        assertTrue(engine.submit(KernelOrder.modify("missing", "maker", Side.SIDE_BUY, 1, 99L, 0)).isEmpty());
        assertTrue(engine.submit(KernelOrder.market("empty", "taker", Side.SIDE_BUY, 5, 0)).isEmpty());
        assertTrue(engine.events().isEmpty());
    }

    @Test
    void perSubmissionContextPreservesHistoricalProvenanceAndLogicalTick() {
        IntegerMatchingEngine engine = engine();
        MutationContext historical = new MutationContext(
                7L,
                null,
                null,
                null,
                EventSource.EVENT_SOURCE_HISTORICAL,
                42L,
                35_100_000_000_000L,
                35_100_000_000_001L);
        engine.submit(
                KernelOrder.limit("ask", "historical-maker", Side.SIDE_SELL, 5, 101, 35_100_000_000_000L),
                historical);
        ExchangeEvent execution = engine.submit(
                        KernelOrder.market(
                                "buy", "historical-taker", Side.SIDE_BUY, 2, 35_100_000_000_100L),
                        new MutationContext(
                                8L,
                                null,
                                null,
                                null,
                                EventSource.EVENT_SOURCE_HISTORICAL,
                                43L,
                                35_100_000_000_100L,
                                35_100_000_000_101L))
                .getFirst();

        assertEquals(EventSource.EVENT_SOURCE_HISTORICAL, execution.getMetadata().getSource());
        assertEquals(43, execution.getMetadata().getSourceSequence());
        assertEquals(8, execution.getMetadata().getTick());
        assertEquals(35_100_000_000_100L, execution.getMetadata().getExchangeTimestampNs());
        assertEquals(32, CanonicalHashes.eventStreamHash(engine.events(), 1).length);
    }

    @Test
    void boundedEventViewsPreserveOrderWithoutCopyingTheFullHistory() {
        IntegerMatchingEngine engine = engine();
        engine.submit(KernelOrder.limit("bid-1", "maker", Side.SIDE_BUY, 1, 97, 1));
        engine.submit(KernelOrder.limit("bid-2", "maker", Side.SIDE_BUY, 1, 98, 2));
        engine.submit(KernelOrder.limit("bid-3", "maker", Side.SIDE_BUY, 1, 99, 3));
        engine.submit(
                KernelOrder.limit("ask-historical", "historical", Side.SIDE_SELL, 1, 101, 4),
                new MutationContext(
                        4L,
                        null,
                        null,
                        null,
                        EventSource.EVENT_SOURCE_HISTORICAL,
                        10L,
                        4L,
                        4L));

        assertEquals(
                List.of(3L, 4L),
                engine.tailEvents(2).stream().map(event -> event.getMetadata().getSequence()).toList());
        assertEquals(
                List.of(4L),
                engine.tailEventsBySource(EventSource.EVENT_SOURCE_HISTORICAL, 5).stream()
                        .map(event -> event.getMetadata().getSequence())
                        .toList());
        assertEquals(
                List.of(3L),
                engine.eventsAtTick(3).stream().map(event -> event.getMetadata().getSequence()).toList());
        assertEquals(
                List.of(3L),
                engine.eventsAfterSequence(2, 1).stream()
                        .map(event -> event.getMetadata().getSequence())
                        .toList());
        assertEquals(4, engine.latestEventSequence());
    }

    @Test
    void recordsImmutableSourceSnapshotWithoutReplacingLiveBook() {
        IntegerMatchingEngine engine = engine();
        engine.submit(KernelOrder.limit("synthetic-bid", "agent", Side.SIDE_BUY, 5, 99, 1));
        BookSnapshot historical = BookSnapshot.newBuilder()
                .addBids(PriceLevel.newBuilder().setPriceTicks(90).setQuantityLots(10).setOwner("historical"))
                .addAsks(PriceLevel.newBuilder().setPriceTicks(91).setQuantityLots(12).setOwner("historical"))
                .setBestBidTicks(90)
                .setBestAskTicks(91)
                .setMidPriceTicksX2(181)
                .setSpreadTicks(1)
                .build();

        ExchangeEvent event = engine.recordSnapshot(
                historical,
                1,
                new MutationContext(
                        2L,
                        null,
                        null,
                        null,
                        EventSource.EVENT_SOURCE_HISTORICAL,
                        17L,
                        34_200_000_000_000L,
                        34_200_000_000_000L));

        assertEquals(90, event.getSnapshot().getBook().getBestBidTicks());
        assertEquals(99, engine.book().snapshot(1).getBestBidTicks());
        assertEquals(EventSource.EVENT_SOURCE_HISTORICAL, event.getMetadata().getSource());
        assertEquals(17, event.getMetadata().getSourceSequence());
    }

    @Test
    void boundedHistoryEvictsWithoutReusingSequencesOrDroppingSinkEvents() {
        List<ExchangeEvent> emitted = new java.util.ArrayList<>();
        IntegerMatchingEngine engine = new IntegerMatchingEngine(
                new IntegerOrderBook(1_000_000_000, 1_000_000),
                "LOB",
                "SIM",
                EventSource.EVENT_SOURCE_SIMULATION,
                2,
                emitted::add);

        engine.submit(KernelOrder.limit("bid-1", "maker", Side.SIDE_BUY, 1, 97, 1));
        engine.submit(KernelOrder.limit("bid-2", "maker", Side.SIDE_BUY, 1, 98, 2));
        engine.submit(KernelOrder.limit("bid-3", "maker", Side.SIDE_BUY, 1, 99, 3));
        List<ExchangeEvent> fourth =
                engine.submit(KernelOrder.limit("bid-4", "maker", Side.SIDE_BUY, 1, 100, 4));

        assertEquals(List.of(3L, 4L), engine.events().stream()
                .map(event -> event.getMetadata().getSequence())
                .toList());
        assertEquals(3, engine.firstRetainedSequence());
        assertEquals(4, engine.latestEventSequence());
        assertEquals(2, engine.retainedEventCount());
        assertEquals(List.of(1L, 2L, 3L, 4L), emitted.stream()
                .map(event -> event.getMetadata().getSequence())
                .toList());
        assertEquals(List.of(4L), fourth.stream()
                .map(event -> event.getMetadata().getSequence())
                .toList());
    }

    private IntegerMatchingEngine engine() {
        return new IntegerMatchingEngine(
                new IntegerOrderBook(1_000_000_000, 1_000_000),
                "LOB",
                "SIM",
                EventSource.EVENT_SOURCE_SIMULATION);
    }

    private String payload(ExchangeEvent event) {
        return event.getPayloadCase().name().toLowerCase();
    }
}
