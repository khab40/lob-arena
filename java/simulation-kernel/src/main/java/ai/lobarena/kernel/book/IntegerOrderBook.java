package ai.lobarena.kernel.book;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.PriceLevel;
import ai.lobarena.exchange.v1.Side;
import ai.lobarena.kernel.determinism.DeterministicValues;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import java.util.function.Consumer;

public final class IntegerOrderBook {
    private static final String NORMAL_OWNER = "normal";

    private final NavigableMap<Long, List<KernelOrder>> bids = new TreeMap<>(Comparator.reverseOrder());
    private final NavigableMap<Long, List<KernelOrder>> asks = new TreeMap<>();
    private final Map<String, KernelOrder> orders = new LinkedHashMap<>();
    private final long priceTickSizeNanos;
    private final long quantityLotSizeNanos;
    private Consumer<BookMutation> mutationListener = ignored -> {};

    public IntegerOrderBook(long priceTickSizeNanos, long quantityLotSizeNanos) {
        if (priceTickSizeNanos <= 0 || quantityLotSizeNanos <= 0) {
            throw new IllegalArgumentException("price and quantity unit sizes must be positive");
        }
        this.priceTickSizeNanos = priceTickSizeNanos;
        this.quantityLotSizeNanos = quantityLotSizeNanos;
    }

    public void setMutationListener(Consumer<BookMutation> listener) {
        mutationListener = listener == null ? ignored -> {} : listener;
    }

    public void initialize(
            long referencePriceTicks,
            int levels,
            long tickSpacingTicks,
            long baseQuantityLots,
            String owner) {
        if (referencePriceTicks <= 0 || levels < 0 || tickSpacingTicks <= 0 || baseQuantityLots <= 0) {
            throw new IllegalArgumentException("invalid baseline book configuration");
        }
        bids.clear();
        asks.clear();
        orders.clear();
        if (1_000_000_000L % quantityLotSizeNanos != 0) {
            throw new IllegalArgumentException("quantity unit must represent whole units exactly");
        }
        long lotsPerWholeUnit = 1_000_000_000L / quantityLotSizeNanos;
        for (int index = 0; index < levels; index++) {
            long distance = Math.multiplyExact(index + 1L, tickSpacingTicks);
            long quantity = Math.addExact(baseQuantityLots, Math.multiplyExact(index, lotsPerWholeUnit));
            updateLevel(Side.SIDE_BUY, referencePriceTicks - distance, quantity, owner);
            updateLevel(Side.SIDE_SELL, referencePriceTicks + distance, quantity, owner);
        }
    }

    public void add(KernelOrder order) {
        if (order.orderType() != OrderType.LIMIT) {
            throw new IllegalArgumentException("only limit orders can rest in the book");
        }
        if (orders.containsKey(order.orderId())) {
            throw new IllegalArgumentException("duplicate order id: " + order.orderId());
        }
        addWithoutMutation(order);
        mutationListener.accept(BookMutation.add(order));
    }

    public KernelOrder cancel(String orderId) {
        KernelOrder order = orders.remove(orderId);
        if (order == null) {
            return null;
        }
        NavigableMap<Long, List<KernelOrder>> levels = levels(order.side());
        List<KernelOrder> queue = levels.get(order.priceTicks());
        queue.removeIf(candidate -> candidate.orderId().equals(orderId));
        if (queue.isEmpty()) {
            levels.remove(order.priceTicks());
        }
        mutationListener.accept(BookMutation.cancel(order));
        return order;
    }

