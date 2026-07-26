package ai.lobarena.controlplane;

import ai.lobarena.exchange.v1.BookSnapshot;
import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.exchange.v1.PriceLevel;
import ai.lobarena.exchange.v1.Side;
import ai.lobarena.kernel.book.IntegerMatchingEngine;
import ai.lobarena.kernel.book.IntegerOrderBook;
import ai.lobarena.kernel.book.KernelOrder;
import ai.lobarena.kernel.book.MutationContext;
import ai.lobarena.kernel.determinism.EventOrderKey;
import ai.lobarena.kernel.determinism.EventPhase;
import ai.lobarena.kernel.determinism.DeterministicValues;
import ai.lobarena.kernel.hashing.CanonicalHashes;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HexFormat;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.scheduling.annotation.Scheduled;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

final class LiveArenaService {
    private static final long UNIT_NANOS = 1_000_000L;
    private static final long REFERENCE_PRICE_TICKS = 68_125_000L;
    private static final long LEVEL_SPACING_TICKS = 1_000L;
    private static final long BASE_QUANTITY_LOTS = 1_500L;
    private static final int BASELINE_LEVELS = 12;
    private static final int SNAPSHOT_DEPTH = 12;
    private static final int EVENT_WINDOW = 100;
    private static final int AGENT_EVENT_WINDOW = 20;

    private final ObjectMapper mapper;
    private final AgentOrchestrator orchestrator;
    private final ArenaJournal journal;
    private final HistoricalMarketDataSource historical;
    private final HistoricalCsvMarketDataSource historicalCsv;
    private final Deque<ObjectNode> agentEvents = new ArrayDeque<>();
    private final List<ObjectNode> incidents = new ArrayList<>();
    private final Set<String> incidentKeys = new HashSet<>();
    private final Map<String, List<Long>> detectorAlertTicks = new LinkedHashMap<>();
    private final long defaultMasterSeed;

    private IntegerMatchingEngine matching;
    private volatile long tick;
    private volatile boolean running;
    private volatile int metricsIncidentCount;
    private int scenarioCounter;
    private int incidentCounter;
    private List<String> activeAgentIds = List.of();
    private LiveScenario scenario;
    private double previousDepth;
    private String replaySourceType;
    private long replayMasterSeed;
    private volatile boolean lobsterKernelReplay;
    private final Set<Long> lobsterBidPrices = new HashSet<>();
    private final Set<Long> lobsterAskPrices = new HashSet<>();

    LiveArenaService(ObjectMapper mapper, AgentOrchestrator orchestrator, ArenaJournal journal) {
        this(
                mapper,
                orchestrator,
                journal,
                Path.of("../../data/processed/lobster"),
                Path.of("../../data/historical"),
                250,
                42);
    }

    LiveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            Path historicalDataDir,
            int historicalRowsPerTick) {
        this(
                mapper,
                orchestrator,
                journal,
                historicalDataDir,
                Path.of("../../data/historical"),
                historicalRowsPerTick,
                42);
    }

    LiveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            Path historicalDataDir,
            Path historicalCsvDataDir,
            int historicalRowsPerTick) {
        this(
                mapper,
                orchestrator,
                journal,
                historicalDataDir,
                historicalCsvDataDir,
                historicalRowsPerTick,
                42);
    }

    LiveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            Path historicalDataDir,
            Path historicalCsvDataDir,
            int historicalRowsPerTick,
            long masterSeed) {
        this.mapper = mapper;
        this.orchestrator = orchestrator;
        this.journal = journal;
        this.historical = new HistoricalMarketDataSource(mapper, historicalDataDir, historicalRowsPerTick);
        this.historicalCsv =
                new HistoricalCsvMarketDataSource(mapper, historicalCsvDataDir, historicalRowsPerTick);
        this.defaultMasterSeed = masterSeed;
        this.replayMasterSeed = masterSeed;
        this.matching = newMatchingEngine();
        this.previousDepth = topDepth(matching.book().snapshot(5));
    }

    synchronized JsonNode state() {
        if (historical.loaded() && !lobsterKernelReplay) {
            return historical.state();
        }
        return buildState();
    }

    JsonNode metricsState() {
        if (historical.loaded() && !lobsterKernelReplay) {
            return historical.metricsState();
        }
        return mapper.createObjectNode()
                .put("tick", tick)
                .put("running", running)
                .put("incidents_count", metricsIncidentCount);
    }

    synchronized JsonNode start() {
        if (historical.loaded() && !lobsterKernelReplay) {
            return historical.start();
        }
        running = true;
        return buildState();
    }

    synchronized JsonNode pause() {
        if (historical.loaded() && !lobsterKernelReplay) {
            return historical.pause();
        }
        running = false;
        return buildState();
    }

    synchronized JsonNode reset() {
        if (historical.loaded() && !lobsterKernelReplay) {
            return historical.reset();
        }
        if (historicalCsv.loaded()) {
            historicalCsv.reset();
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if (lobsterKernelReplay) {
            historical.reset();
            lobsterBidPrices.clear();
            lobsterAskPrices.clear();
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        resetRuntime(newMatchingEngine());
        return buildState();
    }

    private void resetRuntime(IntegerMatchingEngine replacement) {
        running = false;
        tick = 0;
        scenario = null;
        agentEvents.clear();
        incidents.clear();
        metricsIncidentCount = 0;
        incidentKeys.clear();
        detectorAlertTicks.clear();
        activeAgentIds = List.of();
        matching = replacement;
        lobsterBidPrices.clear();
        lobsterAskPrices.clear();
        previousDepth = topDepth(matching.book().snapshot(5));
    }

    synchronized JsonNode launchScenario(String family) {
        if (historical.loaded() && !lobsterKernelReplay) {
            throw new IllegalArgumentException("scenarios are unavailable for historical market data");
        }
        if (kernelHistoricalLoaded() && !"hybrid".equals(replaySourceType)) {
            throw new IllegalArgumentException("scenarios require the hybrid historical source");
        }
        String normalized = normalizeScenario(family);
        scenarioCounter++;
        String scenarioAgentId = kernelHistoricalLoaded() ? "SYN:ABUSER_01" : "ABUSER_01";
        long scenarioSeed = kernelHistoricalLoaded()
                ? DeterministicValues.deriveStreamSeed(
                        replayMasterSeed,
                        "hybrid:" + replayDatasetId() + ":" + normalized + ":" + scenarioCounter)
                : 0L;
        scenario = new LiveScenario(
                "SCN-%06d".formatted(scenarioCounter),
                normalized,
                displayName(normalized),
                scenarioAgentId,
                tick + 1,
                scenarioSeed);
        running = true;
        addAgentEvent(event("red_team", scenarioAgentId, "scenario armed")
                .put("scenario_id", scenario.id())
                .put("scenario_name", scenario.name())
                .put("scenario_family", scenario.family())
                .put("stage", "armed"));
        journal.append("attacks/attacks.jsonl", scenarioJson());
        journal.append("labels/scenario_labels.jsonl", groundTruthLabel());
        return scenarioJson();
    }

    synchronized JsonNode incident(String incidentId) {
        return incidents.stream()
                .filter(item -> incidentId.equals(item.path("id").textValue()))
                .findFirst()
                .map(ObjectNode::deepCopy)
                .orElse(null);
    }

    synchronized JsonNode incidents() {
        ArrayNode result = mapper.createArrayNode();
        incidents.forEach(result::add);
        return result;
    }

    synchronized JsonNode exchangeEvents(long afterSequence, int limit) {
        if (historical.loaded() && !lobsterKernelReplay) {
            ObjectNode replay = mapper.createObjectNode();
            replay.putArray("events");
            return replay.put("after_sequence", afterSequence)
                    .put("next_after_sequence", afterSequence)
                    .put("latest_sequence", 0)
                    .put("has_more", false);
        }
        List<ExchangeEvent> page = matching.eventsAfterSequence(afterSequence, limit);
        ArrayNode events = mapper.createArrayNode();
        page.stream()
                .map(this::exchangeEventJson)
                .forEach(events::add);
        long latest = matching.latestEventSequence();
        long next = events.isEmpty() ? afterSequence : events.get(events.size() - 1).path("sequence").longValue();
        return mapper.createObjectNode()
                .set("events", events)
                .put("after_sequence", afterSequence)
                .put("next_after_sequence", next)
                .put("latest_sequence", latest)
                .put("has_more", next < latest);
    }

    @Scheduled(fixedDelayString = "${lob.arena.tick-interval-ms:500}")
    synchronized void scheduledTick() {
        if (historical.loaded() && !lobsterKernelReplay) {
            historical.advance();
            return;
        }
        if (running) {
            advance();
        }
    }

    synchronized JsonNode stepForTest() {
        if (historical.loaded() && !lobsterKernelReplay) {
            historical.start();
            historical.advance();
            return historical.state();
        }
        advance();
        return buildState();
    }

    synchronized long defaultMasterSeed() {
        return defaultMasterSeed;
    }

    synchronized JsonNode loadDataSource(String sourceType, String datasetId) {
        return loadDataSource(sourceType, datasetId, defaultMasterSeed);
    }

    synchronized JsonNode loadDataSource(String sourceType, String datasetId, long masterSeed) {
        running = false;
        replayMasterSeed = masterSeed;
        if ("historical".equals(sourceType)) {
            if (historicalCsv.supports(datasetId)) {
                historical.clear();
                lobsterKernelReplay = false;
                replaySourceType = "historical";
                historicalCsv.load(datasetId);
                resetRuntime(newHistoricalMatchingEngine());
                return buildState();
            }
            historicalCsv.clear();
            replaySourceType = "historical";
            lobsterKernelReplay = false;
            historical.load(datasetId);
            lobsterKernelReplay = true;
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if ("hybrid".equals(sourceType)) {
            if (historicalCsv.supports(datasetId)) {
                historical.clear();
                lobsterKernelReplay = false;
                replaySourceType = "hybrid";
                historicalCsv.load(datasetId);
                resetRuntime(newHistoricalMatchingEngine());
                return buildState();
            }
            historicalCsv.clear();
            lobsterKernelReplay = false;
            historical.load(datasetId);
            lobsterKernelReplay = true;
            replaySourceType = "hybrid";
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if ("synthetic".equals(sourceType)) {
            historical.clear();
            historicalCsv.clear();
            lobsterKernelReplay = false;
            replaySourceType = null;
            return reset();
        }
        throw new IllegalArgumentException("unknown market data source");
    }

    synchronized JsonNode historicalCsvDatasets() {
        ArrayNode result = mapper.createArrayNode();
        historicalCsv.datasets().forEach(result::add);
        historical.datasets().forEach(result::add);
        return result;
    }

    synchronized JsonNode runReplayComparison(String datasetId, String scenarioFamily, int maxTicks) {
        return runReplayComparison(datasetId, scenarioFamily, maxTicks, defaultMasterSeed);
    }

    synchronized JsonNode runReplayComparison(
            String datasetId, String scenarioFamily, int maxTicks, long masterSeed) {
        if (maxTicks < 1 || maxTicks > 100_000) {
            throw new IllegalArgumentException("max_ticks must be between 1 and 100000");
        }
        String normalizedScenario = normalizeScenario(scenarioFamily);
        scenarioCounter = 0;
        incidentCounter = 0;
        ObjectNode control = runReplayOnce("historical", datasetId, null, maxTicks, masterSeed);
        ObjectNode hybrid = runReplayOnce("hybrid", datasetId, normalizedScenario, maxTicks, masterSeed);
        scenarioCounter = 0;
        incidentCounter = 0;
        ObjectNode repeatedControl =
                runReplayOnce("historical", datasetId, null, maxTicks, masterSeed);
        ObjectNode repeatedHybrid =
                runReplayOnce("hybrid", datasetId, normalizedScenario, maxTicks, masterSeed);
        ObjectNode result = mapper.createObjectNode()
                .put("schema_version", "historical_replay_comparison_v1")
                .put("dataset_id", datasetId)
                .put("master_seed", masterSeed)
                .put("events_sha256", replayEventsSha256())
                .set("control", control)
                .set("hybrid", hybrid);
        ObjectNode determinism = result.putObject("determinism");
        determinism.put(
                "control_stream_match",
                control.path("stream_hash").equals(repeatedControl.path("stream_hash")));
        determinism.put(
                "hybrid_stream_match",
                hybrid.path("stream_hash").equals(repeatedHybrid.path("stream_hash")));
        determinism.put(
                "control_trace_match",
                control.path("validation_trace").equals(repeatedControl.path("validation_trace")));
        determinism.put(
                "hybrid_trace_match",
                hybrid.path("validation_trace").equals(repeatedHybrid.path("validation_trace")));
        determinism.put(
                "historical_snapshot_match",
                control.path("historical_snapshot_stream_hash")
                                .equals(repeatedControl.path("historical_snapshot_stream_hash"))
                        && hybrid.path("historical_snapshot_stream_hash")
                                .equals(repeatedHybrid.path("historical_snapshot_stream_hash")));
        determinism.put("control_repeat_stream_hash", repeatedControl.path("stream_hash").asText());
        determinism.put("hybrid_repeat_stream_hash", repeatedHybrid.path("stream_hash").asText());
        ObjectNode impact = result.putObject("realism_impact");
        impact.put(
                "canonical_event_count_delta",
                hybrid.path("canonical_event_count").longValue()
                        - control.path("canonical_event_count").longValue());
        impact.put(
                "final_depth_delta",
                round(hybrid.path("realism").path("final_depth_top_n").doubleValue()
                        - control.path("realism").path("final_depth_top_n").doubleValue()));
        impact.put(
                "final_spread_delta",
                round(hybrid.path("realism").path("final_spread").doubleValue()
                        - control.path("realism").path("final_spread").doubleValue()));
        journal.append("historical-replay/comparisons.jsonl", result);
        return result;
    }

    private ObjectNode runReplayOnce(
            String sourceType, String datasetId, String scenarioFamily, int maxTicks, long masterSeed) {
        loadDataSource(sourceType, datasetId, masterSeed);
        if (scenarioFamily != null) {
            launchScenario(scenarioFamily);
        } else {
            start();
        }
        int advanced = 0;
        while (running && advanced < maxTicks) {
            advance();
            advanced++;
        }
        running = false;
        ObjectNode summary = replaySummary(sourceType);
        summary.put("ticks_executed", advanced);
        return summary;
    }

    private void advance() {
        if (lobsterKernelReplay) {
            advanceLobsterReplay();
            return;
        }
        if (historicalCsv.loaded()) {
            advanceHistoricalReplay();
            return;
        }
        tick++;
        BookSnapshot before = matching.book().snapshot(5);
        double depthBefore = topDepth(before);
        JsonNode snapshot = marketSnapshot(before);
        Map<String, Object> orchestration = orchestrator.collect(snapshot);
        activeAgentIds = stringList(orchestration.get("agent_ids"));
        for (Object raw : listValue(orchestration.get("intents"))) {
            if (raw instanceof JsonNode intent) {
                applyIntent(intent);
            }
        }
        applyScenario();
        maintainBaseline();
        matching.recordSnapshot(
                tick,
                SNAPSHOT_DEPTH,
                null,
                null,
                scenario == null ? null : scenario.id(),
                scenario == null ? null : scenario.name(),
                scenario == null ? null : scenario.family());
        previousDepth = depthBefore;
        JsonNode state = buildState();
        journal.append("snapshots/ticks.jsonl", state);
    }

    private void advanceHistoricalReplay() {
        if (historicalCsv.eof()) {
            running = false;
            return;
        }
        tick++;
        BookSnapshot before = matching.book().snapshot(5);
        double depthBefore = topDepth(before);
        List<HistoricalCsvMarketDataSource.HistoricalCsvRecord> records =
                new ArrayList<>(historicalCsv.nextBatch());
        records.sort(Comparator.comparing(record -> new EventOrderKey(
                record.timestampNs(),
                EventPhase.HISTORICAL.code(),
                0,
                historicalParticipantId(record.participantId()),
                record.sourceSequence(),
                record.sourceSequence())));
        records.forEach(this::applyHistoricalRecord);
        if ("hybrid".equals(replaySourceType)) {
            applyScenario();
        }
        MutationContext snapshotContext = new MutationContext(
                tick,
                null,
                null,
                null,
                EventSource.EVENT_SOURCE_SIMULATION,
                null,
                null,
                null);
        matching.recordSnapshot(SNAPSHOT_DEPTH, snapshotContext);
        previousDepth = depthBefore;
        if (historicalCsv.eof()) {
            running = false;
        }
        JsonNode state = buildState();
        journal.append("snapshots/ticks.jsonl", state);
    }

    private void advanceLobsterReplay() {
        if (historical.eof()) {
            running = false;
            return;
        }
        tick++;
        BookSnapshot before = matching.book().snapshot(5);
        double depthBefore = topDepth(before);
        List<HistoricalMarketDataSource.HistoricalSnapshotRecord> records =
                new ArrayList<>(historical.nextKernelBatch());
        records.sort(Comparator.comparing(record -> new EventOrderKey(
                record.timestampNs(),
                EventPhase.HISTORICAL.code(),
                0,
                "HIST:" + historical.datasetId(),
                record.sourceSequence(),
                record.sourceSequence())));
        records.forEach(this::applyLobsterSnapshot);
        if ("hybrid".equals(replaySourceType)) {
            applyScenario();
        }
        matching.recordSnapshot(
                SNAPSHOT_DEPTH,
                new MutationContext(
                        tick, null, null, null, EventSource.EVENT_SOURCE_SIMULATION,
                        null, historical.currentTimestampNs(), historical.currentTimestampNs()));
        previousDepth = depthBefore;
        if (historical.eof()) running = false;
        journal.append("snapshots/ticks.jsonl", buildState());
    }

    private void applyLobsterSnapshot(HistoricalMarketDataSource.HistoricalSnapshotRecord record) {
        MutationContext context = new MutationContext(
                tick,
                null,
                null,
                null,
                EventSource.EVENT_SOURCE_HISTORICAL,
                record.sourceSequence(),
                record.timestampNs(),
                record.timestampNs());
        matching.runWithMutationContext(context, () -> {
            syncLobsterSide(Side.SIDE_BUY, record.bids(), lobsterBidPrices, record);
            syncLobsterSide(Side.SIDE_SELL, record.asks(), lobsterAskPrices, record);
            int depth = Math.max(1, historical.context(replaySourceType).path("depth").intValue());
            matching.recordSnapshot(lobsterSourceSnapshot(record), depth, context);
        });
    }

    private BookSnapshot lobsterSourceSnapshot(
            HistoricalMarketDataSource.HistoricalSnapshotRecord record) {
        BookSnapshot.Builder snapshot = BookSnapshot.newBuilder();
        record.bids().forEach(level -> snapshot.addBids(PriceLevel.newBuilder()
                .setPriceTicks(level.path("price_x10000").longValue())
                .setQuantityLots(level.path("quantity").longValue())
                .setOwner("historical")));
        record.asks().forEach(level -> snapshot.addAsks(PriceLevel.newBuilder()
                .setPriceTicks(level.path("price_x10000").longValue())
                .setQuantityLots(level.path("quantity").longValue())
                .setOwner("historical")));
        if (!record.bids().isEmpty()) {
            snapshot.setBestBidTicks(record.bids().get(0).path("price_x10000").longValue());
        }
        if (!record.asks().isEmpty()) {
            snapshot.setBestAskTicks(record.asks().get(0).path("price_x10000").longValue());
        }
        if (!record.bids().isEmpty() && !record.asks().isEmpty()) {
            long bestBid = record.bids().get(0).path("price_x10000").longValue();
            long bestAsk = record.asks().get(0).path("price_x10000").longValue();
            snapshot.setMidPriceTicksX2(Math.addExact(bestBid, bestAsk));
            snapshot.setSpreadTicks(Math.subtractExact(bestAsk, bestBid));
        }
        return snapshot.build();
    }

    private void syncLobsterSide(
            Side side,
            JsonNode levels,
            Set<Long> priorPrices,
            HistoricalMarketDataSource.HistoricalSnapshotRecord record) {
        Map<Long, Long> desired = new LinkedHashMap<>();
        levels.forEach(level -> desired.put(
                level.path("price_x10000").longValue(),
                level.path("quantity").longValue()));
        for (long price : new HashSet<>(priorPrices)) {
            if (!desired.containsKey(price)) {
                matching.book().updateAgentLevel(
                        side, price, 0, lobsterParticipantId(), "historical",
                        lobsterLevelOrderId(side, price), record.timestampNs(),
                        null, null, null);
            }
        }
        desired.forEach((price, quantity) -> matching.book().updateAgentLevel(
                side, price, quantity, lobsterParticipantId(), "historical",
                lobsterLevelOrderId(side, price), record.timestampNs(),
                null, null, null));
        priorPrices.clear();
        priorPrices.addAll(desired.keySet());
    }

    private void applyHistoricalRecord(HistoricalCsvMarketDataSource.HistoricalCsvRecord record) {
        String orderId = historicalOrderId(record.orderId());
        String participantId = historicalParticipantId(record.participantId());
        KernelOrder order = switch (record.eventType()) {
            case "ADD" -> KernelOrder.limit(
                    orderId,
                    participantId,
                    record.side(),
                    record.quantityLots(),
                    record.priceTicks(),
                    record.timestampNs());
            case "MODIFY" -> KernelOrder.modify(
                    orderId,
                    participantId,
                    record.side(),
                    record.quantityLots(),
                    record.priceTicks(),
                    record.timestampNs());
            case "CANCEL" -> KernelOrder.cancel(
                    orderId, participantId, record.side(), record.timestampNs());
            case "MARKET" -> KernelOrder.market(
                    orderId,
                    participantId,
                    record.side(),
                    record.quantityLots(),
                    record.timestampNs());
            default -> throw new IllegalStateException(
                    "validated historical event type is unsupported: " + record.eventType());
        };
        MutationContext context = new MutationContext(
                tick,
                null,
                null,
                null,
                EventSource.EVENT_SOURCE_HISTORICAL,
                record.sourceSequence(),
                record.timestampNs(),
                record.timestampNs());
        matching.submit(order, context);
    }

    private void applyIntent(JsonNode intent) {
        String kind = intent.path("kind").textValue();
        String agentId = intent.path("agent_id").textValue();
        try {
            Side side = side(intent.path("side").asText(""));
            long quantity = lots(intent.path("quantity").asDouble(0.0));
            long price = switch (kind) {
                case "set_level", "limit" -> ticks(intent.path("price").asDouble(0.0));
                default -> 0L;
            };
            int sequence = intent.path("sequence").asInt(0);
            switch (kind) {
                case "set_level" -> matching.book().updateAgentLevel(
                        side,
                        price,
                        Math.min(quantity, 25_000L),
                        agentId,
                        "normal",
                        null,
                        tick,
                        null,
                        null,
                        null);
                case "market" -> matching.submit(KernelOrder.market(
                        orderId(intent, agentId, sequence), agentId, side, quantity, tick));
                case "limit" -> matching.submit(KernelOrder.limit(
                        orderId(intent, agentId, sequence), agentId, side, quantity, price, tick));
                case "cancel" -> matching.submit(KernelOrder.cancel(
                        intent.path("order_id").asText(), agentId, side, tick));
                default -> {
                    return;
                }
            }
            ObjectNode event = event(intent.path("event_type").asText("normal"), agentId,
                    intent.path("message").asText("agent intent applied"));
            event.put("runtime_source", "agent_runner");
            event.put("side", side == Side.SIDE_BUY ? "buy" : "sell");
            if (price > 0) {
                event.put("price", price(price));
            }
            event.put("quantity", quantity(quantity));
            addAgentEvent(event);
        } catch (IllegalArgumentException ignored) {
            // Validation is repeated at the single-writer boundary; bad intents are dropped.
        }
    }

    private void applyScenario() {
        if (scenario == null) {
            return;
        }
        long age = scenario.age(tick);
        Long exchangeTimestamp = kernelHistoricalLoaded() ? replayCurrentTimestampNs() : null;
        MutationContext context = new MutationContext(
                tick,
                scenario.id(),
                scenario.name(),
                scenario.family(),
                EventSource.EVENT_SOURCE_SIMULATION,
                null,
                exchangeTimestamp,
                exchangeTimestamp);
        matching.runWithMutationContext(context, () -> {
            switch (scenario.family()) {
                case "spoofing_like_wall" -> applySpoofing(age);
                case "layering_like" -> applyLayering(age);
                case "quote_stuffing" -> applyQuoteStuffing(age);
                case "liquidity_evaporation" -> applyLiquidityEvaporation(age);
                default -> throw new IllegalStateException("unsupported live scenario");
            }
        });
        if (age > 0 && age <= 5) {
            ObjectNode event = event("red_team", scenario.agentId(), scenario.name() + " " + scenario.stage(tick));
            event.put("scenario_id", scenario.id());
            event.put("scenario_name", scenario.name());
            event.put("scenario_family", scenario.family());
            event.put("stage", scenario.stage(tick));
            addAgentEvent(event);
        }
    }

    private void applySpoofing(long age) {
        Side side = hybridAttackSide();
        int direction = side == Side.SIDE_SELL ? 1 : -1;
        long price = referencePriceTicks()
                + direction * (2 + Math.floorMod(scenario.seed(), 2)) * LEVEL_SPACING_TICKS;
        matching.book().updateAgentLevel(
                side, price, age < 3 ? 30_000 : 0, scenario.agentId(), "abuser",
                scenarioOrderId("WALL"), tick, scenario.id(), scenario.name(), scenario.family());
    }

    private void applyLayering(long age) {
        long referencePrice = referencePriceTicks();
        Side side = hybridAttackSide();
        int direction = side == Side.SIDE_SELL ? 1 : -1;
        for (int level = 2; level <= 4; level++) {
            matching.book().updateAgentLevel(
                    side,
                    referencePrice + direction * level * LEVEL_SPACING_TICKS,
                    age < 4 ? 10_000 + level * 1_000L : 0,
                    scenario.agentId(),
                    "abuser",
                    scenarioOrderId("LAYER-" + level),
                    tick,
                    scenario.id(),
                    scenario.name(),
                    scenario.family());
        }
    }

    private void applyQuoteStuffing(long age) {
        if (age > 5) {
            return;
        }
        long referencePrice = referencePriceTicks();
        for (int burst = 0; burst < 6; burst++) {
            Side side = burst % 2 == 0 ? Side.SIDE_BUY : Side.SIDE_SELL;
            int direction = side == Side.SIDE_BUY ? -1 : 1;
            long price = referencePrice + direction * (burst + 2L) * LEVEL_SPACING_TICKS;
            String orderId = scenarioOrderId("STUFF-" + age + "-" + burst);
            matching.book().updateAgentLevel(
                    side,
                    price,
                    1_000,
                    scenario.agentId(),
                    "abuser",
                    orderId,
                    tick,
                    scenario.id(),
                    scenario.name(),
                    scenario.family());
            matching.book().updateAgentLevel(
                    side,
                    price,
                    0,
                    scenario.agentId(),
                    "abuser",
                    orderId,
                    tick,
                    scenario.id(),
                    scenario.name(),
                    scenario.family());
        }
    }

    private void applyLiquidityEvaporation(long age) {
        if (age != 1) {
            return;
        }
        for (long price : matching.book().prices(Side.SIDE_BUY, 5)) {
            matching.book().removeLevel(Side.SIDE_BUY, price);
        }
        for (long price : matching.book().prices(Side.SIDE_SELL, 5)) {
            matching.book().removeLevel(Side.SIDE_SELL, price);
        }
    }

    private void maintainBaseline() {
        MutationContext context = new MutationContext(tick, null, null, null);
        matching.runWithMutationContext(context, () -> {
            for (int index = 0; index < BASELINE_LEVELS; index++) {
                long distance = (index + 1L) * LEVEL_SPACING_TICKS;
                long minimum = BASE_QUANTITY_LOTS + index * 1_000L;
                matching.book().ensureLevelMinimum(
                        Side.SIDE_BUY, REFERENCE_PRICE_TICKS - distance, minimum, "BASELINE_MM", "normal");
                matching.book().ensureLevelMinimum(
                        Side.SIDE_SELL, REFERENCE_PRICE_TICKS + distance, minimum, "BASELINE_MM", "normal");
            }
        });
    }

    private ObjectNode buildState() {
        BookSnapshot book = matching.book().snapshot(SNAPSHOT_DEPTH);
        ObjectNode result = mapper.createObjectNode();
        result.put("tick", tick);
        result.put("running", running);
        ArrayNode events = result.putArray("events");
        agentEvents.forEach(events::add);
        ArrayNode exchangeEvents = result.putArray("exchange_events");
        matching.tailEvents(EVENT_WINDOW).stream()
                .map(this::exchangeEventJson)
                .forEach(exchangeEvents::add);
        if (kernelHistoricalLoaded()) {
            ArrayNode historicalEvents = result.putArray("historical_events");
            matching.tailEventsBySource(EventSource.EVENT_SOURCE_HISTORICAL, EVENT_WINDOW).stream()
                    .map(this::exchangeEventJson)
                    .forEach(historicalEvents::add);
            result.set("market_data", replayContext());
        }
        ObjectNode bookJson = bookJson(book);
        result.set("book", bookJson);
        copyNullable(result, bookJson, "best_bid");
        copyNullable(result, bookJson, "best_ask");
        copyNullable(result, bookJson, "mid");
        copyNullable(result, bookJson, "spread");
        ArrayNode agents = result.putArray("active_agents");
        activeAgentIds.forEach(agents::add);
        if (scenario != null) {
            agents.add(scenario.agentId());
            result.set("active_scenario", scenarioJson());
        } else {
            result.putNull("active_scenario");
        }
        ObjectNode features = features(book);
        result.set("features", features);
        result.set("detectors", detectors(features));
        ArrayNode incidentArray = result.putArray("incidents");
        incidents.forEach(incidentArray::add);
        return result;
    }

    private ObjectNode features(BookSnapshot book) {
        double bidDepth = book.getBidsList().stream().limit(5).mapToDouble(level -> quantity(level.getQuantityLots())).sum();
        double askDepth = book.getAsksList().stream().limit(5).mapToDouble(level -> quantity(level.getQuantityLots())).sum();
        double depth = bidDepth + askDepth;
        double imbalance = depth == 0 ? 0 : (bidDepth - askDepth) / depth;
        double wall = book.getBidsList().stream().limit(5).mapToDouble(level -> quantity(level.getQuantityLots())).max().orElse(0);
        wall = Math.max(wall, book.getAsksList().stream().limit(5).mapToDouble(level -> quantity(level.getQuantityLots())).max().orElse(0));
        double average = depth / Math.max(1, Math.min(10, book.getBidsCount() + book.getAsksCount()));
        long largeLevelCount = book.getBidsList().stream()
                        .limit(5)
                        .filter(level -> quantity(level.getQuantityLots()) >= average * 1.5)
                        .count()
                + book.getAsksList().stream()
                        .limit(5)
                        .filter(level -> quantity(level.getQuantityLots()) >= average * 1.5)
                        .count();
        List<ExchangeEvent> currentEvents = matching.eventsAtTick(tick).stream()
                .filter(event -> event.getPayloadCase() != ExchangeEvent.PayloadCase.SNAPSHOT)
                .toList();
        long cancels = currentEvents.stream()
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.CANCEL)
                .count();
        long executions = currentEvents.stream()
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.EXECUTE)
                .count();
        double spread = book.hasSpreadTicks() ? price(book.getSpreadTicks()) : 0;
        double mid = book.hasMidPriceTicksX2() ? price(book.getMidPriceTicksX2()) / 2 : 0;
        return mapper.createObjectNode()
                .put("spread_bps", mid == 0 ? 0 : round(spread / mid * 10_000))
                .put("depth_top_n", round(depth))
                .put("imbalance", round(imbalance))
                .put("message_rate", 2.0 * currentEvents.size())
                .put("cancel_to_trade_ratio", round((double) cancels / Math.max(1, executions)))
                .put("order_lifetime_ms", round(averageCancelledLifetimeMs(currentEvents)))
                .put("wall_size_ratio", average == 0 ? 1.0 : round(wall / average))
                .put("large_level_count", largeLevelCount)
                .put("depth_change_pct", previousDepth == 0 ? 0 : round((depth - previousDepth) / previousDepth * 100));
    }

    private ObjectNode detectors(ObjectNode features) {
        ObjectNode result = mapper.createObjectNode();
        ArrayNode scores = result.putArray("scores");
        ArrayNode alerts = result.putArray("alerts");
        double wallRatio = features.path("wall_size_ratio").doubleValue();
        double cancelRatio = features.path("cancel_to_trade_ratio").doubleValue();
        double messageRate = features.path("message_rate").doubleValue();
        double largeLevels = features.path("large_level_count").doubleValue();
        double depthChange = features.path("depth_change_pct").doubleValue();
        List<DetectorScore> detectorScores = List.of(
                new DetectorScore(
                        "spoofing_like_detector",
                        clamp(0.05 + Math.max(0, wallRatio - 1.5) * 0.55
                                + Math.min(4, cancelRatio) * 0.08)),
                new DetectorScore(
                        "layering_like_detector",
                        clamp(0.05 + largeLevels * 0.25 + Math.min(4, cancelRatio) * 0.05)),
                new DetectorScore(
                        "quote_stuffing_detector",
                        clamp(0.05 + Math.min(1, messageRate / 25) * 0.55
                                + Math.min(1, cancelRatio / 6) * 0.35)),
                new DetectorScore(
                        "liquidity_shock_detector",
                        clamp(0.05 + Math.min(1, Math.max(0, -depthChange) / 60) * 0.95)));
        for (DetectorScore detector : detectorScores) {
            double confidence = detector.confidence();
            ObjectNode score = mapper.createObjectNode()
                    .put("name", detector.name())
                    .put("confidence", round(confidence))
                    .put("alert", confidence >= 0.75);
            if (confidence >= 0.75) {
                score.put("severity", confidence >= 0.9 ? "critical" : "high");
            } else {
                score.putNull("severity");
            }
            ArrayNode evidence = score.putArray("evidence");
            evidence.add(evidence("wall_size_ratio", "Wall size ratio", features.path("wall_size_ratio").doubleValue()));
            evidence.add(evidence("message_rate", "Message rate", messageRate));
            evidence.add(evidence("cancel_to_trade_ratio", "Cancel to trade ratio", cancelRatio));
            evidence.add(evidence("large_level_count", "Large top levels", largeLevels));
            evidence.add(evidence("depth_change_pct", "Top-depth change", depthChange));
            scores.add(score);
            if (confidence >= 0.75) {
                alerts.add(score.deepCopy());
                detectorAlertTicks.computeIfAbsent(detector.name(), ignored -> new ArrayList<>());
                List<Long> ticks = detectorAlertTicks.get(detector.name());
                if (ticks.isEmpty() || ticks.getLast() != tick) {
                    ticks.add(tick);
                }
                maybeCreateIncident(detector.name(), confidence, evidence);
            }
        }
        return result;
    }

    private void maybeCreateIncident(String detector, double confidence, ArrayNode evidence) {
        if (scenario == null || confidence < 0.80) {
            return;
        }
        String key = scenario.id() + ":" + detector;
        if (!incidentKeys.add(key)) {
            return;
        }
        incidentCounter++;
        ObjectNode incident = mapper.createObjectNode()
                .put("id", "INC-%06d".formatted(incidentCounter))
                .put("title", detector.replace('_', ' ') + " detected")
                .put("type", detector)
                .put("agent", scenario.agentId())
                .put("confidence", round(confidence))
                .put("severity", confidence >= 0.9 ? "Critical" : "High")
                .set("evidence", evidence.deepCopy())
                .put("explanation", "Nebius AI explanation pending.")
                .put("scenario_id", scenario.id())
                .put("scenario_family", scenario.family());
        incidents.add(incident);
        metricsIncidentCount = incidents.size();
        journal.append("incidents/incidents.jsonl", incident);
    }

    private ObjectNode scenarioJson() {
        ObjectNode result = mapper.createObjectNode()
                .put("scenario_id", scenario.id())
                .put("scenario_name", scenario.name())
                .put("scenario_family", scenario.family())
                .put("agent_id", scenario.agentId())
                .put("current_stage", scenario.stage(tick))
                .put("start_tick", scenario.startTick())
                .put("attack_seed", scenario.seed())
                .put("status", scenario.stage(tick));
        result.putArray("stages");
        result.putArray("evidence");
        return result;
    }

    private ObjectNode groundTruthLabel() {
        if (scenario == null) {
            throw new IllegalStateException("ground truth requires an active synthetic scenario");
        }
        long endTick = switch (scenario.family()) {
            case "spoofing_like_wall" -> scenario.startTick() + 3;
            case "layering_like" -> scenario.startTick() + 4;
            case "quote_stuffing" -> scenario.startTick() + 5;
            case "liquidity_evaporation" -> scenario.startTick() + 1;
            default -> throw new IllegalStateException("unsupported scenario family");
        };
        ObjectNode result = mapper.createObjectNode()
                .put("schema_version", "scenario_ground_truth_v1")
                .put("scenario_id", scenario.id())
                .put("scenario_family", scenario.family())
                .put("source", "synthetic_scenario")
                .put("has_attack", true)
                .put("start_tick", scenario.startTick())
                .put("end_tick", endTick);
        result.putArray("agent_ids").add(scenario.agentId());
        ArrayNode orderIds = result.putArray("order_ids");
        expectedScenarioOrderIds().forEach(orderIds::add);
        ArrayNode windows = result.putArray("manipulation_windows");
        windows.add(mapper.createObjectNode()
                .put("start_tick", scenario.startTick())
                .put("end_tick", endTick)
                .put("scenario_family", scenario.family()));
        ObjectNode phases = result.putObject("phase_windows");
        long cancellationStart = switch (scenario.family()) {
            case "spoofing_like_wall" -> scenario.startTick() + 3;
            case "layering_like" -> scenario.startTick() + 4;
            case "quote_stuffing" -> scenario.startTick();
            case "liquidity_evaporation" -> scenario.startTick();
            default -> throw new IllegalStateException("unsupported scenario family");
        };
        phases.set(
                "pressure_phase",
                mapper.createObjectNode()
                        .put("start_tick", scenario.startTick())
                        .put("end_tick", Math.max(scenario.startTick(), cancellationStart - 1)));
        phases.set(
                "cancellation_phase",
                mapper.createObjectNode()
                        .put("start_tick", cancellationStart)
                        .put("end_tick", endTick));
        return result;
    }

    private List<String> expectedScenarioOrderIds() {
        return switch (scenario.family()) {
            case "spoofing_like_wall" -> List.of(scenarioOrderId("WALL"));
            case "layering_like" -> List.of(
                    scenarioOrderId("LAYER-2"),
                    scenarioOrderId("LAYER-3"),
                    scenarioOrderId("LAYER-4"));
            case "quote_stuffing" -> {
                List<String> ids = new ArrayList<>();
                for (int age = 0; age <= 5; age++) {
                    for (int burst = 0; burst < 6; burst++) {
                        ids.add(scenarioOrderId("STUFF-" + age + "-" + burst));
                    }
                }
                yield List.copyOf(ids);
            }
            case "liquidity_evaporation" -> List.of();
            default -> throw new IllegalStateException("unsupported scenario family");
        };
    }

    private ObjectNode replaySummary(String sourceType) {
        ObjectNode summary = mapper.createObjectNode()
                .put("mode", sourceType)
                .put("dataset_id", replayDatasetId())
                .put("master_seed", replayMasterSeed)
                .put("source_row_count", replayRowCount())
                .put("source_rows_replayed", replayPosition())
                .put("events_sha256", replayEventsSha256())
                .put("canonical_event_count", matching.events().size())
                .put("stream_hash", HexFormat.of().formatHex(CanonicalHashes.eventStreamHash(matching.events(), 1)))
                .put("historical_event_hash", sourceEventHash(EventSource.EVENT_SOURCE_HISTORICAL))
                .put("synthetic_event_hash", sourceEventHash(EventSource.EVENT_SOURCE_SIMULATION))
                .put("historical_snapshot_stream_hash", historicalSnapshotStreamHash())
                .put(
                        "historical_source_sequences",
                        matching.events().stream()
                                .filter(event -> event.getMetadata().getSource()
                                        == EventSource.EVENT_SOURCE_HISTORICAL)
                                .filter(event -> event.getMetadata().hasSourceSequence())
                                .map(event -> event.getMetadata().getSourceSequence())
                                .distinct()
                                .count());
        summary.set("source_integrity", replaySourceIntegrity());
        ObjectNode counts = summary.putObject("event_counts");
        ObjectNode sourceCounts = counts.putObject("by_source");
        ObjectNode typeCounts = counts.putObject("by_type");
        for (ExchangeEvent event : matching.events()) {
            String source = event.getMetadata().getSource() == EventSource.EVENT_SOURCE_HISTORICAL
                    ? "historical"
                    : "simulation";
            sourceCounts.put(source, sourceCounts.has(source) ? sourceCounts.path(source).longValue() + 1 : 1);
            String type = event.getPayloadCase().name().toLowerCase();
            typeCounts.put(type, typeCounts.has(type) ? typeCounts.path(type).longValue() + 1 : 1);
        }
        ObjectNode alerts = summary.putObject("detector_alert_ticks");
        detectorAlertTicks.forEach((detector, ticks) -> {
            ArrayNode values = alerts.putArray(detector);
            ticks.forEach(values::add);
        });
        if (scenario == null) {
            summary.putNull("ground_truth");
            summary.putNull("attack_seed");
        } else {
            summary.set("ground_truth", groundTruthLabel());
            summary.put("attack_seed", scenario.seed());
        }
        BookSnapshot book = matching.book().snapshot(SNAPSHOT_DEPTH);
        ObjectNode realism = summary.putObject("realism");
        ObjectNode derived = features(book);
        realism.put("final_depth_top_n", derived.path("depth_top_n").doubleValue());
        realism.put("final_spread", book.hasSpreadTicks() ? price(book.getSpreadTicks()) : 0);
        realism.put("final_imbalance", derived.path("imbalance").doubleValue());
        realism.put("final_level_count", book.getBidsCount() + book.getAsksCount());
        summary.set("validation_trace", validationTrace());
        ArrayNode syntheticEvents = summary.putArray("synthetic_events");
        matching.events().stream()
                .filter(event -> event.getMetadata().getSource() == EventSource.EVENT_SOURCE_SIMULATION)
                .filter(event -> event.getMetadata().hasScenarioId())
                .map(this::exchangeEventJson)
                .forEach(syntheticEvents::add);
        return summary;
    }

    private String historicalSnapshotStreamHash() {
        MessageDigest digest = sha256Digest();
        matching.events().stream()
                .filter(event -> event.getMetadata().getSource() == EventSource.EVENT_SOURCE_HISTORICAL)
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.SNAPSHOT)
                .forEach(event -> {
                    var metadata = event.getMetadata();
                    String identity = "%d|%d|".formatted(
                            metadata.hasSourceSequence() ? metadata.getSourceSequence() : 0,
                            metadata.hasExchangeTimestampNs() ? metadata.getExchangeTimestampNs() : 0);
                    digest.update(identity.getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                    digest.update(CanonicalHashes.bookHash(event.getSnapshot().getBook()));
                });
        return HexFormat.of().formatHex(digest.digest());
    }

    private ArrayNode validationTrace() {
        ArrayNode trace = mapper.createArrayNode();
        Map<Long, long[]> flowByTick = new LinkedHashMap<>();
        for (ExchangeEvent event : matching.events()) {
            if (event.getPayloadCase() == ExchangeEvent.PayloadCase.SNAPSHOT) {
                continue;
            }
            long[] counts = flowByTick.computeIfAbsent(
                    event.getMetadata().getTick(), ignored -> new long[4]);
            counts[0]++;
            switch (event.getPayloadCase()) {
                case ADD -> counts[1]++;
                case CANCEL -> counts[2]++;
                case EXECUTE -> counts[3]++;
                default -> {
                    // Other canonical messages still contribute to message_count.
                }
            }
        }
        trace.add(validationObservation(
                0, 0, BookSnapshot.getDefaultInstance(), flowByTick.getOrDefault(0L, new long[4])));
        matching.events().stream()
                .filter(event -> event.getMetadata().getSource() == EventSource.EVENT_SOURCE_SIMULATION)
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.SNAPSHOT)
                .map(event -> validationObservation(
                        event.getMetadata().getTick(),
                        event.getMetadata().hasExchangeTimestampNs()
                                ? event.getMetadata().getExchangeTimestampNs()
                                : 0,
                        event.getSnapshot().getBook(),
                        flowByTick.getOrDefault(event.getMetadata().getTick(), new long[4])))
                .forEach(trace::add);
        return trace;
    }

    private ObjectNode validationObservation(
            long observationTick, long timestampNs, BookSnapshot book, long[] eventFlow) {
        double bidDepth = book.getBidsList().stream()
                .limit(5)
                .mapToDouble(level -> quantity(level.getQuantityLots()))
                .sum();
        double askDepth = book.getAsksList().stream()
                .limit(5)
                .mapToDouble(level -> quantity(level.getQuantityLots()))
                .sum();
        double depth = bidDepth + askDepth;
        return mapper.createObjectNode()
                .put("tick", observationTick)
                .put("exchange_timestamp_ns", timestampNs)
                .put("book_hash", HexFormat.of().formatHex(CanonicalHashes.bookHash(book)))
                .put("spread", book.hasSpreadTicks() ? price(book.getSpreadTicks()) : 0)
                .put("depth_top_n", round(depth))
                .put("imbalance", depth == 0 ? 0 : round((bidDepth - askDepth) / depth))
                .put("level_count", book.getBidsCount() + book.getAsksCount())
                .put("message_count", eventFlow[0])
                .put("add_count", eventFlow[1])
                .put("cancel_count", eventFlow[2])
                .put("execute_count", eventFlow[3]);
    }

    private String sourceEventHash(EventSource source) {
        MessageDigest digest = sha256Digest();
        matching.events().stream()
                .filter(event -> event.getMetadata().getSource() == source)
                .map(CanonicalHashes::eventHash)
                .forEach(digest::update);
        return HexFormat.of().formatHex(digest.digest());
    }

    private static MessageDigest sha256Digest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
    }

    private double averageCancelledLifetimeMs(List<ExchangeEvent> currentEvents) {
        Set<String> cancelledOrderIds = currentEvents.stream()
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.CANCEL)
                .map(event -> event.getCancel().getOrderId())
                .collect(java.util.stream.Collectors.toSet());
        if (cancelledOrderIds.isEmpty()) {
            return 0;
        }
        Map<String, ExchangeEvent> adds = new LinkedHashMap<>();
        matching.events().stream()
                .filter(event -> event.getPayloadCase() == ExchangeEvent.PayloadCase.ADD)
                .filter(event -> cancelledOrderIds.contains(event.getAdd().getOrderId()))
                .forEach(event -> adds.putIfAbsent(event.getAdd().getOrderId(), event));
        double total = 0;
        int count = 0;
        for (ExchangeEvent cancel : currentEvents) {
            if (cancel.getPayloadCase() != ExchangeEvent.PayloadCase.CANCEL) {
                continue;
            }
            ExchangeEvent add = adds.get(cancel.getCancel().getOrderId());
            if (add == null) {
                continue;
            }
            long addTime = eventTimeNs(add);
            long cancelTime = eventTimeNs(cancel);
            total += Math.max(0, cancelTime - addTime) / 1_000_000.0;
            count++;
        }
        return count == 0 ? 0 : total / count;
    }

    private static long eventTimeNs(ExchangeEvent event) {
        if (event.getMetadata().hasExchangeTimestampNs()) {
            return event.getMetadata().getExchangeTimestampNs();
        }
        return event.getMetadata().getTick() * 500_000_000L;
    }

    private long referencePriceTicks() {
        BookSnapshot book = matching.book().snapshot(1);
        if (book.hasMidPriceTicksX2()) {
            return book.getMidPriceTicksX2() / 2;
        }
        if (book.hasBestBidTicks()) {
            return book.getBestBidTicks();
        }
        if (book.hasBestAskTicks()) {
            return book.getBestAskTicks();
        }
        return REFERENCE_PRICE_TICKS;
    }

    private Side hybridAttackSide() {
        if (!kernelHistoricalLoaded()) {
            return Side.SIDE_SELL;
        }
        return (scenario.seed() & 1L) == 0 ? Side.SIDE_SELL : Side.SIDE_BUY;
    }

    private boolean kernelHistoricalLoaded() {
        return historicalCsv.loaded() || lobsterKernelReplay;
    }

    private String replayDatasetId() {
        return historicalCsv.loaded() ? historicalCsv.datasetId() : historical.datasetId();
    }

    private String replaySymbol() {
        return historicalCsv.loaded() ? historicalCsv.symbol() : historical.symbol();
    }

    private String replayVenue() {
        return historicalCsv.loaded() ? historicalCsv.venue() : historical.venue();
    }

    private long replayPriceTickSizeNanos() {
        return historicalCsv.loaded()
                ? historicalCsv.priceTickSizeNanos()
                : historical.priceTickSizeNanos();
    }

    private long replayQuantityLotSizeNanos() {
        return historicalCsv.loaded()
                ? historicalCsv.quantityLotSizeNanos()
                : historical.quantityLotSizeNanos();
    }

    private long replayCurrentTimestampNs() {
        return historicalCsv.loaded()
                ? historicalCsv.currentTimestampNs()
                : historical.currentTimestampNs();
    }

    private long replayPosition() {
        return historicalCsv.loaded()
                ? historicalCsv.replayPosition()
                : historical.replayPosition();
    }

    private long replayRowCount() {
        return historicalCsv.loaded() ? historicalCsv.rowCount() : historical.rowCount();
    }

    private String replayEventsSha256() {
        return historicalCsv.loaded()
                ? historicalCsv.eventsSha256()
                : historical.eventsSha256();
    }

    private JsonNode replaySourceIntegrity() {
        if (!historicalCsv.loaded()) {
            return historical.integrity();
        }
        ObjectNode result = mapper.createObjectNode()
                .put("validated", true)
                .put("format", "canonical_csv_v1")
                .put("row_count", historicalCsv.rowCount())
                .put("paired_rows", historicalCsv.rowCount());
        result.putObject("output_sha256")
                .put("events.csv", historicalCsv.eventsSha256());
        return result;
    }

    private JsonNode replayContext() {
        return historicalCsv.loaded()
                ? historicalCsv.context(replaySourceType)
                : historical.context(replaySourceType);
    }

    private String lobsterParticipantId() {
        return "HIST:" + replayDatasetId() + ":P:LOBSTER";
    }

    private String lobsterLevelOrderId(Side side, long priceTicks) {
        String bookSide = side == Side.SIDE_BUY ? "B" : "S";
        return "HIST:" + replayDatasetId() + ":L2:" + bookSide + ":" + priceTicks;
    }

    private String scenarioOrderId(String suffix) {
        if (kernelHistoricalLoaded()) {
            return "SYN:" + scenario.id() + ":" + Long.toUnsignedString(scenario.seed(), 16) + ":O:" + suffix;
        }
        return "SCENARIO-" + suffix;
    }

    private String historicalOrderId(String sourceOrderId) {
        return "HIST:" + replayDatasetId() + ":O:" + sourceOrderId;
    }

    private String historicalParticipantId(String sourceParticipantId) {
        return "HIST:" + replayDatasetId() + ":P:" + sourceParticipantId;
    }

    private ObjectNode marketSnapshot(BookSnapshot book) {
        ObjectNode result = mapper.createObjectNode().put("tick", tick);
        ObjectNode rendered = bookJson(book);
        result.set("bids", rendered.path("bids"));
        result.set("asks", rendered.path("asks"));
        copyNullable(result, rendered, "best_bid");
        copyNullable(result, rendered, "best_ask");
        copyNullable(result, rendered, "mid");
        copyNullable(result, rendered, "spread");
        return result;
    }

    private ObjectNode bookJson(BookSnapshot book) {
        ObjectNode result = mapper.createObjectNode();
        ArrayNode bids = result.putArray("bids");
        book.getBidsList().forEach(level -> bids.add(levelJson(level)));
        ArrayNode asks = result.putArray("asks");
        book.getAsksList().forEach(level -> asks.add(levelJson(level)));
        if (book.hasBestBidTicks()) {
            result.put("best_bid", price(book.getBestBidTicks()));
        } else {
            result.putNull("best_bid");
        }
        if (book.hasBestAskTicks()) {
            result.put("best_ask", price(book.getBestAskTicks()));
        } else {
            result.putNull("best_ask");
        }
        if (book.hasMidPriceTicksX2()) {
            result.put("mid", price(book.getMidPriceTicksX2()) / 2.0);
            result.put("spread", price(book.getSpreadTicks()));
        } else {
            result.putNull("mid");
            result.putNull("spread");
        }
        return result;
    }

    private ObjectNode levelJson(PriceLevel level) {
        ObjectNode result = mapper.createObjectNode()
                .put("price", price(level.getPriceTicks()))
                .put("quantity", quantity(level.getQuantityLots()));
        if (level.hasOwner()) {
            result.put("owner", level.getOwner());
        }
        return result;
    }

    private ObjectNode exchangeEventJson(ExchangeEvent event) {
        ObjectNode result = mapper.createObjectNode();
        var metadata = event.getMetadata();
        result.put("schema_version", metadata.getSchemaVersion());
        result.put("event_id", metadata.getEventId());
        result.put("sequence", metadata.getSequence());
        result.put("source", metadata.getSource() == EventSource.EVENT_SOURCE_HISTORICAL ? "historical" : "simulation");
        if (metadata.hasSourceSequence()) {
            result.put("source_sequence", metadata.getSourceSequence());
        } else {
            result.putNull("source_sequence");
        }
        result.put("symbol", metadata.getSymbol());
        result.put("venue", metadata.getVenue());
        result.put("tick", metadata.getTick());
        if (metadata.hasExchangeTimestampNs()) {
            result.put("exchange_timestamp_ns", metadata.getExchangeTimestampNs());
        } else {
            result.putNull("exchange_timestamp_ns");
        }
        if (metadata.hasReceivedTimestampNs()) {
            result.put("received_timestamp_ns", metadata.getReceivedTimestampNs());
        } else {
            result.putNull("received_timestamp_ns");
        }
        optional(result, "scenario_id", metadata.hasScenarioId(), metadata.getScenarioId());
        optional(result, "scenario_name", metadata.hasScenarioName(), metadata.getScenarioName());
        optional(result, "scenario_family", metadata.hasScenarioFamily(), metadata.getScenarioFamily());
        switch (event.getPayloadCase()) {
            case ADD -> {
                result.put("event_type", "add");
                resting(result, event.getAdd().getOrderId(), event.getAdd().getAgentId(), event.getAdd().getSide(),
                        event.getAdd().getPriceTicks(), event.getAdd().getQuantityLots(), event.getAdd().getOwner());
            }
            case MODIFY -> {
                result.put("event_type", "modify");
                resting(result, event.getModify().getOrderId(), event.getModify().getAgentId(), event.getModify().getSide(),
                        event.getModify().getPriceTicks(), event.getModify().getQuantityLots(), event.getModify().getOwner());
                result.put("previous_price", price(event.getModify().getPreviousPriceTicks()));
                result.put("previous_quantity", quantity(event.getModify().getPreviousQuantityLots()));
                result.put("priority_preserved", event.getModify().getPriorityPreserved());
            }
            case CANCEL -> {
                result.put("event_type", "cancel");
                resting(result, event.getCancel().getOrderId(), event.getCancel().getAgentId(), event.getCancel().getSide(),
                        event.getCancel().getPriceTicks(), event.getCancel().getQuantityLots(), event.getCancel().getOwner());
            }
            case EXECUTE -> {
                result.put("event_type", "execute");
                var execution = event.getExecute();
                result.put("execution_id", execution.getExecutionId());
                result.put("aggressor_order_id", execution.getAggressorOrderId());
                result.put("resting_order_id", execution.getRestingOrderId());
                result.put("aggressor_agent_id", execution.getAggressorAgentId());
                result.put("resting_agent_id", execution.getRestingAgentId());
                result.put("side", execution.getAggressorSide() == Side.SIDE_BUY ? "buy" : "sell");
                result.put("price", price(execution.getPriceTicks()));
                result.put("quantity", quantity(execution.getQuantityLots()));
                result.put("aggressor_remaining_quantity", quantity(execution.getAggressorRemainingQuantityLots()));
                result.put("resting_remaining_quantity", quantity(execution.getRestingRemainingQuantityLots()));
            }
            case SNAPSHOT -> {
                result.put("event_type", "snapshot");
                result.put("depth", event.getSnapshot().getDepth());
                result.set("book", bookJson(event.getSnapshot().getBook()));
            }
            default -> throw new IllegalStateException("exchange event payload is required");
        }
        return result;
    }

    private void resting(ObjectNode result, String orderId, String agentId, Side side, long price, long quantity, String owner) {
        result.put("order_id", orderId);
        result.put("agent_id", agentId);
        result.put("side", side == Side.SIDE_BUY ? "buy" : "sell");
        result.put("price", price(price));
        result.put("quantity", quantity(quantity));
        result.put("owner", owner);
    }

    private IntegerMatchingEngine newMatchingEngine() {
        IntegerOrderBook book = new IntegerOrderBook(UNIT_NANOS, UNIT_NANOS);
        book.initialize(REFERENCE_PRICE_TICKS, BASELINE_LEVELS, LEVEL_SPACING_TICKS, BASE_QUANTITY_LOTS, "normal");
        return new IntegerMatchingEngine(book, "BTCUSDT", "SIM", EventSource.EVENT_SOURCE_SIMULATION);
    }

    private IntegerMatchingEngine newHistoricalMatchingEngine() {
        IntegerOrderBook book =
                new IntegerOrderBook(replayPriceTickSizeNanos(), replayQuantityLotSizeNanos());
        return new IntegerMatchingEngine(
                book,
                replaySymbol(),
                replayVenue(),
                EventSource.EVENT_SOURCE_SIMULATION);
    }

    private void addAgentEvent(ObjectNode event) {
        agentEvents.addFirst(event);
        while (agentEvents.size() > AGENT_EVENT_WINDOW) {
            agentEvents.removeLast();
        }
        journal.append("events/events.jsonl", event);
    }

    private ObjectNode event(String type, String agentId, String message) {
        return mapper.createObjectNode()
                .put("type", type)
                .put("timestamp", tick)
                .put("tick", tick)
                .put("agent_id", agentId)
                .put("message", message);
    }

    private ObjectNode evidence(String key, String label, Object value) {
        ObjectNode result = mapper.createObjectNode().put("key", key).put("label", label);
        if (value instanceof Number number) {
            result.put("value", number.doubleValue());
        } else {
            result.put("value", String.valueOf(value));
        }
        result.put("interpretation", "Confirmed by deterministic Java detector threshold.");
        return result;
    }

    private static String normalizeScenario(String raw) {
        String normalized = raw == null ? "" : raw.trim().toLowerCase().replace('-', '_');
        if ("spoofing_like".equals(normalized)) {
            normalized = "spoofing_like_wall";
        }
        if (!Set.of("spoofing_like_wall", "layering_like", "quote_stuffing", "liquidity_evaporation").contains(normalized)) {
            throw new IllegalArgumentException("unknown scenario: " + raw);
        }
        return normalized;
    }

    private static String displayName(String family) {
        return switch (family) {
            case "spoofing_like_wall" -> "Spoofing-like Wall";
            case "layering_like" -> "Layering-like Pattern";
            case "quote_stuffing" -> "Quote Stuffing Burst";
            case "liquidity_evaporation" -> "Liquidity Evaporation";
            default -> family;
        };
    }

    private static Side side(String raw) {
        return switch (raw) {
            case "bid", "buy" -> Side.SIDE_BUY;
            case "ask", "sell" -> Side.SIDE_SELL;
            default -> throw new IllegalArgumentException("intent side is required");
        };
    }

    private static String orderId(JsonNode intent, String agentId, int sequence) {
        String provided = intent.path("order_id").asText("");
        return provided.isBlank() ? agentId + "-" + intent.path("tick").longValue() + "-" + sequence : provided;
    }

    private long ticks(double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException("positive finite price is required");
        }
        long unit = kernelHistoricalLoaded() ? replayPriceTickSizeNanos() : UNIT_NANOS;
        return BigDecimal.valueOf(value)
                .movePointRight(9)
                .divide(BigDecimal.valueOf(unit), 0, RoundingMode.HALF_EVEN)
                .longValueExact();
    }

    private long lots(double value) {
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException("non-negative finite quantity is required");
        }
        long unit = kernelHistoricalLoaded() ? replayQuantityLotSizeNanos() : UNIT_NANOS;
        return BigDecimal.valueOf(value)
                .movePointRight(9)
                .divide(BigDecimal.valueOf(unit), 0, RoundingMode.HALF_EVEN)
                .longValueExact();
    }

    private double price(long ticks) {
        long unit = kernelHistoricalLoaded() ? replayPriceTickSizeNanos() : UNIT_NANOS;
        return BigDecimal.valueOf(ticks)
                .multiply(BigDecimal.valueOf(unit))
                .movePointLeft(9)
                .doubleValue();
    }

    private double quantity(long lots) {
        long unit = kernelHistoricalLoaded() ? replayQuantityLotSizeNanos() : UNIT_NANOS;
        return BigDecimal.valueOf(lots)
                .multiply(BigDecimal.valueOf(unit))
                .movePointLeft(9)
                .doubleValue();
    }

    private double topDepth(BookSnapshot book) {
        return book.getBidsList().stream().mapToDouble(level -> quantity(level.getQuantityLots())).sum()
                + book.getAsksList().stream().mapToDouble(level -> quantity(level.getQuantityLots())).sum();
    }

    @SuppressWarnings("unchecked")
    private static List<Object> listValue(Object value) {
        return value instanceof List<?> list ? (List<Object>) list : List.of();
    }

    private static List<String> stringList(Object value) {
        return listValue(value).stream().map(String::valueOf).toList();
    }

    private static double round(double value) {
        return BigDecimal.valueOf(value).setScale(4, RoundingMode.HALF_EVEN).doubleValue();
    }

    private static double clamp(double value) {
        return Math.max(0, Math.min(0.99, value));
    }

    private static void optional(ObjectNode node, String field, boolean present, String value) {
        if (present) {
            node.put(field, value);
        } else {
            node.putNull(field);
        }
    }

    private static void copyNullable(ObjectNode target, ObjectNode source, String field) {
        target.set(field, source.path(field).deepCopy());
    }

    private record DetectorScore(String name, double confidence) {}
}
