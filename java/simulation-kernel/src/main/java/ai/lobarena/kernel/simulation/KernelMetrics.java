package ai.lobarena.kernel.simulation;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.MetricValue;
import ai.lobarena.exchange.v1.PriceLevel;
import ai.lobarena.exchange.v1.Side;
import ai.lobarena.kernel.determinism.DeterministicValues;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class KernelMetrics {
    private final long priceUnitNanos;
    private final long quantityUnitNanos;
    private final double tickIntervalSeconds;
    private final Map<String, Long> orderFirstSeenTicks = new HashMap<>();

    KernelMetrics(long priceUnitNanos, long quantityUnitNanos, long tickIntervalNs) {
        this.priceUnitNanos = priceUnitNanos;
        this.quantityUnitNanos = quantityUnitNanos;
        this.tickIntervalSeconds = tickIntervalNs / 1_000_000_000.0;
    }

    FeatureResult calculate(
            long tick,
            BookSnapshot book,
            List<Activity> activities,
            Double previousDepthTopN) {
        List<VisibleLevel> bids = visible(book.getBidsList(), Side.SIDE_BUY, 5);
        List<VisibleLevel> asks = visible(book.getAsksList(), Side.SIDE_SELL, 5);
        double bidDepth = round4(bids.stream().mapToDouble(level -> level.quantity()).sum());
        double askDepth = round4(asks.stream().mapToDouble(level -> level.quantity()).sum());
        double totalDepth = bidDepth + askDepth;
        double imbalance = totalDepth == 0 ? 0 : round4((bidDepth - askDepth) / totalDepth);
        double spreadBps = 0;
        if (book.hasMidPriceTicksX2() && book.hasSpreadTicks() && book.getMidPriceTicksX2() != 0) {
            double mid = price(book.getMidPriceTicksX2()) / 2.0;
            spreadBps = round4(price(book.getSpreadTicks()) / mid * 10_000);
        }
        double depthChangePct = 0;
        if (previousDepthTopN != null && previousDepthTopN > 0) {
            depthChangePct = round4((totalDepth - previousDepthTopN) / previousDepthTopN * 100);
        }

        List<VisibleLevel> visible = new ArrayList<>(bids);
        visible.addAll(asks);
        VisibleLevel largest = visible.stream()
                .max(Comparator.comparingDouble(level -> level.quantity()))
                .orElse(null);
        double wallSizeRatio = 1;
        double distanceFromTouchBps = 0;
        int largeLevelCount = 0;
        if (largest != null) {
            List<Double> nearby = visible.stream()
                    .filter(level -> level.side() == largest.side() && level != largest)
                    .map(level -> level.quantity())
                    .sorted()
                    .toList();
            double nearbySize = median(nearby);
            wallSizeRatio = round4(largest.quantity() / Math.max(nearbySize, 0.0001));
            largeLevelCount = (int) visible.stream()
                    .filter(level -> level.side() == largest.side())
                    .filter(level -> level.quantity() >= nearbySize * 1.5)
                    .count();
            Long touchTicks = largest.side() == Side.SIDE_BUY
                    ? optional(book.hasBestBidTicks(), book.getBestBidTicks())
                    : optional(book.hasBestAskTicks(), book.getBestAskTicks());
            if (touchTicks != null && book.hasMidPriceTicksX2() && book.getMidPriceTicksX2() != 0) {
                double mid = price(book.getMidPriceTicksX2()) / 2.0;
                distanceFromTouchBps = round4(Math.abs(largest.price() - price(touchTicks)) / mid * 10_000);
            }
        }

        List<Activity> cancellations = activities.stream().filter(KernelMetrics::isCancel).toList();
        List<Activity> trades = activities.stream().filter(KernelMetrics::isTrade).toList();
        List<Activity> placements = activities.stream().filter(KernelMetrics::isPlacement).toList();
        double cancelToTradeRatio = round4((double) cancellations.size() / Math.max(1, trades.size()));
        List<Double> completedLifetimes = new ArrayList<>();
        for (Activity activity : activities) {
            if (activity.orderId() == null) {
                continue;
            }
            if (cancellations.contains(activity) || trades.contains(activity)) {
                Long firstTick = orderFirstSeenTicks.remove(activity.orderId());
                if (firstTick != null) {
                    completedLifetimes.add((tick - firstTick) * tickIntervalSeconds * 1_000);
                }
            } else {
                orderFirstSeenTicks.putIfAbsent(activity.orderId(), tick);
            }
        }
        double orderLifetimeMs = completedLifetimes.stream().mapToDouble(value -> value.doubleValue()).max().orElse(0);
        for (long firstTick : orderFirstSeenTicks.values()) {
            orderLifetimeMs = Math.max(orderLifetimeMs, (tick - firstTick) * tickIntervalSeconds * 1_000);
        }

        long linkedEvents = activities.stream()
                .filter(activity -> activity.agentId() != null || activity.orderId() != null)
                .count();
        double participantOrderLinkage = activities.isEmpty() ? 0 : (double) linkedEvents / activities.size();
        double cancelProbability = (double) cancellations.size() / Math.max(1, cancellations.size() + trades.size());
        double executionRatio = (double) trades.size() / Math.max(1, placements.size());
        long replenishments = activities.stream()
                .filter(activity -> containsAny(activity.message(), "maintained", "replenish", "updated"))
                .count();
        double replenishmentRate = (double) replenishments / Math.max(1, placements.size());
        Map<String, List<Side>> sidesByParticipant = new LinkedHashMap<>();
        for (Activity activity : activities) {
            if (activity.agentId() != null && activity.side() != null) {
                sidesByParticipant.computeIfAbsent(activity.agentId(), ignored -> new ArrayList<>()).add(activity.side());
            }
        }
        int switches = 0;
        int observations = 0;
        for (List<Side> sides : sidesByParticipant.values()) {
            for (int index = 1; index < sides.size(); index++) {
                observations++;
                if (sides.get(index - 1) != sides.get(index)) {
                    switches++;
                }
            }
        }

        Map<String, Double> features = new LinkedHashMap<>();
        features.put("spread_bps", spreadBps);
        features.put("depth_top_n", round4(totalDepth));
        features.put("imbalance", imbalance);
        features.put("message_rate", round4(activities.size() / tickIntervalSeconds));
        features.put("cancel_to_trade_ratio", cancelToTradeRatio);
        features.put("order_lifetime_ms", round4(orderLifetimeMs));
        features.put("wall_size_ratio", wallSizeRatio);
        features.put("depth_change_pct", depthChangePct);
        features.put("order_book_imbalance", imbalance);
        features.put("top_n_bid_depth", bidDepth);
        features.put("top_n_ask_depth", askDepth);
        features.put("message_rate_per_sec", round4(activities.size() / tickIntervalSeconds));
        features.put("distance_from_touch_bps", distanceFromTouchBps);
        features.put("cancel_probability", round4(cancelProbability));
        features.put("execution_ratio", round4(executionRatio));
        features.put("replenishment_rate", round4(replenishmentRate));
        features.put("side_switching_rate", round4((double) switches / Math.max(1, observations)));
        features.put("participant_order_linkage", round4(participantOrderLinkage));
        features.put("large_level_count", (double) largeLevelCount);

        double wallComponent = Math.min(wallSizeRatio / 8.0, 1);
        double lifetimeComponent = orderLifetimeMs >= 500 && orderLifetimeMs <= 5_000 ? 1 : 0.25;
        double cancelComponent = Math.max(Math.min(cancelToTradeRatio / 3.0, 1), cancelProbability);
        double imbalanceComponent = Math.min(Math.abs(imbalance) / 0.5, 1);
        double spoofing = round4(Math.max(
                wallComponent * 0.6 + lifetimeComponent * 0.2 + cancelComponent * 0.1 + imbalanceComponent * 0.1,
                0));
        double dominantDepth = Math.max(askDepth, bidDepth);
        double oppositeDepth = Math.min(askDepth, bidDepth);
        double layering = round4(
                Math.min(wallSizeRatio / 5.0, 1) * 0.15
                        + Math.min(Math.abs(imbalance) / 0.35, 1) * 0.15
                        + (dominantDepth > oppositeDepth * 1.4 ? 1 : 0.35) * 0.2
                        + Math.min(replenishmentRate, 1) * 0.15
                        + (largeLevelCount >= 3 ? 1 : 0) * 0.35);
        double quoteStuffing = round4(
                Math.min(features.get("message_rate_per_sec") / 18.0, 1) * 0.75
                        + Math.min(cancelToTradeRatio / 8.0, 1) * 0.25);
        double liquidity = round4(
                Math.min(Math.abs(Math.min(depthChangePct, 0)) / 45.0, 1) * 0.45
                        + Math.min(spreadBps / 1.0, 1) * 0.35
                        + Math.min(Math.abs(imbalance) / 0.55, 1) * 0.2);
        Map<String, Double> detectors = Map.of(
                "layering_like", Math.min(layering, 1),
                "liquidity_shock", Math.min(liquidity, 1),
                "quote_stuffing", Math.min(quoteStuffing, 1),
                "spoofing_like", Math.min(spoofing, 1));
        return new FeatureResult(features, detectors);
    }

    List<MetricValue> toProto(long tick, FeatureResult result) {
        Map<String, Double> values = new HashMap<>();
        values.put("tick", (double) tick);
        result.features().forEach((name, value) -> values.put("market." + name, value));
        result.detectors().forEach((name, value) -> values.put("detector." + name + ".confidence", value));
        return values.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(entry -> MetricValue.newBuilder()
                        .setName(entry.getKey())
                        .setQuantizedValue(DeterministicValues.quantizeMetric(Double.toString(entry.getValue()), 6))
                        .setDecimalScale(6)
                        .build())
                .toList();
    }

    double topDepth(BookSnapshot book) {
        return round4(
                visible(book.getBidsList(), Side.SIDE_BUY, 5).stream().mapToDouble(level -> level.quantity()).sum()
                        + visible(book.getAsksList(), Side.SIDE_SELL, 5).stream().mapToDouble(level -> level.quantity()).sum());
    }

    record FeatureResult(Map<String, Double> features, Map<String, Double> detectors) {}

    private List<VisibleLevel> visible(List<PriceLevel> levels, Side side, int depth) {
        return levels.stream()
                .limit(depth)
                .map(level -> new VisibleLevel(side, price(level.getPriceTicks()), quantity(level.getQuantityLots())))
                .toList();
    }

    private double price(long ticks) {
        return BigDecimal.valueOf(ticks)
                .multiply(BigDecimal.valueOf(priceUnitNanos))
                .movePointLeft(9)
                .doubleValue();
    }

    private double quantity(long lots) {
        return BigDecimal.valueOf(lots)
                .multiply(BigDecimal.valueOf(quantityUnitNanos))
                .movePointLeft(9)
                .doubleValue();
    }

    private static boolean isCancel(Activity activity) {
        return lower(activity.stage()).contains("cancel") || lower(activity.message()).contains("cancel");
    }

    private static boolean isTrade(Activity activity) {
        return "trade".equals(activity.type()) || lower(activity.message()).contains("execut");
    }

    private static boolean isPlacement(Activity activity) {
        return containsAny(activity.message(), "placed", "updated", "maintained");
    }

    private static boolean containsAny(String value, String... tokens) {
        String normalized = lower(value);
        for (String token : tokens) {
            if (normalized.contains(token)) {
                return true;
            }
        }
        return false;
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private static double median(List<Double> values) {
        if (values.isEmpty()) {
            return 1;
        }
        int middle = values.size() / 2;
        if (values.size() % 2 == 1) {
            return values.get(middle);
        }
        return (values.get(middle - 1) + values.get(middle)) / 2;
    }

    private static double round4(double value) {
        return BigDecimal.valueOf(value).setScale(4, RoundingMode.HALF_EVEN).doubleValue();
    }

    private static Long optional(boolean present, long value) {
        return present ? value : null;
    }

    private record VisibleLevel(Side side, double price, double quantity) {}
}