    public ModifyResult modify(KernelOrder request) {
        KernelOrder existing = orders.get(request.orderId());
        if (existing == null) {
            return null;
        }
        if (request.orderType() != OrderType.MODIFY) {
            throw new IllegalArgumentException("modify requires a modify request");
        }
        if (request.side() != existing.side()) {
            throw new IllegalArgumentException("modify order cannot change side");
        }
        if (!request.agentId().equals(existing.agentId())) {
            throw new IllegalArgumentException("modify order cannot change agent ownership");
        }
        long newPrice = request.priceTicks() == null ? existing.priceTicks() : request.priceTicks();
        boolean priorityPreserved = newPrice == existing.priceTicks();
        long newTimestamp = priorityPreserved ? existing.timestamp() : request.timestamp();
        KernelOrder updated = new KernelOrder(
                existing.orderId(),
                existing.agentId(),
                existing.side(),
                request.quantityLots(),
                newPrice,
                OrderType.LIMIT,
                newTimestamp,
                firstNonNull(request.scenarioId(), existing.scenarioId()),
                firstNonNull(request.scenarioName(), existing.scenarioName()),
                firstNonNull(request.scenarioFamily(), existing.scenarioFamily()),
                existing.owner());

        NavigableMap<Long, List<KernelOrder>> sideLevels = levels(existing.side());
        List<KernelOrder> oldQueue = sideLevels.get(existing.priceTicks());
        if (priorityPreserved) {
            int index = indexOf(oldQueue, existing.orderId());
            oldQueue.set(index, updated);
        } else {
            oldQueue.removeIf(candidate -> candidate.orderId().equals(existing.orderId()));
            if (oldQueue.isEmpty()) {
                sideLevels.remove(existing.priceTicks());
            }
            sideLevels.computeIfAbsent(newPrice, ignored -> new ArrayList<>()).add(updated);
        }
        orders.put(updated.orderId(), updated);
        mutationListener.accept(BookMutation.modify(existing, updated, priorityPreserved));
        return new ModifyResult(existing, updated, priorityPreserved);
    }

    public List<Execution> match(KernelOrder aggressor, Long limitPriceTicks) {
        if (aggressor.orderType() != OrderType.LIMIT && aggressor.orderType() != OrderType.MARKET) {
            throw new IllegalArgumentException("only limit or market orders can match");
        }
        NavigableMap<Long, List<KernelOrder>> opposite =
                aggressor.side() == Side.SIDE_BUY ? asks : bids;
        long remaining = aggressor.quantityLots();
        List<Execution> executions = new ArrayList<>();
        for (long price : new ArrayList<>(opposite.keySet())) {
            if (!crosses(aggressor.side(), price, limitPriceTicks)) {
                break;
            }
            if (remaining == 0) {
                break;
            }
            List<KernelOrder> queue = opposite.get(price);
            List<KernelOrder> updatedQueue = new ArrayList<>();
            for (KernelOrder resting : queue) {
                if (remaining == 0) {
                    updatedQueue.add(resting);
                    continue;
                }
                long traded = Math.min(remaining, resting.quantityLots());
                remaining -= traded;
                long restingRemaining = resting.quantityLots() - traded;
                executions.add(new Execution(
                        aggressor.orderId(),
                        resting.orderId(),
                        aggressor.agentId(),
                        resting.agentId(),
                        aggressor.side(),
                        price,
                        traded,
                        remaining,
                        restingRemaining,
                        aggressor.timestamp(),
                        firstNonNull(aggressor.scenarioId(), resting.scenarioId()),
                        firstNonNull(aggressor.scenarioName(), resting.scenarioName()),
                        firstNonNull(aggressor.scenarioFamily(), resting.scenarioFamily())));
                if (restingRemaining == 0) {
                    orders.remove(resting.orderId());
                } else {
                    KernelOrder updated = resting.withQuantity(restingRemaining);
                    orders.put(updated.orderId(), updated);
                    updatedQueue.add(updated);
                }
            }
            if (updatedQueue.isEmpty()) {
                opposite.remove(price);
            } else {
                opposite.put(price, updatedQueue);
            }
        }
        return List.copyOf(executions);
    }

    public void updateLevel(Side side, long priceTicks, long quantityLots, String owner) {
        if (quantityLots <= 0) {
            removeLevel(side, priceTicks);
            return;
        }
        NavigableMap<Long, List<KernelOrder>> sideLevels = levels(side);
        List<KernelOrder> existing = new ArrayList<>(sideLevels.getOrDefault(priceTicks, List.of()));
        for (KernelOrder order : existing) {
            orders.remove(order.orderId());
        }
        KernelOrder replacement = syntheticOrder(side, priceTicks, quantityLots, owner);
        sideLevels.put(priceTicks, new ArrayList<>(List.of(replacement)));
        orders.put(replacement.orderId(), replacement);
        KernelOrder replaced = existing.stream()
                .filter(item -> item.orderId().equals(replacement.orderId()))
                .findFirst()
                .orElse(null);
        existing.stream()
                .filter(item -> !item.orderId().equals(replacement.orderId()))
                .forEach(item -> mutationListener.accept(BookMutation.cancel(item)));
        if (replaced == null) {
            mutationListener.accept(BookMutation.add(replacement));
        } else if (!replaced.equals(replacement)) {
            mutationListener.accept(BookMutation.modify(replaced, replacement, true));
        }
    }

