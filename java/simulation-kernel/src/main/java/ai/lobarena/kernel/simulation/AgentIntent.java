package ai.lobarena.kernel.simulation;

import ai.lobarena.exchange.v1.Side;
import java.util.Comparator;

record AgentIntent(
        long tick,
        String agentId,
        Kind kind,
        int sequence,
        int latencyBucket,
        String eventType,
        Side side,
        Long priceTicks,
        long quantityLots,
        String message) implements Comparable<AgentIntent> {
    private static final Comparator<AgentIntent> ORDER = Comparator
            .comparingLong((AgentIntent intent) -> intent.tick())
            .thenComparingInt(intent -> intent.latencyBucket())
            .thenComparing(intent -> intent.agentId())
            .thenComparingInt(intent -> intent.sequence())
            .thenComparing(intent -> intent.kind().wireName);

    enum Kind {
        SET_LEVEL("set_level"),
        MARKET("market");

        private final String wireName;

        Kind(String wireName) {
            this.wireName = wireName;
        }
    }

    @Override
    public int compareTo(AgentIntent other) {
        return ORDER.compare(this, other);
    }
}
