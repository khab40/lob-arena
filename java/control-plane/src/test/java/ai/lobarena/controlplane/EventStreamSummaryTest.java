package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;

import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.exchange.v1.Side;
import ai.lobarena.kernel.book.IntegerMatchingEngine;
import ai.lobarena.kernel.book.IntegerOrderBook;
import ai.lobarena.kernel.book.KernelOrder;
import ai.lobarena.kernel.hashing.CanonicalHashes;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import org.junit.jupiter.api.Test;

class EventStreamSummaryTest {
    @Test
    void streamingDigestMatchesTheFullCanonicalEventStreamAfterEviction() {
        EventStreamSummary summary = new EventStreamSummary();
        List<ExchangeEvent> allEvents = new ArrayList<>();
        IntegerMatchingEngine engine = new IntegerMatchingEngine(
                new IntegerOrderBook(1_000_000, 1_000_000),
                "TEST",
                "SIM",
                EventSource.EVENT_SOURCE_SIMULATION,
                2,
                event -> {
                    allEvents.add(event);
                    summary.accept(event);
                });

        engine.submit(KernelOrder.limit("one", "maker", Side.SIDE_BUY, 1, 99, 1));
        engine.submit(KernelOrder.limit("two", "maker", Side.SIDE_BUY, 1, 98, 2));
        engine.submit(KernelOrder.limit("three", "maker", Side.SIDE_BUY, 1, 97, 3));

        assertThat(engine.retainedEventCount()).isEqualTo(2);
        assertThat(summary.eventCount()).isEqualTo(3);
        assertThat(summary.streamHashHex())
                .isEqualTo(HexFormat.of().formatHex(CanonicalHashes.eventStreamHash(allEvents, 1)));
        assertThat(summary.sourceCount(EventSource.EVENT_SOURCE_SIMULATION)).isEqualTo(3);
    }
}
