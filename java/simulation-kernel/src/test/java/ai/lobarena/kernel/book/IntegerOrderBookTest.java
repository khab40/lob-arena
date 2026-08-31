package ai.lobarena.kernel.book;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.Side;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

final class IntegerOrderBookTest {
    @Test
    void matchingUsesBestPriceThenFifoAndPreservesPartialRemainder() {
        IntegerOrderBook book = book();
        book.add(KernelOrder.limit("far", "maker-far", Side.SIDE_SELL, 4, 101, 0));
        book.add(KernelOrder.limit("old", "maker-old", Side.SIDE_SELL, 3, 100, 1));
        book.add(KernelOrder.limit("new", "maker-new", Side.SIDE_SELL, 4, 100, 2));

        List<Execution> executions = book.match(
                KernelOrder.market("buy", "taker", Side.SIDE_BUY, 5, 3), null);

        assertEquals(List.of("old", "new"), executions.stream().map(Execution::restingOrderId).toList());
        assertEquals(List.of(3L, 2L), executions.stream().map(Execution::quantityLots).toList());
        assertEquals(2, book.orders().get("new").quantityLots());
        assertEquals(100, book.bestAsk());
        assertEquals(List.of("new"), book.orderIdsAt(Side.SIDE_SELL, 100));
    }

    @Test
    void sellAggressorUsesHighestBidAndHonorsItsLimit() {
        IntegerOrderBook book = book();
        book.add(KernelOrder.limit("low", "maker-low", Side.SIDE_BUY, 4, 98, 1));
        book.add(KernelOrder.limit("best", "maker-best", Side.SIDE_BUY, 3, 100, 2));

        List<Execution> executions = book.match(
                KernelOrder.limit("sell", "taker", Side.SIDE_SELL, 5, 99, 3), 99L);

        assertEquals(List.of("best"), executions.stream().map(Execution::restingOrderId).toList());
        assertEquals(3, executions.getFirst().quantityLots());
        assertEquals(98, book.bestBid());
    }

    @Test
    void samePriceModifyPreservesQueueAndTimestampWhilePriceChangeAppends() {
        IntegerOrderBook book = book();
        book.add(KernelOrder.limit("old", "maker-old", Side.SIDE_SELL, 3, 100, 1));
        book.add(KernelOrder.limit("new", "maker-new", Side.SIDE_SELL, 4, 100, 2));

        ModifyResult samePrice = book.modify(KernelOrder.modify("old", "maker-old", Side.SIDE_SELL, 6, 100L, 9));
        book.add(KernelOrder.limit("at-101", "maker-third", Side.SIDE_SELL, 2, 101, 3));
        ModifyResult moved = book.modify(KernelOrder.modify("new", "maker-new", Side.SIDE_SELL, 5, 101L, 8));

        assertTrue(samePrice.priorityPreserved());
        assertEquals(1, samePrice.after().timestamp());
        assertEquals(List.of("old"), book.orderIdsAt(Side.SIDE_SELL, 100));
        assertFalse(moved.priorityPreserved());
        assertEquals(8, moved.after().timestamp());
        assertEquals(List.of("at-101", "new"), book.orderIdsAt(Side.SIDE_SELL, 101));
    }

    @Test
    void baselineInitializationUsesReferenceIdsDepthOrderingAndIntegerLots() {
        IntegerOrderBook book = book();

        book.initialize(100, 3, 1, 1_500, "normal");
        BookSnapshot snapshot = book.snapshot(2);

        assertEquals(List.of(99L, 98L), snapshot.getBidsList().stream().map(level -> level.getPriceTicks()).toList());
        assertEquals(List.of(101L, 102L), snapshot.getAsksList().stream().map(level -> level.getPriceTicks()).toList());
        assertEquals(1_500, snapshot.getBids(0).getQuantityLots());
        assertEquals(2_500, snapshot.getBids(1).getQuantityLots());
        assertTrue(book.orders().containsKey("l2-bid-99.00000000"));
        assertEquals(200, snapshot.getMidPriceTicksX2());
        assertEquals(2, snapshot.getSpreadTicks());
    }

