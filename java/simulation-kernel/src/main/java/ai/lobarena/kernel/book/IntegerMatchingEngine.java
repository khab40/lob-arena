package ai.lobarena.kernel.book;

import ai.lobarena.exchange.v1.AddOrder;
import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.CancelOrder;
import ai.lobarena.exchange.v1.EventMetadata;
import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.exchange.v1.ExecuteOrder;
import ai.lobarena.exchange.v1.LobSnapshot;
import ai.lobarena.exchange.v1.ModifyOrder;
import ai.lobarena.kernel.determinism.DeterministicValues;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.function.Consumer;

public final class IntegerMatchingEngine {
    private final IntegerOrderBook book;
    private final String symbol;
    private final String venue;
    private final EventSource source;
    private final int eventHistoryCapacity;
    private final Consumer<ExchangeEvent> eventSink;
    private final Deque<ExchangeEvent> events = new ArrayDeque<>();
    private MutationContext mutationContext = MutationContext.EMPTY;
    private List<ExchangeEvent> submissionEvents;
    private long latestEventSequence;

    public IntegerMatchingEngine(
            IntegerOrderBook book, String symbol, String venue, EventSource source) {
        this(book, symbol, venue, source, Integer.MAX_VALUE, ignored -> {});
    }

    public IntegerMatchingEngine(
            IntegerOrderBook book,
            String symbol,
            String venue,
            EventSource source,
            int eventHistoryCapacity,
            Consumer<ExchangeEvent> eventSink) {
        this.book = book;
        this.symbol = requireText("symbol", symbol);
        this.venue = requireText("venue", venue);
        if (source != EventSource.EVENT_SOURCE_SIMULATION && source != EventSource.EVENT_SOURCE_HISTORICAL) {
            throw new IllegalArgumentException("source must be simulation or historical");
        }
        if (eventHistoryCapacity <= 0) {
            throw new IllegalArgumentException("eventHistoryCapacity must be positive");
        }
        this.source = source;
        this.eventHistoryCapacity = eventHistoryCapacity;
        this.eventSink = eventSink == null ? ignored -> {} : eventSink;
        book.setMutationListener(this::recordMutation);
    }

    public List<ExchangeEvent> submit(KernelOrder order) {
        return submit(order, contextFrom(order));
    }

    public List<ExchangeEvent> submit(KernelOrder order, MutationContext context) {
        List<ExchangeEvent> previousSubmissionEvents = submissionEvents;
        List<ExchangeEvent> emitted = new ArrayList<>();
        submissionEvents = emitted;
        MutationContext previous = mutationContext;
        mutationContext = mergeContext(order, context);
        try {
            switch (order.orderType()) {
                case CANCEL -> book.cancel(order.orderId());
                case MODIFY -> book.modify(order);
                case MARKET -> recordExecutions(order, book.match(order, null));
                case LIMIT -> {
                    List<Execution> executions = book.match(order, order.priceTicks());
                    recordExecutions(order, executions);
                    long filled = executions.stream()
                            .mapToLong(Execution::quantityLots)
                            .reduce(0, Math::addExact);
                    long remaining = order.quantityLots() - filled;
                    if (remaining > 0) {
                        book.add(order.withQuantity(remaining));
                    }
                }
            }
        } finally {
            mutationContext = previous;
            submissionEvents = previousSubmissionEvents;
        }
        return List.copyOf(emitted);
    }

    public ExchangeEvent recordSnapshot(
            long tick,
            int depth,
            Long exchangeTimestampNs,
            Long receivedTimestampNs,
            String scenarioId,
            String scenarioName,
            String scenarioFamily) {
        return recordSnapshot(
                depth,
                new MutationContext(
                        tick,
                        scenarioId,
                        scenarioName,
                        scenarioFamily,
                        null,
                        null,
                        exchangeTimestampNs,
                        receivedTimestampNs));
    }

    public ExchangeEvent recordSnapshot(int depth, MutationContext context) {
        return recordSnapshot(book.snapshot(depth), depth, context);
    }

    public ExchangeEvent recordSnapshot(BookSnapshot snapshot, int depth, MutationContext context) {
        if (snapshot == null) {
            throw new IllegalArgumentException("snapshot must not be null");
        }
        if (depth <= 0) {
            throw new IllegalArgumentException("snapshot depth must be positive");
        }
        MutationContext previous = mutationContext;
        mutationContext = context == null ? MutationContext.EMPTY : context;
        try {
            long snapshotTick = mutationContext.tick() == null ? 0L : mutationContext.tick();
            ExchangeEvent event = ExchangeEvent.newBuilder()
                    .setMetadata(metadata(
                            "snapshot",
                            snapshotTick,
                            mutationContext.scenarioId(),
                            mutationContext.scenarioName(),
                            mutationContext.scenarioFamily()))
                    .setSnapshot(LobSnapshot.newBuilder().setDepth(depth).setBook(snapshot))
                    .build();
            appendEvent(event);
            return event;
        } finally {
            mutationContext = previous;
        }
    }