    public void updateAgentLevel(
            Side side,
            long priceTicks,
            long quantityLots,
            String agentId,
            String owner,
            String orderId,
            long timestamp,
            String scenarioId,
            String scenarioName,
            String scenarioFamily) {
        String resolvedOrderId = orderId == null ? agentLevelOrderId(side, priceTicks, agentId) : orderId;
        if (quantityLots <= 0) {
            cancel(resolvedOrderId);
            return;
        }
        KernelOrder replaced = orders.get(resolvedOrderId);
        boolean priorityPreserved = false;
        if (replaced != null) {
            NavigableMap<Long, List<KernelOrder>> priorSide = levels(replaced.side());
            List<KernelOrder> priorQueue =
                    new ArrayList<>(priorSide.getOrDefault(replaced.priceTicks(), List.of()));
            priorityPreserved = replaced.side() == side && replaced.priceTicks() == priceTicks;
            priorQueue.removeIf(item -> item.orderId().equals(resolvedOrderId));
            if (priorQueue.isEmpty()) {
                priorSide.remove(replaced.priceTicks());
            } else {
                priorSide.put(replaced.priceTicks(), priorQueue);
            }
            orders.remove(resolvedOrderId);
        }
        NavigableMap<Long, List<KernelOrder>> sideLevels = levels(side);
        List<KernelOrder> queue = new ArrayList<>(sideLevels.getOrDefault(priceTicks, List.of()));
        queue.removeIf(item -> item.orderId().equals(resolvedOrderId));
        KernelOrder updated = new KernelOrder(
                resolvedOrderId, agentId, side, quantityLots, priceTicks, OrderType.LIMIT, timestamp,
                scenarioId, scenarioName, scenarioFamily, owner);
        queue.add(updated);
        sideLevels.put(priceTicks, queue);
        orders.put(updated.orderId(), updated);
        if (replaced == null) {
            mutationListener.accept(BookMutation.add(updated));
        } else if (!replaced.equals(updated)) {
            mutationListener.accept(BookMutation.modify(replaced, updated, priorityPreserved));
        }
    }

    public void ensureLevelMinimum(Side side, long priceTicks, long minimumLots, String agentId, String owner) {
        String orderId = agentLevelOrderId(side, priceTicks, agentId);
        long quantityWithoutAgent = levels(side).getOrDefault(priceTicks, List.of()).stream()
                .filter(order -> !order.orderId().equals(orderId))
                .mapToLong(KernelOrder::quantityLots)
                .reduce(0, Math::addExact);
        long agentLots = Math.max(0, minimumLots - quantityWithoutAgent);
        updateAgentLevel(side, priceTicks, agentLots, agentId, owner, orderId, 0, null, null, null);
    }

    public void removeLevel(Side side, long priceTicks) {
        List<KernelOrder> removed = levels(side).remove(priceTicks);
        if (removed == null) {
            return;
        }
        for (KernelOrder order : removed) {
            orders.remove(order.orderId());
            mutationListener.accept(BookMutation.cancel(order));
        }
    }

    public Long bestBid() {
        return bids.isEmpty() ? null : bids.firstKey();
    }

    public Long bestAsk() {
        return asks.isEmpty() ? null : asks.firstKey();
    }

    public BookSnapshot snapshot(int depth) {
        if (depth <= 0) {
            throw new IllegalArgumentException("snapshot depth must be positive");
        }
        BookSnapshot.Builder snapshot = BookSnapshot.newBuilder();
        bids.entrySet().stream().limit(depth).forEach(entry -> snapshot.addBids(priceLevel(entry)));
        asks.entrySet().stream().limit(depth).forEach(entry -> snapshot.addAsks(priceLevel(entry)));
        Long bestBid = bestBid();
        Long bestAsk = bestAsk();
        if (bestBid != null) {
            snapshot.setBestBidTicks(bestBid);
        }
        if (bestAsk != null) {
            snapshot.setBestAskTicks(bestAsk);
        }
        if (bestBid != null && bestAsk != null) {
            snapshot.setMidPriceTicksX2(DeterministicValues.midpointTicksX2(bestBid, bestAsk));
            snapshot.setSpreadTicks(Math.subtractExact(bestAsk, bestBid));
        }
        return snapshot.build();
    }