    @Test
    void agentLevelsAreAdditiveAndOwnerFallsBackAfterCancel() {
        IntegerOrderBook book = book();
        book.updateAgentLevel(
                Side.SIDE_SELL, 101, 3, "MM", "normal", null, 0, null, null, null);
        book.updateAgentLevel(
                Side.SIDE_SELL, 101, 48, "ABUSER", "abuser", "attack-wall", 1,
                "scenario-1", "spoofing_like_wall", "spoofing_like_wall");

        assertEquals(51, book.snapshot(5).getAsks(0).getQuantityLots());
        assertEquals("abuser", book.snapshot(5).getAsks(0).getOwner());
        book.cancel("attack-wall");
        assertEquals(3, book.snapshot(5).getAsks(0).getQuantityLots());
        assertEquals("normal", book.snapshot(5).getAsks(0).getOwner());
    }

    @Test
    void movingAgentOrderByStableIdRemovesOldQueueEntryAndCancelsCleanly() {
        IntegerOrderBook book = book();
        List<BookMutation> mutations = new ArrayList<>();
        book.setMutationListener(mutations::add);
        book.updateAgentLevel(
                Side.SIDE_SELL, 103, 48, "ABUSER", "abuser", "attack-wall", 1,
                "scenario-1", "spoofing_like_wall", "spoofing_like_wall");
        mutations.clear();

        book.updateAgentLevel(
                Side.SIDE_SELL, 104, 48, "ABUSER", "abuser", "attack-wall", 2,
                "scenario-1", "spoofing_like_wall", "spoofing_like_wall");

        assertEquals(1, mutations.size());
        assertEquals(BookMutation.Type.MODIFY, mutations.getFirst().type());
        assertEquals(103, mutations.getFirst().before().priceTicks());
        assertEquals(104, mutations.getFirst().after().priceTicks());
        assertFalse(mutations.getFirst().priorityPreserved());
        assertEquals(List.of(), book.orderIdsAt(Side.SIDE_SELL, 103));
        assertEquals(List.of("attack-wall"), book.orderIdsAt(Side.SIDE_SELL, 104));
        assertEquals(1, book.orders().size());
        book.updateAgentLevel(
                Side.SIDE_SELL, 105, 0, "ABUSER", "abuser", "attack-wall", 3,
                "scenario-1", "spoofing_like_wall", "spoofing_like_wall");
        assertTrue(book.orders().isEmpty());
        assertTrue(book.snapshot(5).getAsksList().isEmpty());
    }

    @Test
    void invalidModifyAndDuplicateOrUnknownOrdersFollowFrozenRules() {
        IntegerOrderBook book = book();
        book.add(KernelOrder.limit("bid", "maker", Side.SIDE_BUY, 2, 99, 0));

        assertThrows(
                IllegalArgumentException.class,
                () -> book.modify(KernelOrder.modify("bid", "maker", Side.SIDE_SELL, 2, 99L, 1)));
        assertThrows(
                IllegalArgumentException.class,
                () -> book.modify(KernelOrder.modify("bid", "other", Side.SIDE_BUY, 2, 99L, 1)));
        assertThrows(
                IllegalArgumentException.class,
                () -> book.add(KernelOrder.limit("bid", "maker", Side.SIDE_BUY, 2, 99, 0)));
        assertEquals(null, book.cancel("missing"));
        assertEquals(null, book.modify(KernelOrder.modify("missing", "maker", Side.SIDE_BUY, 1, 99L, 0)));
    }

    @Test
    void emptyBookSnapshotKeepsDerivedFieldsAbsent() {
        BookSnapshot snapshot = book().snapshot(5);

        assertFalse(snapshot.hasBestBidTicks());
        assertFalse(snapshot.hasBestAskTicks());
        assertFalse(snapshot.hasMidPriceTicksX2());
        assertFalse(snapshot.hasSpreadTicks());
    }

    private static IntegerOrderBook book() {
        return new IntegerOrderBook(1_000_000_000, 1_000_000);
    }
}