    public List<ExchangeEvent> events() {
        return List.copyOf(events);
    }

    public long latestEventSequence() {
        return latestEventSequence;
    }

    public long firstRetainedSequence() {
        return events.isEmpty() ? latestEventSequence + 1 : events.getFirst().getMetadata().getSequence();
    }

    public int retainedEventCount() {
        return events.size();
    }

    public List<ExchangeEvent> tailEvents(int limit) {
        if (limit <= 0 || events.isEmpty()) {
            return List.of();
        }
        int skip = Math.max(0, events.size() - limit);
        return events.stream().skip(skip).toList();
    }

    public List<ExchangeEvent> tailEventsBySource(EventSource source, int limit) {
        if (limit <= 0 || events.isEmpty()) {
            return List.of();
        }
        Deque<ExchangeEvent> result = new ArrayDeque<>();
        Iterator<ExchangeEvent> iterator = events.descendingIterator();
        while (iterator.hasNext() && result.size() < limit) {
            ExchangeEvent event = iterator.next();
            if (event.getMetadata().getSource() == source) {
                result.addFirst(event);
            }
        }
        return List.copyOf(result);
    }

    public List<ExchangeEvent> eventsAtTick(long tick) {
        Deque<ExchangeEvent> result = new ArrayDeque<>();
        Iterator<ExchangeEvent> iterator = events.descendingIterator();
        while (iterator.hasNext()) {
            ExchangeEvent event = iterator.next();
            long eventTick = event.getMetadata().getTick();
            if (eventTick < tick) {
                break;
            }
            if (eventTick == tick) {
                result.addFirst(event);
            }
        }
        return List.copyOf(result);
    }

    public List<ExchangeEvent> eventsAfterSequence(long afterSequence, int limit) {
        if (limit <= 0 || events.isEmpty()) {
            return List.of();
        }
        List<ExchangeEvent> result = new ArrayList<>(Math.min(limit, events.size()));
        for (ExchangeEvent event : events) {
            if (event.getMetadata().getSequence() > afterSequence) {
                result.add(event);
                if (result.size() == limit) {
                    break;
                }
            }
        }
        return List.copyOf(result);
    }

    public IntegerOrderBook book() {
        return book;
    }

    public void runWithMutationContext(MutationContext context, Runnable action) {
        MutationContext previous = mutationContext;
        mutationContext = context;
        try {
            action.run();
        } finally {
            mutationContext = previous;
        }
    }

    private void recordExecutions(KernelOrder order, List<Execution> executions) {
        for (Execution execution : executions) {
            String eventId = nextEventId("execute");
            ExchangeEvent event = ExchangeEvent.newBuilder()
                    .setMetadata(metadata(
                            "execute",
                            mutationContext.tick() == null ? order.timestamp() : mutationContext.tick(),
                            order.scenarioId(),
                            order.scenarioName(),
                            order.scenarioFamily(),
                            eventId))
                    .setExecute(ExecuteOrder.newBuilder()
                            .setExecutionId(eventId)
                            .setAggressorOrderId(execution.aggressorOrderId())
                            .setRestingOrderId(execution.restingOrderId())
                            .setAggressorAgentId(execution.aggressorAgentId())
                            .setRestingAgentId(execution.restingAgentId())
                            .setAggressorSide(execution.aggressorSide())
                            .setPriceTicks(execution.priceTicks())
                            .setQuantityLots(execution.quantityLots())
                            .setAggressorRemainingQuantityLots(execution.aggressorRemainingQuantityLots())
                            .setRestingRemainingQuantityLots(execution.restingRemainingQuantityLots()))
                    .build();
            appendEvent(event);
        }
    }

