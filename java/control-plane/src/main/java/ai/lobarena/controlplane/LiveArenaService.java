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
import jakarta.annotation.PreDestroy;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
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
import java.util.Locale;
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
    private static final int DEFAULT_EVENT_HISTORY_CAPACITY = 50_000;
    private static final int DEFAULT_ARCHIVE_SEGMENT_EVENTS = 25_000;
    private static final long DEFAULT_ARCHIVE_MAX_STREAM_BYTES = 20L * 1024 * 1024 * 1024;

    private final ObjectMapper mapper;
    private final AgentOrchestrator orchestrator;
    private final ArenaJournal journal;
    private final HistoricalMarketDataSource historical;
    private final HistoricalCsvMarketDataSource historicalCsv;
    private final int eventHistoryCapacity;
    private final CanonicalEventArchive eventArchive;
    private final DuckDbResourceLimits duckDbResourceLimits;
    private final Deque<ObjectNode> agentEvents = new ArrayDeque<>();
    private final List<ObjectNode> incidents = new ArrayList<>();
    private final Set<String> incidentKeys = new HashSet<>();
    private final Map<String, List<Long>> detectorAlertTicks = new LinkedHashMap<>();
    private final long defaultMasterSeed;

    private IntegerMatchingEngine matching;
    private volatile long tick;
    private volatile boolean running;
    private volatile int metricsIncidentCount;
    private volatile int metricsRetainedEventCount;
    private volatile long metricsLatestSequence;
    private volatile long metricsArchiveBytes;
    private int scenarioCounter;
    private int incidentCounter;
    private List<String> activeAgentIds = List.of();
    private LiveScenario scenario;
    private ObjectNode scenarioParameters;
    private InjectionScheduleState injectionSchedule;
    private long normalizedAppliedRows;
    private long normalizedAppliedSourceSequence;
    private long normalizedAppliedTimestampNs;
    private double previousDepth;
    private String replaySourceType;
    private long replayMasterSeed;
    private volatile boolean normalizedHistoricalKernelReplay;
    private EventStreamSummary eventSummary;
    private String streamId;
    private volatile String streamError;
    private final Set<Long> historicalBidPrices = new HashSet<>();
    private final Set<Long> historicalAskPrices = new HashSet<>();
    private final Deque<HistoricalMarketDataSource.HistoricalSnapshotRecord> scheduledHistoricalRecords =
            new ArrayDeque<>();

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
        this(
                mapper,
                orchestrator,
                journal,
                historicalDataDir,
                historicalCsvDataDir,
                historicalRowsPerTick,
                masterSeed,
                DEFAULT_EVENT_HISTORY_CAPACITY,
                DEFAULT_ARCHIVE_SEGMENT_EVENTS,
                DEFAULT_ARCHIVE_MAX_STREAM_BYTES);
    }

    LiveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            Path historicalDataDir,
            Path historicalCsvDataDir,
            int historicalRowsPerTick,
            long masterSeed,
            int eventHistoryCapacity,
            int archiveSegmentEvents,
            long archiveMaxStreamBytes) {
        this(
                mapper,
                orchestrator,
                journal,
                historicalDataDir,
                historicalCsvDataDir,
                historicalRowsPerTick,
                masterSeed,
                eventHistoryCapacity,
                archiveSegmentEvents,
                archiveMaxStreamBytes,
                DuckDbResourceLimits.defaults());
    }

    LiveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            Path historicalDataDir,
            Path historicalCsvDataDir,
            int historicalRowsPerTick,
            long masterSeed,
            int eventHistoryCapacity,
            int archiveSegmentEvents,
            long archiveMaxStreamBytes,
            DuckDbResourceLimits duckDbResourceLimits) {
        this.mapper = mapper;
        this.orchestrator = orchestrator;
        this.journal = journal;
        this.historical = new HistoricalMarketDataSource(
                mapper, historicalDataDir, historicalRowsPerTick, duckDbResourceLimits);
        this.duckDbResourceLimits = duckDbResourceLimits;
        this.historicalCsv =
                new HistoricalCsvMarketDataSource(mapper, historicalCsvDataDir, historicalRowsPerTick);
        this.eventHistoryCapacity = eventHistoryCapacity;
        this.eventArchive = new CanonicalEventArchive(
                journal.root(),
                mapper,
                archiveSegmentEvents,
                archiveMaxStreamBytes,
                this::exchangeEventJson);
        this.defaultMasterSeed = masterSeed;
        this.replayMasterSeed = masterSeed;
        this.matching = newMatchingEngine();
        this.previousDepth = topDepth(matching.book().snapshot(5));
    }

    synchronized JsonNode state() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            return historical.state();
        }
        return buildState();
    }

    JsonNode metricsState() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            return historical.metricsState();
        }
        return mapper.createObjectNode()
                .put("tick", tick)
                .put("running", running)
                .put("incidents_count", metricsIncidentCount)
                .put("retained_event_count", metricsRetainedEventCount)
                .put("latest_sequence", metricsLatestSequence)
                .put("archive_bytes", metricsArchiveBytes)
                .put("archive_pending_events", eventArchive.pendingCount());
    }

    synchronized JsonNode start() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            return historical.start();
        }
        ensureReplayArchiveCapacity();
        running = true;
        return buildState();
    }

    synchronized JsonNode pause() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            return historical.pause();
        }
        running = false;
        return buildState();
    }

    synchronized JsonNode reset() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            return historical.reset();
        }
        if (historicalCsv.loaded()) {
            historicalCsv.reset();
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if (normalizedHistoricalKernelReplay) {
            historical.reset();
            historicalBidPrices.clear();
            historicalAskPrices.clear();
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
        scenarioParameters = null;
        injectionSchedule = null;
        scheduledHistoricalRecords.clear();
        normalizedAppliedRows = 0;
        normalizedAppliedSourceSequence = 0;
        normalizedAppliedTimestampNs = 0;
        agentEvents.clear();
        incidents.clear();
        metricsIncidentCount = 0;
        incidentKeys.clear();
        detectorAlertTicks.clear();
        activeAgentIds = List.of();
        matching = replacement;
        historicalBidPrices.clear();
        historicalAskPrices.clear();
        previousDepth = topDepth(matching.book().snapshot(5));
    }

    synchronized JsonNode launchScenario(String family) {
        String normalized = normalizeScenario(family);
        return launchScenario(normalized, resolveScenarioParameters(normalized, Map.of()));
    }

    private JsonNode launchScenario(String family, ObjectNode parameters) {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            throw new IllegalArgumentException("scenarios are unavailable for historical market data");
        }
        if (kernelHistoricalLoaded() && !"hybrid".equals(replaySourceType)) {
            throw new IllegalArgumentException("scenarios require the hybrid historical source");
        }
        ensureReplayArchiveCapacity();
        String normalized = normalizeScenario(family);
        armScenario(normalized, parameters, tick + 1, null, null);
        return scenarioJson();
    }

    private void armScenario(
            String normalized,
            ObjectNode parameters,
            long startTick,
            Long triggerSourceSequence,
            Long triggerTimestampNs) {
        scenarioCounter++;
        String scenarioAgentId = kernelHistoricalLoaded() ? "SYN:ABUSER_01" : "ABUSER_01";
        long scenarioSeed = kernelHistoricalLoaded()
                ? DeterministicValues.deriveStreamSeed(
                        replayMasterSeed,
                        "hybrid:" + replayDatasetId() + ":" + normalized + ":" + scenarioCounter
                                + (injectionSchedule == null ? "" : ":" + injectionSchedule.scheduleSha256))
                : 0L;
        scenario = new LiveScenario(
                "SCN-%06d".formatted(scenarioCounter),
                normalized,
                displayName(normalized),
                scenarioAgentId,
                startTick,
                scenarioSeed);
        scenarioParameters = parameters.deepCopy();
        if (injectionSchedule != null) {
            injectionSchedule.actualSourceSequence = triggerSourceSequence;
            injectionSchedule.actualTimestampNs = triggerTimestampNs;
        }
        running = true;
        addAgentEvent(event("red_team", scenarioAgentId, "scenario armed")
                .put("scenario_id", scenario.id())
                .put("scenario_name", scenario.name())
                .put("scenario_family", scenario.family())
                .put("stage", "armed"));
        journal.append("attacks/attacks.jsonl", scenarioJson());
        journal.append("labels/scenario_labels.jsonl", groundTruthLabel());
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
        return exchangeEvents(null, afterSequence, limit);
    }

    synchronized JsonNode exchangeEvents(String requestedStreamId, long afterSequence, int limit) {
        if (requestedStreamId == null && historical.loaded() && !normalizedHistoricalKernelReplay) {
            ObjectNode replay = mapper.createObjectNode();
            replay.putArray("events");
            return replay.put("after_sequence", afterSequence)
                    .put("next_after_sequence", afterSequence)
                    .put("latest_sequence", 0)
                    .putNull("stream_id")
                    .put("first_available_sequence", 0)
                    .put("retained_from_sequence", 0)
                    .put("has_more", false);
        }
        String selectedStreamId = requestedStreamId == null ? streamId : requestedStreamId;
        ArrayNode events = mapper.createArrayNode();
        eventArchive.readAfter(selectedStreamId, afterSequence, limit).forEach(events::add);
        boolean currentStream = selectedStreamId.equals(streamId);
        long latest = currentStream
                ? matching.latestEventSequence()
                : eventArchive.latestSequence(selectedStreamId);
        long next = events.isEmpty() ? afterSequence : events.get(events.size() - 1).path("sequence").longValue();
        return mapper.createObjectNode()
                .set("events", events)
                .put("after_sequence", afterSequence)
                .put("next_after_sequence", next)
                .put("latest_sequence", latest)
                .put("stream_id", selectedStreamId)
                .put("first_available_sequence", latest == 0 ? 0 : 1)
                .put(
                        "retained_from_sequence",
                        currentStream ? matching.firstRetainedSequence() : latest + 1)
                .put("has_more", next < latest);
    }

    @Scheduled(fixedDelayString = "${lob.arena.tick-interval-ms:500}")
    synchronized void scheduledTick() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
            historical.advance();
            return;
        }
        if (running) {
            advance();
        }
    }

    synchronized JsonNode stepForTest() {
        if (historical.loaded() && !normalizedHistoricalKernelReplay) {
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

    JsonNode runtimeLimits() {
        return mapper.createObjectNode()
                .put("event_history_capacity", eventHistoryCapacity)
                .put("event_archive_max_stream_bytes", eventArchive.maxStreamBytes())
                .put("duckdb_memory_limit", duckDbResourceLimits.memoryLimit())
                .put("duckdb_threads", duckDbResourceLimits.threads())
                .put("duckdb_temp_directory", duckDbResourceLimits.tempDirectory().toString())
                .put(
                        "duckdb_max_temp_directory_size",
                        duckDbResourceLimits.maxTempDirectorySize());
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
                normalizedHistoricalKernelReplay = false;
                replaySourceType = "historical";
                historicalCsv.load(datasetId);
                resetRuntime(newHistoricalMatchingEngine());
                return buildState();
            }
            historicalCsv.clear();
            replaySourceType = "historical";
            normalizedHistoricalKernelReplay = false;
            historical.load(datasetId);
            normalizedHistoricalKernelReplay = true;
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if ("hybrid".equals(sourceType)) {
            if (historicalCsv.supports(datasetId)) {
                historical.clear();
                normalizedHistoricalKernelReplay = false;
                replaySourceType = "hybrid";
                historicalCsv.load(datasetId);
                resetRuntime(newHistoricalMatchingEngine());
                return buildState();
            }
            historicalCsv.clear();
            normalizedHistoricalKernelReplay = false;
            historical.load(datasetId);
            normalizedHistoricalKernelReplay = true;
            replaySourceType = "hybrid";
            resetRuntime(newHistoricalMatchingEngine());
            return buildState();
        }
        if ("synthetic".equals(sourceType)) {
            historical.clear();
            historicalCsv.clear();
            normalizedHistoricalKernelReplay = false;
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
        return runReplayComparison(
                datasetId, scenarioFamily, maxTicks, masterSeed, null, null, Map.of());
    }

    synchronized JsonNode runReplayComparison(
            String datasetId,
            String scenarioFamily,
            int maxTicks,
            long masterSeed,
            Long triggerSourceSequence,
            Long triggerTimestampNs,
            Map<String, Object> parameterOverrides) {
        if (maxTicks < 1 || maxTicks > 100_000) {
            throw new IllegalArgumentException("max_ticks must be between 1 and 100000");
        }
        if (triggerSourceSequence != null && triggerTimestampNs != null) {
            throw new IllegalArgumentException(
                    "trigger_source_sequence and trigger_timestamp_ns are mutually exclusive");
        }
        if (triggerSourceSequence != null && triggerSourceSequence <= 0) {
            throw new IllegalArgumentException("trigger_source_sequence must be positive");
        }
        if (triggerTimestampNs != null
                && (triggerTimestampNs < 0 || triggerTimestampNs >= 86_400_000_000_000L)) {
            throw new IllegalArgumentException("trigger_timestamp_ns must be within one trading day");
        }
        String normalizedScenario = normalizeScenario(scenarioFamily);
        ObjectNode parameters = resolveScenarioParameters(normalizedScenario, parameterOverrides);
        boolean scheduled = triggerSourceSequence != null || triggerTimestampNs != null;
        scenarioCounter = 0;
        incidentCounter = 0;
        ObjectNode control = runReplayOnce(
                "historical", datasetId, normalizedScenario, maxTicks, masterSeed,
                triggerSourceSequence, triggerTimestampNs, parameters, false);
        ObjectNode hybrid = runReplayOnce(
                "hybrid", datasetId, normalizedScenario, maxTicks, masterSeed,
                triggerSourceSequence, triggerTimestampNs, parameters, true);
        scenarioCounter = 0;
        incidentCounter = 0;
        ObjectNode repeatedControl = runReplayOnce(
                "historical", datasetId, normalizedScenario, maxTicks, masterSeed,
                triggerSourceSequence, triggerTimestampNs, parameters, false);
        ObjectNode repeatedHybrid = runReplayOnce(
                "hybrid", datasetId, normalizedScenario, maxTicks, masterSeed,
                triggerSourceSequence, triggerTimestampNs, parameters, true);
        ObjectNode result = mapper.createObjectNode()
                .put("schema_version", "historical_replay_comparison_v1")
                .put("dataset_id", datasetId)
                .put("master_seed", masterSeed)
                .put("events_sha256", replayEventsSha256())
                .set("control", control)
                .set("hybrid", hybrid);
        result.put("scheduled_injection", scheduled);
        if (scheduled) {
            result.set("injection_schedule", hybrid.path("injection_schedule").deepCopy());
        } else {
            result.putNull("injection_schedule");
        }
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
            String sourceType,
            String datasetId,
            String scenarioFamily,
            int maxTicks,
            long masterSeed,
            Long triggerSourceSequence,
            Long triggerTimestampNs,
            ObjectNode parameters,
            boolean inject) {
        loadDataSource(sourceType, datasetId, masterSeed);
        if (triggerSourceSequence != null || triggerTimestampNs != null) {
            if (!normalizedHistoricalKernelReplay) {
                throw new IllegalArgumentException(
                        "scheduled injection requires normalized historical Parquet data");
            }
            injectionSchedule = new InjectionScheduleState(
                    scenarioFamily,
                    triggerSourceSequence,
                    triggerTimestampNs,
                    parameters.deepCopy(),
                    injectionScheduleHash(
                            datasetId,
                            scenarioFamily,
                            masterSeed,
                            triggerSourceSequence,
                            triggerTimestampNs,
                            parameters),
                    inject);
            start();
        } else if (inject) {
            launchScenario(scenarioFamily, parameters);
        } else {
            start();
        }
        int advanced = 0;
        while (running && advanced < maxTicks) {
            advance();
            advanced++;
        }
        running = false;
        if (injectionSchedule != null && !injectionSchedule.triggered) {
            throw new IllegalArgumentException("injection trigger was not reached in the selected window");
        }
        if (injectionSchedule != null
                && injectionSchedule.triggered
                && tick < injectionSchedule.completionTick) {
            throw new IllegalArgumentException("max_ticks ended before the injection schedule completed");
        }
        if (inject && scenario == null) {
            throw new IllegalArgumentException("scheduled synthetic scenario was not launched");
        }
        ObjectNode summary = replaySummary(sourceType);
        summary.put("ticks_executed", advanced);
        return summary;
    }

    private void advance() {
        if (normalizedHistoricalKernelReplay) {
            advanceNormalizedHistoricalReplay();
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
        completeCanonicalTick();
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
        completeCanonicalTick();
        previousDepth = depthBefore;
        if (historicalCsv.eof()) {
            running = false;
        }
        JsonNode state = buildState();
        journal.append("snapshots/ticks.jsonl", state);
    }

    private void advanceNormalizedHistoricalReplay() {
        if (scheduledHistoricalRecords.isEmpty() && historical.eof()) {
            if (injectionSchedule != null
                    && injectionSchedule.triggered
                    && tick < injectionSchedule.completionTick) {
                advanceScheduledPostSourceTick();
            } else {
                running = false;
            }
            return;
        }
        tick++;
        BookSnapshot before = matching.book().snapshot(5);
        double depthBefore = topDepth(before);
        List<HistoricalMarketDataSource.HistoricalSnapshotRecord> records = new ArrayList<>();
        if (scheduledHistoricalRecords.isEmpty()) {
            records.addAll(historical.nextKernelBatch());
        } else {
            while (!scheduledHistoricalRecords.isEmpty()) {
                records.add(scheduledHistoricalRecords.removeFirst());
            }
        }
        HistoricalMarketDataSource.HistoricalSnapshotRecord triggerRecord =
                splitAtScheduledInjection(records);
        records.sort(Comparator.comparing(record -> new EventOrderKey(
                record.timestampNs(),
                EventPhase.HISTORICAL.code(),
                0,
                "HIST:" + historical.datasetId(),
                record.sourceSequence(),
                record.sourceSequence())));
        records.forEach(this::applyNormalizedHistoricalSnapshot);
        if (triggerRecord != null && injectionSchedule != null) {
            injectionSchedule.triggered = true;
            injectionSchedule.actualSourceSequence = triggerRecord.sourceSequence();
            injectionSchedule.actualTimestampNs = triggerRecord.timestampNs();
            injectionSchedule.completionTick = scenarioEndTick(
                    injectionSchedule.scenarioFamily,
                    tick,
                    injectionSchedule.parameters) + 1;
            if (injectionSchedule.inject) {
                armScenario(
                        normalizeScenario(injectionSchedule.scenarioFamily),
                        injectionSchedule.parameters,
                        tick,
                        triggerRecord.sourceSequence(),
                        triggerRecord.timestampNs());
            }
        }
        if ("hybrid".equals(replaySourceType)) {
            applyScenario();
        }
        matching.recordSnapshot(
                SNAPSHOT_DEPTH,
                new MutationContext(
                        tick, null, null, null, EventSource.EVENT_SOURCE_SIMULATION,
                        null, replayCurrentTimestampNs(), replayCurrentTimestampNs()));
        completeCanonicalTick();
        previousDepth = depthBefore;
        if (historical.eof()
                && scheduledHistoricalRecords.isEmpty()
                && (injectionSchedule == null
                        || !injectionSchedule.triggered
                        || tick >= injectionSchedule.completionTick)) {
            running = false;
        }
        journal.append("snapshots/ticks.jsonl", buildState());
    }

    private void advanceScheduledPostSourceTick() {
        tick++;
        BookSnapshot before = matching.book().snapshot(5);
        double depthBefore = topDepth(before);
        if ("hybrid".equals(replaySourceType)) {
            applyScenario();
        }
        matching.recordSnapshot(
                SNAPSHOT_DEPTH,
                new MutationContext(
                        tick, null, null, null, EventSource.EVENT_SOURCE_SIMULATION,
                        null, replayCurrentTimestampNs(), replayCurrentTimestampNs()));
        completeCanonicalTick();
        previousDepth = depthBefore;
        if (tick >= injectionSchedule.completionTick) {
            running = false;
        }
        journal.append("snapshots/ticks.jsonl", buildState());
    }

    private HistoricalMarketDataSource.HistoricalSnapshotRecord splitAtScheduledInjection(
            List<HistoricalMarketDataSource.HistoricalSnapshotRecord> records) {
        if (injectionSchedule == null || injectionSchedule.triggered || records.isEmpty()) {
            return null;
        }
        int triggerIndex = -1;
        for (int index = 0; index < records.size(); index++) {
            HistoricalMarketDataSource.HistoricalSnapshotRecord record = records.get(index);
            if (injectionSchedule.triggerSourceSequence != null
                    && record.sourceSequence() == injectionSchedule.triggerSourceSequence) {
                triggerIndex = index;
                break;
            }
            if (injectionSchedule.triggerTimestampNs != null
                    && record.timestampNs() >= injectionSchedule.triggerTimestampNs) {
                triggerIndex = index;
                break;
            }
        }
        if (triggerIndex < 0) {
            return null;
        }
        long triggerTimestamp = records.get(triggerIndex).timestampNs();
        while (!historical.eof() && records.get(records.size() - 1).timestampNs() == triggerTimestamp) {
            List<HistoricalMarketDataSource.HistoricalSnapshotRecord> next = historical.nextKernelBatch();
            if (next.isEmpty()) {
                break;
            }
            records.addAll(next);
        }
        int lastTieIndex = triggerIndex;
        while (lastTieIndex + 1 < records.size()
                && records.get(lastTieIndex + 1).timestampNs() == triggerTimestamp) {
            lastTieIndex++;
        }
        for (int index = lastTieIndex + 1; index < records.size(); index++) {
            scheduledHistoricalRecords.addLast(records.get(index));
        }
        records.subList(lastTieIndex + 1, records.size()).clear();
        return records.get(triggerIndex);
    }

    private void applyNormalizedHistoricalSnapshot(HistoricalMarketDataSource.HistoricalSnapshotRecord record) {
        normalizedAppliedRows++;
        normalizedAppliedSourceSequence = record.sourceSequence();
        normalizedAppliedTimestampNs = record.timestampNs();
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
            syncNormalizedHistoricalSide(Side.SIDE_BUY, record.bids(), historicalBidPrices, record);
            syncNormalizedHistoricalSide(Side.SIDE_SELL, record.asks(), historicalAskPrices, record);
            int depth = Math.max(1, historical.context(replaySourceType).path("depth").intValue());
            matching.recordSnapshot(normalizedHistoricalSourceSnapshot(record), depth, context);
        });
    }

    private BookSnapshot normalizedHistoricalSourceSnapshot(
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

    private void syncNormalizedHistoricalSide(
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
                        side, price, 0, normalizedHistoricalParticipantId(), "historical",
                        normalizedHistoricalLevelOrderId(side, price), record.timestampNs(),
                        null, null, null);
            }
        }
        desired.forEach((price, quantity) -> matching.book().updateAgentLevel(
                side, price, quantity, normalizedHistoricalParticipantId(), "historical",
                normalizedHistoricalLevelOrderId(side, price), record.timestampNs(),
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
        if (age > 0 && tick <= scenarioEndTick(scenario.family(), scenario.startTick(), scenarioParameters) + 1) {
            String stage = scenarioStage();
            ObjectNode event = event("red_team", scenario.agentId(), scenario.name() + " " + stage);
            event.put("scenario_id", scenario.id());
            event.put("scenario_name", scenario.name());
            event.put("scenario_family", scenario.family());
            event.put("stage", stage);
            addAgentEvent(event);
        }
    }

    private void applySpoofing(long age) {
        Side side = hybridAttackSide();
        int direction = side == Side.SIDE_SELL ? 1 : -1;
        long price = referencePriceTicks()
                + direction * (scenarioParameter("distance_levels") + Math.floorMod(scenario.seed(), 2))
                        * LEVEL_SPACING_TICKS;
        matching.book().updateAgentLevel(
                side, price, age < scenarioParameter("duration_ticks")
                        ? scenarioParameter("quantity_lots") : 0,
                scenario.agentId(), "abuser",
                scenarioOrderId("WALL"), tick, scenario.id(), scenario.name(), scenario.family());
    }

    private void applyLayering(long age) {
        long referencePrice = referencePriceTicks();
        Side side = hybridAttackSide();
        int direction = side == Side.SIDE_SELL ? 1 : -1;
        for (long level = scenarioParameter("first_level");
                level <= scenarioParameter("last_level"); level++) {
            matching.book().updateAgentLevel(
                    side,
                    referencePrice + direction * level * LEVEL_SPACING_TICKS,
                    age < scenarioParameter("duration_ticks")
                            ? scenarioParameter("base_quantity_lots")
                                    + level * scenarioParameter("level_increment_lots")
                            : 0,
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
        if (age >= scenarioParameter("duration_ticks")) {
            return;
        }
        long referencePrice = referencePriceTicks();
        for (int burst = 0; burst < scenarioParameter("bursts_per_tick"); burst++) {
            Side side = burst % 2 == 0 ? Side.SIDE_BUY : Side.SIDE_SELL;
            int direction = side == Side.SIDE_BUY ? -1 : 1;
            long price = referencePrice
                    + direction * (burst + scenarioParameter("start_distance_levels"))
                            * LEVEL_SPACING_TICKS;
            String orderId = scenarioOrderId("STUFF-" + age + "-" + burst);
            matching.book().updateAgentLevel(
                    side,
                    price,
                    scenarioParameter("quantity_lots"),
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
        int depthLevels = Math.toIntExact(scenarioParameter("depth_levels"));
        for (long price : matching.book().prices(Side.SIDE_BUY, depthLevels)) {
            matching.book().removeLevel(Side.SIDE_BUY, price);
        }
        for (long price : matching.book().prices(Side.SIDE_SELL, depthLevels)) {
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
        result.put("stream_id", streamId);
        result.put("latest_sequence", matching.latestEventSequence());
        result.put("retained_from_sequence", matching.firstRetainedSequence());
        result.put("retained_event_count", matching.retainedEventCount());
        result.put("archive_bytes", eventArchive.archiveBytes());
        if (streamError == null) {
            result.putNull("stream_error");
        } else {
            result.put("stream_error", streamError);
        }
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
        String stage = scenarioStage();
        ObjectNode result = mapper.createObjectNode()
                .put("scenario_id", scenario.id())
                .put("scenario_name", scenario.name())
                .put("scenario_family", scenario.family())
                .put("agent_id", scenario.agentId())
                .put("current_stage", stage)
                .put("start_tick", scenario.startTick())
                .put("attack_seed", scenario.seed())
                .put("status", stage);
        result.set("parameters", scenarioParameters.deepCopy());
        if (injectionSchedule == null) {
            result.putNull("injection_schedule");
        } else {
            result.set("injection_schedule", injectionScheduleJson());
        }
        result.putArray("stages");
        result.putArray("evidence");
        return result;
    }

    private String scenarioStage() {
        long durationTicks = "liquidity_evaporation".equals(scenario.family())
                ? 1
                : scenarioParameter("duration_ticks");
        return scenario.stage(tick, durationTicks);
    }

    private ObjectNode groundTruthLabel() {
        if (scenario == null) {
            throw new IllegalStateException("ground truth requires an active synthetic scenario");
        }
        long endTick = scenarioEndTick(scenario.family(), scenario.startTick(), scenarioParameters);
        ObjectNode result = mapper.createObjectNode()
                .put("schema_version", "scenario_ground_truth_v1")
                .put("scenario_id", scenario.id())
                .put("scenario_family", scenario.family())
                .put("source", "synthetic_scenario")
                .put("has_attack", true)
                .put("start_tick", scenario.startTick())
                .put("end_tick", endTick);
        result.set("parameters", scenarioParameters.deepCopy());
        if (injectionSchedule == null) {
            result.putNull("trigger_source_sequence");
            result.putNull("trigger_timestamp_ns");
            result.putNull("start_exchange_timestamp_ns");
            result.putNull("end_exchange_timestamp_ns");
            result.putNull("schedule_sha256");
        } else {
            putNullableLong(result, "trigger_source_sequence", injectionSchedule.actualSourceSequence);
            putNullableLong(result, "trigger_timestamp_ns", injectionSchedule.actualTimestampNs);
            putNullableLong(result, "start_exchange_timestamp_ns", injectionSchedule.actualTimestampNs);
            putNullableLong(result, "end_exchange_timestamp_ns", exchangeTimestampAtTick(endTick));
            result.put("schedule_sha256", injectionSchedule.scheduleSha256);
        }
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
            case "spoofing_like_wall", "layering_like" ->
                    scenario.startTick() + scenarioParameter("duration_ticks");
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
                    java.util.stream.LongStream.rangeClosed(
                                    scenarioParameter("first_level"),
                                    scenarioParameter("last_level"))
                            .mapToObj(level -> scenarioOrderId("LAYER-" + level))
                            .toArray(String[]::new));
            case "quote_stuffing" -> {
                List<String> ids = new ArrayList<>();
                for (int age = 0; age < scenarioParameter("duration_ticks"); age++) {
                    for (int burst = 0; burst < scenarioParameter("bursts_per_tick"); burst++) {
                        ids.add(scenarioOrderId("STUFF-" + age + "-" + burst));
                    }
                }
                yield List.copyOf(ids);
            }
            case "liquidity_evaporation" -> List.of();
            default -> throw new IllegalStateException("unsupported scenario family");
        };
    }

    private static long scenarioEndTick(String family, long startTick, ObjectNode parameters) {
        return switch (family) {
            case "spoofing_like_wall", "layering_like" ->
                    startTick + parameters.path("duration_ticks").longValue();
            case "quote_stuffing" ->
                    startTick + parameters.path("duration_ticks").longValue() - 1;
            case "liquidity_evaporation" -> startTick + 1;
            default -> throw new IllegalStateException("unsupported scenario family");
        };
    }

    private Long exchangeTimestampAtTick(long targetTick) {
        if (targetTick > tick) {
            return null;
        }
        Long latest = null;
        for (EventStreamSummary.ValidationPoint point : eventSummary.validationPoints()) {
            if (point.tick() > targetTick) {
                break;
            }
            latest = point.exchangeTimestampNs();
        }
        return latest;
    }

    private static void putNullableLong(ObjectNode node, String field, Long value) {
        if (value == null) {
            node.putNull(field);
        } else {
            node.put(field, value);
        }
    }

    private ObjectNode replaySummary(String sourceType) {
        ObjectNode summary = mapper.createObjectNode()
                .put("mode", sourceType)
                .put("dataset_id", replayDatasetId())
                .put("master_seed", replayMasterSeed)
                .put("source_row_count", replayRowCount())
                .put("source_rows_replayed", replayPosition())
                .put("events_sha256", replayEventsSha256())
                .put("canonical_event_count", eventSummary.eventCount())
                .put("stream_hash", eventSummary.streamHashHex())
                .put("historical_event_hash", sourceEventHash(EventSource.EVENT_SOURCE_HISTORICAL))
                .put("synthetic_event_hash", sourceEventHash(EventSource.EVENT_SOURCE_SIMULATION))
                .put("historical_snapshot_stream_hash", historicalSnapshotStreamHash())
                .put("historical_source_sequences", eventSummary.historicalSourceSequences());
        summary.set("source_integrity", replaySourceIntegrity());
        if (injectionSchedule == null) {
            summary.putNull("injection_schedule");
        } else {
            summary.set("injection_schedule", injectionScheduleJson());
        }
        ObjectNode counts = summary.putObject("event_counts");
        ObjectNode sourceCounts = counts.putObject("by_source");
        ObjectNode typeCounts = counts.putObject("by_type");
        for (EventSource source : List.of(
                EventSource.EVENT_SOURCE_HISTORICAL,
                EventSource.EVENT_SOURCE_SIMULATION)) {
            long count = eventSummary.sourceCount(source);
            if (count > 0) {
                sourceCounts.put(
                        source == EventSource.EVENT_SOURCE_HISTORICAL ? "historical" : "simulation",
                        count);
            }
        }
        for (ExchangeEvent.PayloadCase type : ExchangeEvent.PayloadCase.values()) {
            long count = eventSummary.typeCount(type);
            if (count > 0) {
                typeCounts.put(type.name().toLowerCase(), count);
            }
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
        eventSummary.scenarioEvents().stream()
                .map(this::exchangeEventJson)
                .forEach(syntheticEvents::add);
        return summary;
    }

    private String historicalSnapshotStreamHash() {
        return eventSummary.historicalSnapshotHashHex();
    }

    private ArrayNode validationTrace() {
        ArrayNode trace = mapper.createArrayNode();
        trace.add(validationObservation(0, 0, BookSnapshot.getDefaultInstance(), new long[4]));
        eventSummary.validationPoints().stream()
                .map(point -> validationObservation(
                        point.tick(),
                        point.exchangeTimestampNs(),
                        point.book(),
                        point.eventFlow()))
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
        return eventSummary.sourceHashHex(source);
    }

    private double averageCancelledLifetimeMs(List<ExchangeEvent> currentEvents) {
        return eventSummary.averageCancellationLifetimeMs(currentEvents);
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
        return historicalCsv.loaded() || normalizedHistoricalKernelReplay;
    }

    private void ensureReplayArchiveCapacity() {
        if (!kernelHistoricalLoaded()) {
            return;
        }
        int depth = Math.max(1, replayContext().path("depth").asInt(SNAPSHOT_DEPTH));
        try {
            long maximumEventsPerRow = Math.addExact(Math.multiplyExact(2L, depth), 2L);
            long estimatedBytes = Math.multiplyExact(
                    Math.multiplyExact(replayRowCount(), maximumEventsPerRow),
                    384L);
            if (estimatedBytes > eventArchive.maxStreamBytes()) {
                throw new CanonicalEventArchive.ArchiveCapacityExceededException(
                        "archive_capacity_insufficient: estimated replay archive "
                                + estimatedBytes
                                + " bytes exceeds configured stream quota "
                                + eventArchive.maxStreamBytes()
                                + " bytes");
            }
        } catch (ArithmeticException exception) {
            throw new CanonicalEventArchive.ArchiveCapacityExceededException(
                    "archive_capacity_insufficient: replay archive estimate overflowed");
        }
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
                : normalizedAppliedTimestampNs;
    }

    private long replayPosition() {
        return historicalCsv.loaded()
                ? historicalCsv.replayPosition()
                : normalizedAppliedRows;
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
        if (historicalCsv.loaded()) {
            return historicalCsv.context(replaySourceType);
        }
        ObjectNode context = (ObjectNode) historical.context(replaySourceType).deepCopy();
        context.put("source_sequence", normalizedAppliedSourceSequence);
        context.put("replay_position", normalizedAppliedRows);
        context.put("exchange_timestamp_ns", normalizedAppliedTimestampNs);
        context.put("progress", historical.rowCount() == 0
                ? 0
                : Math.min(1.0, (double) normalizedAppliedRows / historical.rowCount()));
        context.put("eof", historical.eof() && scheduledHistoricalRecords.isEmpty());
        return context;
    }

    private String normalizedHistoricalParticipantId() {
        return "HIST:" + replayDatasetId() + ":P:"
                + historical.historicalSourceType().toUpperCase(Locale.ROOT);
    }

    private String normalizedHistoricalLevelOrderId(Side side, long priceTicks) {
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
        beginEventStream();
        IntegerOrderBook book = new IntegerOrderBook(UNIT_NANOS, UNIT_NANOS);
        book.initialize(REFERENCE_PRICE_TICKS, BASELINE_LEVELS, LEVEL_SPACING_TICKS, BASE_QUANTITY_LOTS, "normal");
        return new IntegerMatchingEngine(
                book,
                "BTCUSDT",
                "SIM",
                EventSource.EVENT_SOURCE_SIMULATION,
                eventHistoryCapacity,
                this::acceptCanonicalEvent);
    }

    private IntegerMatchingEngine newHistoricalMatchingEngine() {
        beginEventStream();
        IntegerOrderBook book =
                new IntegerOrderBook(replayPriceTickSizeNanos(), replayQuantityLotSizeNanos());
        return new IntegerMatchingEngine(
                book,
                replaySymbol(),
                replayVenue(),
                EventSource.EVENT_SOURCE_SIMULATION,
                eventHistoryCapacity,
                this::acceptCanonicalEvent);
    }

    private void beginEventStream() {
        eventSummary = new EventStreamSummary();
        streamId = eventArchive.beginStream();
        streamError = null;
        metricsRetainedEventCount = 0;
        metricsLatestSequence = 0;
        metricsArchiveBytes = 0;
    }

    private void acceptCanonicalEvent(ExchangeEvent event) {
        eventSummary.accept(event);
        eventArchive.append(event);
    }

    private void completeCanonicalTick() {
        try {
            eventArchive.flushCompletedTick();
            if (eventArchive.latestPersistedSequence() != matching.latestEventSequence()) {
                throw new IllegalStateException("canonical archive did not reach the completed tick sequence");
            }
            metricsRetainedEventCount = matching.retainedEventCount();
            metricsLatestSequence = matching.latestEventSequence();
            metricsArchiveBytes = eventArchive.archiveBytes();
        } catch (RuntimeException exception) {
            running = false;
            streamError = exception.getMessage();
            throw exception;
        }
    }

    int retainedEventCountMetric() {
        return metricsRetainedEventCount;
    }

    long latestSequenceMetric() {
        return metricsLatestSequence;
    }

    long archiveBytesMetric() {
        return metricsArchiveBytes;
    }

    private void addAgentEvent(ObjectNode event) {
        agentEvents.addFirst(event);
        while (agentEvents.size() > AGENT_EVENT_WINDOW) {
            agentEvents.removeLast();
        }
        journal.append("events/events.jsonl", event);
    }

    @PreDestroy
    synchronized void close() {
        running = false;
        historical.close();
        historicalCsv.clear();
        eventArchive.close();
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

    private ObjectNode resolveScenarioParameters(String family, Map<String, Object> overrides) {
        ObjectNode result = mapper.createObjectNode();
        switch (family) {
            case "spoofing_like_wall" -> result
                    .put("quantity_lots", 30_000)
                    .put("duration_ticks", 3)
                    .put("distance_levels", 2);
            case "layering_like" -> result
                    .put("base_quantity_lots", 10_000)
                    .put("level_increment_lots", 1_000)
                    .put("duration_ticks", 4)
                    .put("first_level", 2)
                    .put("last_level", 4);
            case "quote_stuffing" -> result
                    .put("quantity_lots", 1_000)
                    .put("duration_ticks", 6)
                    .put("bursts_per_tick", 6)
                    .put("start_distance_levels", 2);
            case "liquidity_evaporation" -> result.put("depth_levels", 5);
            default -> throw new IllegalArgumentException("unknown scenario: " + family);
        }
        for (Map.Entry<String, Object> override : overrides.entrySet()) {
            if (!result.has(override.getKey())) {
                throw new IllegalArgumentException("unsupported scenario parameter: " + override.getKey());
            }
            long value;
            try {
                value = new BigDecimal(String.valueOf(override.getValue())).longValueExact();
            } catch (ArithmeticException | NumberFormatException exception) {
                throw new IllegalArgumentException(
                        "scenario parameter must be an integer: " + override.getKey(), exception);
            }
            long maximum = override.getKey().contains("quantity") || override.getKey().contains("increment")
                    ? 1_000_000_000L
                    : 100L;
            if (value < 1 || value > maximum) {
                throw new IllegalArgumentException(
                        "scenario parameter is outside its supported range: " + override.getKey());
            }
            result.put(override.getKey(), value);
        }
        if (result.has("first_level")
                && result.path("first_level").longValue() > result.path("last_level").longValue()) {
            throw new IllegalArgumentException("first_level must not exceed last_level");
        }
        return result;
    }

    private long scenarioParameter(String name) {
        if (scenarioParameters == null || !scenarioParameters.path(name).isIntegralNumber()) {
            throw new IllegalStateException("scenario parameter is unavailable: " + name);
        }
        return scenarioParameters.path(name).longValue();
    }

    private String injectionScheduleHash(
            String datasetId,
            String family,
            long masterSeed,
            Long triggerSourceSequence,
            Long triggerTimestampNs,
            ObjectNode parameters) {
        return sha256Hex(
                datasetId + "\n" + family + "\n" + masterSeed + "\n"
                        + triggerSourceSequence + "\n" + triggerTimestampNs + "\n" + parameters);
    }

    private static String sha256Hex(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
    }

    private ObjectNode injectionScheduleJson() {
        if (injectionSchedule == null) {
            throw new IllegalStateException("injection schedule is unavailable");
        }
        ObjectNode result = mapper.createObjectNode()
                .put("schema_version", "historical_injection_schedule_v1")
                .put("scenario_family", injectionSchedule.scenarioFamily)
                .put("schedule_sha256", injectionSchedule.scheduleSha256)
                .put("triggered", injectionSchedule.triggered)
                .put("completion_tick", injectionSchedule.completionTick);
        if (injectionSchedule.triggerSourceSequence == null) {
            result.putNull("requested_source_sequence");
        } else {
            result.put("requested_source_sequence", injectionSchedule.triggerSourceSequence);
        }
        if (injectionSchedule.triggerTimestampNs == null) {
            result.putNull("requested_timestamp_ns");
        } else {
            result.put("requested_timestamp_ns", injectionSchedule.triggerTimestampNs);
        }
        if (injectionSchedule.actualSourceSequence == null) {
            result.putNull("actual_source_sequence");
        } else {
            result.put("actual_source_sequence", injectionSchedule.actualSourceSequence);
        }
        if (injectionSchedule.actualTimestampNs == null) {
            result.putNull("actual_timestamp_ns");
        } else {
            result.put("actual_timestamp_ns", injectionSchedule.actualTimestampNs);
        }
        result.set("parameters", injectionSchedule.parameters.deepCopy());
        return result;
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

    private static final class InjectionScheduleState {
        private final String scenarioFamily;
        private final Long triggerSourceSequence;
        private final Long triggerTimestampNs;
        private final ObjectNode parameters;
        private final String scheduleSha256;
        private final boolean inject;
        private boolean triggered;
        private Long actualSourceSequence;
        private Long actualTimestampNs;
        private long completionTick;

        private InjectionScheduleState(
                String scenarioFamily,
                Long triggerSourceSequence,
                Long triggerTimestampNs,
                ObjectNode parameters,
                String scheduleSha256,
                boolean inject) {
            this.scenarioFamily = scenarioFamily;
            this.triggerSourceSequence = triggerSourceSequence;
            this.triggerTimestampNs = triggerTimestampNs;
            this.parameters = parameters;
            this.scheduleSha256 = scheduleSha256;
            this.inject = inject;
        }
    }
}