    public Map<String, KernelOrder> orders() {
        return Collections.unmodifiableMap(new HashMap<>(orders));
    }

    public List<String> orderIdsAt(Side side, long priceTicks) {
        return levels(side).getOrDefault(priceTicks, List.of()).stream().map(KernelOrder::orderId).toList();
    }

    public long levelQuantity(Side side, long priceTicks) {
        return levels(side).getOrDefault(priceTicks, List.of()).stream()
                .mapToLong(KernelOrder::quantityLots)
                .reduce(0, Math::addExact);
    }

    public double levelQuantityAsReferenceDouble(Side side, long priceTicks) {
        BigDecimal exactBinarySum = BigDecimal.ZERO;
        for (KernelOrder order : levels(side).getOrDefault(priceTicks, List.of())) {
            double value = BigDecimal.valueOf(order.quantityLots())
                    .multiply(BigDecimal.valueOf(quantityLotSizeNanos))
                    .movePointLeft(9)
                    .doubleValue();
            exactBinarySum = exactBinarySum.add(new BigDecimal(value));
        }
        return exactBinarySum.doubleValue();
    }

    public List<Long> prices(Side side, int depth) {
        return levels(side).keySet().stream().limit(depth).toList();
    }

    private void addWithoutMutation(KernelOrder order) {
        levels(order.side()).computeIfAbsent(order.priceTicks(), ignored -> new ArrayList<>()).add(order);
        orders.put(order.orderId(), order);
    }

    private KernelOrder syntheticOrder(Side side, long priceTicks, long quantityLots, String owner) {
        return new KernelOrder(
                syntheticOrderId(side, priceTicks),
                owner,
                side,
                quantityLots,
                priceTicks,
                OrderType.LIMIT,
                0,
                null,
                null,
                null,
                owner);
    }

    private String syntheticOrderId(Side side, long priceTicks) {
        return "l2-" + bookSide(side) + "-" + formattedPrice(priceTicks);
    }

    private String agentLevelOrderId(Side side, long priceTicks, String agentId) {
        return syntheticOrderId(side, priceTicks) + "-" + agentId;
    }

    private String formattedPrice(long priceTicks) {
        return BigDecimal.valueOf(priceTicks)
                .multiply(BigDecimal.valueOf(priceTickSizeNanos))
                .movePointLeft(9)
                .setScale(8, RoundingMode.HALF_EVEN)
                .toPlainString();
    }

    private PriceLevel priceLevel(Map.Entry<Long, List<KernelOrder>> entry) {
        long quantity = entry.getValue().stream()
                .mapToLong(KernelOrder::quantityLots)
                .reduce(0, Math::addExact);
        String owner = entry.getValue().stream()
                .map(KernelOrder::owner)
                .filter(candidate -> !NORMAL_OWNER.equals(candidate))
                .findFirst()
                .orElse(NORMAL_OWNER);
        return PriceLevel.newBuilder()
                .setPriceTicks(entry.getKey())
                .setQuantityLots(quantity)
                .setOwner(owner)
                .build();
    }

    private NavigableMap<Long, List<KernelOrder>> levels(Side side) {
        return side == Side.SIDE_BUY ? bids : asks;
    }

    private static boolean crosses(Side aggressorSide, long restingPrice, Long limitPrice) {
        if (limitPrice == null) {
            return true;
        }
        return aggressorSide == Side.SIDE_BUY ? restingPrice <= limitPrice : restingPrice >= limitPrice;
    }

    private static int indexOf(List<KernelOrder> orders, String orderId) {
        for (int index = 0; index < orders.size(); index++) {
            if (orders.get(index).orderId().equals(orderId)) {
                return index;
            }
        }
        throw new IllegalStateException("order index is inconsistent");
    }

    private static String bookSide(Side side) {
        return side == Side.SIDE_BUY ? "bid" : "ask";
    }

    private static <T> T firstNonNull(T preferred, T fallback) {
        return preferred == null ? fallback : preferred;
    }
}