    private void recordMutation(BookMutation mutation) {
        KernelOrder order = mutation.after() == null ? mutation.before() : mutation.after();
        EventMetadata metadata = metadata(
                        mutation.type().name().toLowerCase(),
                        mutationContext.tick() == null ? order.timestamp() : mutationContext.tick(),
                        firstNonNull(mutationContext.scenarioId(), order.scenarioId()),
                        firstNonNull(mutationContext.scenarioName(), order.scenarioName()),
                        firstNonNull(mutationContext.scenarioFamily(), order.scenarioFamily()))
                .build();
        ExchangeEvent.Builder event = ExchangeEvent.newBuilder().setMetadata(metadata);
        switch (mutation.type()) {
            case ADD -> event.setAdd(AddOrder.newBuilder()
                    .setOrderId(order.orderId())
                    .setAgentId(order.agentId())
                    .setSide(order.side())
                    .setPriceTicks(order.priceTicks())
                    .setQuantityLots(order.quantityLots())
                    .setOwner(order.owner()));
            case CANCEL -> event.setCancel(CancelOrder.newBuilder()
                    .setOrderId(order.orderId())
                    .setAgentId(order.agentId())
                    .setSide(order.side())
                    .setPriceTicks(order.priceTicks())
                    .setQuantityLots(order.quantityLots())
                    .setOwner(order.owner()));
            case MODIFY -> event.setModify(ModifyOrder.newBuilder()
                    .setOrderId(mutation.after().orderId())
                    .setAgentId(mutation.after().agentId())
                    .setSide(mutation.after().side())
                    .setPreviousPriceTicks(mutation.before().priceTicks())
                    .setPreviousQuantityLots(mutation.before().quantityLots())
                    .setPriceTicks(mutation.after().priceTicks())
                    .setQuantityLots(mutation.after().quantityLots())
                    .setPriorityPreserved(mutation.priorityPreserved())
                    .setOwner(mutation.after().owner()));
        }
        appendEvent(event.build());
    }

    private void appendEvent(ExchangeEvent event) {
        events.add(event);
        latestEventSequence = event.getMetadata().getSequence();
        while (events.size() > eventHistoryCapacity) {
            events.removeFirst();
        }
        if (submissionEvents != null) {
            submissionEvents.add(event);
        }
        eventSink.accept(event);
    }

    private EventMetadata.Builder metadata(
            String eventType,
            long tick,
            String scenarioId,
            String scenarioName,
            String scenarioFamily) {
        return metadata(eventType, tick, scenarioId, scenarioName, scenarioFamily, nextEventId(eventType));
    }

    private EventMetadata.Builder metadata(
            String eventType,
            long tick,
            String scenarioId,
            String scenarioName,
            String scenarioFamily,
            String eventId) {
        EventMetadata.Builder metadata = EventMetadata.newBuilder()
                .setSchemaVersion(1)
                .setEventId(eventId)
                .setSequence(nextSequence())
                .setSource(mutationContext.source() == null ? source : mutationContext.source())
                .setSymbol(symbol)
                .setVenue(venue)
                .setTick(tick);
        if (mutationContext.sourceSequence() != null) {
            metadata.setSourceSequence(mutationContext.sourceSequence());
        }
        if (mutationContext.exchangeTimestampNs() != null) {
            metadata.setExchangeTimestampNs(mutationContext.exchangeTimestampNs());
        }
        if (mutationContext.receivedTimestampNs() != null) {
            metadata.setReceivedTimestampNs(mutationContext.receivedTimestampNs());
        }
        if (scenarioId != null) {
            metadata.setScenarioId(scenarioId);
        }
        if (scenarioName != null) {
            metadata.setScenarioName(scenarioName);
        }
        if (scenarioFamily != null) {
            metadata.setScenarioFamily(scenarioFamily);
        }
        return metadata;
    }

    private MutationContext contextFrom(KernelOrder order) {
        return new MutationContext(
                order.timestamp(), order.scenarioId(), order.scenarioName(), order.scenarioFamily());
    }

    private MutationContext mergeContext(KernelOrder order, MutationContext context) {
        MutationContext requested = context == null ? MutationContext.EMPTY : context;
        return new MutationContext(
                firstNonNull(requested.tick(), order.timestamp()),
                firstNonNull(requested.scenarioId(), order.scenarioId()),
                firstNonNull(requested.scenarioName(), order.scenarioName()),
                firstNonNull(requested.scenarioFamily(), order.scenarioFamily()),
                requested.source(),
                requested.sourceSequence(),
                requested.exchangeTimestampNs(),
                requested.receivedTimestampNs());
    }

    private long nextSequence() {
        return latestEventSequence + 1L;
    }

    private String nextEventId(String eventType) {
        return DeterministicValues.simulationEventId(venue, eventType, nextSequence());
    }

    private static String requireText(String name, String value) {
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException(name + " must not be empty");
        }
        return value;
    }

    private static <T> T firstNonNull(T preferred, T fallback) {
        return preferred == null ? fallback : preferred;
    }
}
