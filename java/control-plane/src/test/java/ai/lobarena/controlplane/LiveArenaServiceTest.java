package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ai.lobarena.kernel.determinism.DeterministicValues;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class LiveArenaServiceTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void ticksWithJavaOrchestratedAgentsAndMaintainsTwoSidedBook(@TempDir Path output) {
        LiveArenaService arena = arena(output, mapper.readTree("""
                {"agent_ids":["REMOTE_MM_001"],"intents":[
                  {"tick":1,"agent_id":"REMOTE_MM_001","kind":"set_level","side":"bid","price":68124.0,"quantity":2.5}
                ]}
                """));

        arena.start();
        JsonNode state = arena.stepForTest();

        assertThat(state.path("tick").longValue()).isEqualTo(1);
        assertThat(state.path("running").booleanValue()).isTrue();
        assertThat(state.path("active_agents").get(0).textValue()).isEqualTo("REMOTE_MM_001");
        assertThat(state.path("book").path("bids")).isNotEmpty();
        assertThat(state.path("book").path("asks")).isNotEmpty();
        assertThat(state.path("exchange_events").get(state.path("exchange_events").size() - 1)
                .path("event_type").textValue()).isEqualTo("snapshot");
        assertThat(Files.exists(output.resolve("snapshots/ticks.jsonl"))).isTrue();
    }

    @Test
    void appliesMarketIntentWithoutRequiringLimitPrice(@TempDir Path output) {
        LiveArenaService arena = arena(output, mapper.readTree("""
                {"agent_ids":["REMOTE_TAKER_001"],"intents":[
                  {"tick":1,"agent_id":"REMOTE_TAKER_001","kind":"market","side":"buy","quantity":0.5}
                ]}
                """));

        JsonNode state = arena.stepForTest();

        assertThat(state.path("tick").longValue()).isEqualTo(1);
        assertThat(state.path("events").get(0).path("agent_id").textValue()).isEqualTo("REMOTE_TAKER_001");
        assertThat(state.path("exchange_events")).anyMatch(
                event -> event.path("event_type").textValue().equals("execute"));
    }

    @Test
    void scenarioProgressCreatesDeterministicDetectorIncidentAndResetClearsIt(@TempDir Path output) {
        LiveArenaService arena = arena(output, mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        arena.launchScenario("spoofing_like_wall");

        JsonNode state = null;
        for (int index = 0; index < 3; index++) {
            state = arena.stepForTest();
        }

        assertThat(state.path("active_scenario").path("scenario_family").textValue())
                .isEqualTo("spoofing_like_wall");
        assertThat(state.path("detectors").path("alerts")).isNotEmpty();
        assertThat(state.path("incidents")).hasSize(1);
        assertThat(state.path("incidents").get(0).path("type").textValue())
                .isEqualTo("spoofing_like_detector");
        assertThat(Files.exists(output.resolve("incidents/incidents.jsonl"))).isTrue();

        JsonNode reset = arena.reset();
        assertThat(reset.path("tick").longValue()).isZero();
        assertThat(reset.path("active_scenario").isNull()).isTrue();
        assertThat(reset.path("incidents")).isEmpty();
    }

    @Test
    void exchangeReplayUsesCursorAndBoundedLimit(@TempDir Path output) {
        LiveArenaService arena = arena(output, mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        arena.stepForTest();
        arena.stepForTest();

        JsonNode replay = arena.exchangeEvents(0, 1);

        assertThat(replay.path("events")).hasSize(1);
        assertThat(replay.path("has_more").booleanValue()).isTrue();
        assertThat(replay.path("next_after_sequence").longValue()).isPositive();
    }

    @Test
    void exchangeReplayReadsEventsThatHaveRotatedOutOfMemory(@TempDir Path output) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        LiveArenaService arena = new LiveArenaService(
                mapper,
                new AgentOrchestrator(List.of(), client),
                new ArenaJournal(output, mapper),
                output.resolve("unused-parquet"),
                output.resolve("unused-csv"),
                250,
                42,
                2,
                2,
                1_000_000);
        for (int index = 0; index < 4; index++) {
            arena.stepForTest();
        }

        JsonNode state = arena.state();
        JsonNode replay = arena.exchangeEvents(0, 4);

        assertThat(state.path("retained_event_count").intValue()).isEqualTo(2);
        assertThat(state.path("retained_from_sequence").longValue()).isEqualTo(3);
        assertThat(replay.path("events"))
                .extracting(event -> event.path("sequence").longValue())
                .containsExactly(1L, 2L, 3L, 4L);
        assertThat(replay.path("stream_id").textValue()).isEqualTo(state.path("stream_id").textValue());
    }

    @Test
    void historicalReplayPreservesLifecycleProvenanceAndHasNoGroundTruth(@TempDir Path output) {
        LiveArenaService arena = historicalArena(output, 4);
        JsonNode loaded = arena.loadDataSource("historical", "sample-btcusdt-0945");

        assertThat(loaded.path("market_data").path("source_type").textValue()).isEqualTo("historical");
        JsonNode state = null;
        for (int index = 0; index < 3; index++) {
            state = arena.stepForTest();
        }

        assertThat(state.path("active_scenario").isNull()).isTrue();
        assertThat(state.path("historical_events")).isNotEmpty();
        assertThat(state.path("exchange_events"))
                .filteredOn(event -> "historical".equals(event.path("source").textValue()))
                .allMatch(event -> event.path("source_sequence").isIntegralNumber())
                .allMatch(event -> event.path("scenario_id").isNull());
        assertThat(state.path("exchange_events"))
                .filteredOn(event -> event.hasNonNull("order_id"))
                .allMatch(event -> event.path("order_id").textValue().startsWith("HIST:"));
        assertThat(state.path("detectors").toString()).doesNotContain("scenario");
    }

    @Test
    void rejectsReplayBeforeRunningWhenTheArchiveQuotaIsInsufficient(@TempDir Path output) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        LiveArenaService arena = new LiveArenaService(
                mapper,
                new AgentOrchestrator(List.of(), client),
                new ArenaJournal(output, mapper),
                output.resolve("unused-parquet"),
                HistoricalCsvMarketDataSourceTest.fixtureRoot(),
                4,
                42,
                50,
                25,
                1);
        arena.loadDataSource("historical", "sample-btcusdt-0945");

        org.assertj.core.api.Assertions.assertThatThrownBy(arena::start)
                .isInstanceOf(CanonicalEventArchive.ArchiveCapacityExceededException.class)
                .hasMessageContaining("archive_capacity_insufficient");
        assertThat(arena.state().path("running").booleanValue()).isFalse();
    }

    @Test
    void hybridReplayMergesHistoryBeforeCollisionSafeSyntheticAttack(@TempDir Path output) {
        LiveArenaService arena = historicalArena(output, 12);
        arena.loadDataSource("hybrid", "sample-btcusdt-0945");
        JsonNode label = arena.launchScenario("spoofing_like_wall");
        JsonNode state = arena.stepForTest();

        assertThat(label.path("agent_id").textValue()).startsWith("SYN:");
        assertThat(state.path("exchange_events"))
                .filteredOn(event -> "historical".equals(event.path("source").textValue()))
                .allMatch(event -> {
                    String participant = event.hasNonNull("agent_id")
                            ? event.path("agent_id").textValue()
                            : event.path("aggressor_agent_id").asText("");
                    return participant.startsWith("HIST:");
                });
        assertThat(state.path("exchange_events"))
                .filteredOn(event -> event.hasNonNull("scenario_id"))
                .allMatch(event -> event.path("order_id").asText("").startsWith("SYN:"));
        int firstSynthetic = -1;
        int lastHistorical = -1;
        for (int index = 0; index < state.path("exchange_events").size(); index++) {
            JsonNode event = state.path("exchange_events").get(index);
            if ("historical".equals(event.path("source").textValue())) {
                lastHistorical = index;
            } else if (event.hasNonNull("scenario_id") && firstSynthetic < 0) {
                firstSynthetic = index;
            }
        }
        assertThat(firstSynthetic).isGreaterThan(lastHistorical);
        assertThat(state.path("detectors").path("alerts"))
                .anyMatch(alert -> "spoofing_like_detector".equals(alert.path("name").textValue()));
    }

    @Test
    void comparisonUsesSameWindowAndLabelsOnlyHybridRun(@TempDir Path output) {
        LiveArenaService arena = historicalArena(output, 4);

        JsonNode comparison =
                arena.runReplayComparison("sample-btcusdt-0945", "quote_stuffing", 10);

        assertThat(comparison.path("control").path("source_row_count").longValue()).isEqualTo(12);
        assertThat(comparison.path("hybrid").path("source_row_count").longValue()).isEqualTo(12);
        assertThat(comparison.path("control").path("stream_id").textValue()).isNotBlank();
        assertThat(comparison.path("hybrid").path("stream_id").textValue())
                .isNotBlank()
                .isNotEqualTo(comparison.path("control").path("stream_id").textValue());
        assertThat(comparison.path("control").path("ground_truth").isNull()).isTrue();
        assertThat(comparison.path("hybrid").path("ground_truth").path("has_attack").booleanValue())
                .isTrue();
        assertThat(comparison.path("hybrid").path("ground_truth").path("order_ids"))
                .allMatch(id -> id.textValue().startsWith("SYN:"));
        assertThat(comparison.path("control").path("detector_alert_ticks")
                        .path("quote_stuffing_detector").isMissingNode())
                .isTrue();
        assertThat(comparison.path("hybrid").path("detector_alert_ticks")
                        .path("quote_stuffing_detector"))
                .as(comparison.toPrettyString())
                .isNotEmpty();
        assertThat(comparison.path("events_sha256").textValue()).isNotBlank();
        assertThat(Files.exists(output.resolve("historical-replay/comparisons.jsonl"))).isTrue();

        JsonNode repeated =
                arena.runReplayComparison("sample-btcusdt-0945", "quote_stuffing", 10);
        assertThat(repeated.path("control").path("stream_hash").textValue())
                .isEqualTo(comparison.path("control").path("stream_hash").textValue());
        assertThat(repeated.path("hybrid").path("stream_hash").textValue())
                .isEqualTo(comparison.path("hybrid").path("stream_hash").textValue());
        assertThat(comparison.path("determinism").path("control_stream_match").booleanValue())
                .isTrue();
        assertThat(comparison.path("determinism").path("hybrid_stream_match").booleanValue())
                .isTrue();
        assertThat(comparison.path("determinism").path("control_trace_match").booleanValue())
                .isTrue();
        assertThat(comparison.path("determinism").path("hybrid_trace_match").booleanValue())
                .isTrue();
        JsonNode controlAttackTick = comparison.path("control").path("validation_trace").get(1);
        JsonNode hybridAttackTick = comparison.path("hybrid").path("validation_trace").get(1);
        assertThat(hybridAttackTick.path("book_hash").textValue())
                .isEqualTo(controlAttackTick.path("book_hash").textValue());
        assertThat(hybridAttackTick.path("message_count").longValue())
                .isGreaterThan(controlAttackTick.path("message_count").longValue());
        assertThat(hybridAttackTick.path("cancel_count").longValue())
                .isGreaterThan(controlAttackTick.path("cancel_count").longValue());
    }

    @Test
    void comparisonGroundTruthUsesDisjointPhaseWindows(@TempDir Path output) {
        for (String family : List.of("spoofing_like_wall", "layering_like", "quote_stuffing")) {
            LiveArenaService arena = historicalArena(output.resolve(family), 4);

            JsonNode groundTruth = arena.runReplayComparison(
                            "sample-btcusdt-0945", family, 10)
                    .path("hybrid")
                    .path("ground_truth");
            JsonNode pressure = groundTruth.path("phase_windows").path("pressure_phase");
            JsonNode cancellation = groundTruth.path("phase_windows").path("cancellation_phase");

            assertThat(pressure.path("start_tick").longValue())
                    .as(family)
                    .isEqualTo(groundTruth.path("start_tick").longValue());
            assertThat(pressure.path("end_tick").longValue())
                    .as(family)
                    .isLessThanOrEqualTo(groundTruth.path("end_tick").longValue());
            if (family.equals("quote_stuffing")) {
                assertThat(cancellation.isMissingNode()).as(family).isTrue();
                assertThat(pressure.path("end_tick").longValue())
                        .as(family)
                        .isEqualTo(groundTruth.path("end_tick").longValue());
            } else {
                assertThat(cancellation.path("start_tick").longValue())
                        .as(family)
                        .isEqualTo(pressure.path("end_tick").longValue() + 1);
                assertThat(cancellation.path("end_tick").longValue())
                        .as(family)
                        .isEqualTo(groundTruth.path("end_tick").longValue());
            }
        }
    }

    @Test
    void lobsterHybridIsDeterministicSeededAndPreservesEveryHistoricalMessage(@TempDir Path root)
            throws Exception {
        Path registry = createLobsterDataset(root.resolve("lobster"));
        LiveArenaService arena = lobsterArena(root.resolve("output"), registry, 1);

        JsonNode first = arena.runReplayComparison(
                "lobster-spy-fixture", "layering_like", 20, 7);
        JsonNode repeated = arena.runReplayComparison(
                "lobster-spy-fixture", "layering_like", 20, 7);
        long firstAttackSeed = DeterministicValues.deriveStreamSeed(
                7, "hybrid:lobster-spy-fixture:layering_like:1");
        long differentMasterSeed = 8;
        while ((DeterministicValues.deriveStreamSeed(
                                differentMasterSeed,
                                "hybrid:lobster-spy-fixture:layering_like:1")
                        & 1L)
                == (firstAttackSeed & 1L)) {
            differentMasterSeed++;
        }
        JsonNode differentSeed = arena.runReplayComparison(
                "lobster-spy-fixture", "layering_like", 20, differentMasterSeed);

        assertThat(first.path("control").path("source_rows_replayed").longValue()).isEqualTo(8);
        assertThat(first.path("hybrid").path("source_rows_replayed").longValue()).isEqualTo(8);
        assertThat(first.path("control").path("historical_source_sequences").longValue()).isEqualTo(8);
        assertThat(first.path("hybrid").path("historical_source_sequences").longValue()).isEqualTo(8);
        assertThat(first.path("control").path("source_integrity").path("validated").booleanValue())
                .isTrue();
        assertThat(first.path("control").path("source_integrity").path("paired_rows").longValue())
                .isEqualTo(8);
        assertThat(first.path("control").path("source_integrity").path("output_sha256"))
                .isEqualTo(first.path("hybrid").path("source_integrity").path("output_sha256"));
        assertThat(repeated.path("control").path("stream_hash").textValue())
                .isEqualTo(first.path("control").path("stream_hash").textValue());
        assertThat(repeated.path("hybrid").path("stream_hash").textValue())
                .isEqualTo(first.path("hybrid").path("stream_hash").textValue());
        assertThat(differentSeed.path("control").path("historical_event_hash").textValue())
                .isEqualTo(first.path("control").path("historical_event_hash").textValue());
        assertThat(differentSeed.path("hybrid").path("historical_event_hash").textValue())
                .isEqualTo(first.path("hybrid").path("historical_event_hash").textValue());
        assertThat(differentSeed.path("hybrid").path("synthetic_event_hash").textValue())
                .isNotEqualTo(first.path("hybrid").path("synthetic_event_hash").textValue());
        assertThat(first.path("control").path("historical_snapshot_stream_hash").textValue())
                .isEqualTo(first.path("hybrid").path("historical_snapshot_stream_hash").textValue());
        assertThat(repeated.path("control").path("validation_trace"))
                .isEqualTo(first.path("control").path("validation_trace"));
        assertThat(repeated.path("hybrid").path("validation_trace"))
                .isEqualTo(first.path("hybrid").path("validation_trace"));
        for (int index = 0; index < first.path("control").path("validation_trace").size(); index++) {
            JsonNode controlObservation = first.path("control").path("validation_trace").get(index);
            JsonNode hybridObservation = first.path("hybrid").path("validation_trace").get(index);
            long observationTick = controlObservation.path("tick").longValue();
            assertThat(hybridObservation.path("tick").longValue()).isEqualTo(observationTick);
            if (observationTick == 0 || observationTick >= 5) {
                assertThat(hybridObservation.path("book_hash").textValue())
                        .as(
                                "book outside the layering causal neighbourhood at tick %s%ncontrol=%s%nhybrid=%s",
                                observationTick,
                                controlObservation,
                                hybridObservation)
                        .isEqualTo(controlObservation.path("book_hash").textValue());
            } else {
                assertThat(hybridObservation.path("book_hash").textValue())
                        .as("intended layering impact at tick %s", observationTick)
                        .isNotEqualTo(controlObservation.path("book_hash").textValue());
            }
        }
        assertThat(first.path("hybrid").path("synthetic_events"))
                .allMatch(event -> event.path("tick").longValue() >= 1
                        && event.path("tick").longValue() <= 5);
        assertThat(first.path("control").path("ground_truth").isNull()).isTrue();
        assertThat(first.path("hybrid").path("ground_truth").path("source").textValue())
                .isEqualTo("synthetic_scenario");

        arena.loadDataSource("hybrid", "lobster-spy-fixture", 7);
        arena.launchScenario("spoofing_like_wall");
        JsonNode live = arena.stepForTest();
        JsonNode liveReplay = arena.exchangeEvents(0, 10);
        assertThat(live.path("detectors").toString())
                .doesNotContain("scenario", "attack_seed", "SYN:");
        assertThat(liveReplay.path("events")).isNotEmpty();
        assertThat(liveReplay.path("latest_sequence").longValue()).isPositive();
        int lastHistorical = -1;
        int firstSynthetic = -1;
        for (int index = 0; index < live.path("exchange_events").size(); index++) {
            JsonNode event = live.path("exchange_events").get(index);
            if ("historical".equals(event.path("source").textValue())) {
                lastHistorical = index;
            } else if (event.hasNonNull("scenario_id") && firstSynthetic < 0) {
                firstSynthetic = index;
            }
        }
        assertThat(firstSynthetic).isGreaterThan(lastHistorical);
    }

    @Test
    void normalizedItchReplayUsesManifestSourceInHistoricalParticipantIds(@TempDir Path root)
            throws Exception {
        Path registry = createLobsterDataset(root.resolve("itch"));
        Path manifestPath = registry.resolve("lobster-spy-fixture/manifest.json");
        String manifest = Files.readString(manifestPath)
                .replace("\"source_type\": \"lobster\"", "\"source_type\": \"nasdaq_itch\"")
                .replace("\"symbol\": \"SPY\"", "\"format\": \"itch_parquet_v1\",\n"
                        + "                  \"venue\": \"XNAS\",\n"
                        + "                  \"symbol\": \"SPY\"");
        Files.writeString(manifestPath, manifest);
        LiveArenaService arena = lobsterArena(root.resolve("output"), registry, 1);

        JsonNode loaded = arena.loadDataSource("historical", "lobster-spy-fixture");
        JsonNode state = arena.stepForTest();

        assertThat(loaded.path("market_data").path("historical_source_type").textValue())
                .isEqualTo("nasdaq_itch");
        assertThat(state.path("exchange_events"))
                .filteredOn(event -> "historical".equals(event.path("source").textValue()))
                .anyMatch(event -> event.path("agent_id").asText("").contains(":P:NASDAQ_ITCH"));
    }

    @Test
    void scheduledInjectionSplitsBothRunsAtExactSourceRowAndOrdersTimestampTiesFirst(
            @TempDir Path root) throws Exception {
        Path registry = createLobsterDataset(root.resolve("scheduled"));
        LiveArenaService arena = lobsterArena(root.resolve("output"), registry, 8);

        JsonNode comparison = arena.runReplayComparison(
                "lobster-spy-fixture",
                "spoofing_like_wall",
                20,
                7,
                3L,
                null,
                Map.of("quantity_lots", 12_345));

        JsonNode controlSchedule = comparison.path("control").path("injection_schedule");
        JsonNode hybridSchedule = comparison.path("hybrid").path("injection_schedule");
        JsonNode label = comparison.path("hybrid").path("ground_truth");
        assertThat(controlSchedule).isEqualTo(hybridSchedule);
        assertThat(hybridSchedule.path("actual_source_sequence").longValue()).isEqualTo(3);
        assertThat(hybridSchedule.path("actual_timestamp_ns").longValue())
                .isEqualTo(34_200_000_000_003L);
        assertThat(hybridSchedule.path("parameters").path("quantity_lots").longValue())
                .isEqualTo(12_345);
        assertThat(label.path("trigger_source_sequence").longValue()).isEqualTo(3);
        assertThat(label.path("start_exchange_timestamp_ns").longValue())
                .isEqualTo(34_200_000_000_003L);
        assertThat(label.path("end_exchange_timestamp_ns").isIntegralNumber()).isTrue();
        assertThat(label.path("schedule_sha256").textValue())
                .isEqualTo(hybridSchedule.path("schedule_sha256").textValue());
        assertThat(comparison.path("determinism").path("hybrid_trace_match").booleanValue())
                .isTrue();

        JsonNode events = arena.exchangeEvents(0, 1_000).path("events");
        long firstSyntheticAtTrigger = Long.MAX_VALUE;
        long lastHistoricalAtTrigger = Long.MIN_VALUE;
        for (JsonNode event : events) {
            if (event.path("exchange_timestamp_ns").longValue() != 34_200_000_000_003L) {
                continue;
            }
            if ("historical".equals(event.path("source").textValue())) {
                lastHistoricalAtTrigger = Math.max(lastHistoricalAtTrigger, event.path("sequence").longValue());
            } else if (event.hasNonNull("scenario_id")) {
                firstSyntheticAtTrigger = Math.min(firstSyntheticAtTrigger, event.path("sequence").longValue());
            }
        }
        assertThat(lastHistoricalAtTrigger).isPositive();
        assertThat(firstSyntheticAtTrigger).isLessThan(Long.MAX_VALUE);
        assertThat(lastHistoricalAtTrigger).isLessThan(firstSyntheticAtTrigger);
        assertThat(events)
                .filteredOn(event -> event.hasNonNull("scenario_id"))
                .allMatch(event -> "simulation".equals(event.path("source").textValue()));
    }

    @Test
    void scheduledInjectionRejectsMissingSourceRowsAndConflictingTriggers(@TempDir Path root)
            throws Exception {
        Path registry = createLobsterDataset(root.resolve("scheduled-invalid"));
        LiveArenaService arena = lobsterArena(root.resolve("output"), registry, 2);

        assertThatThrownBy(() -> arena.runReplayComparison(
                        "lobster-spy-fixture", "layering_like", 20, 7, 999L, null, Map.of()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("trigger was not reached");
        assertThatThrownBy(() -> arena.runReplayComparison(
                        "lobster-spy-fixture", "layering_like", 20, 7,
                        3L, 34_200_000_000_003L, Map.of()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("mutually exclusive");
    }

    @Test
    void hybridAttackAtInjectionTimeCannotObserveFutureLobsterRows(@TempDir Path root)
            throws Exception {
        Path firstRegistry = createLobsterDataset(root.resolve("first"), 0);
        Path changedFutureRegistry = createLobsterDataset(root.resolve("changed-future"), 50_000);
        LiveArenaService first = lobsterArena(root.resolve("first-output"), firstRegistry, 1);
        LiveArenaService changedFuture =
                lobsterArena(root.resolve("changed-output"), changedFutureRegistry, 1);

        first.loadDataSource("hybrid", "lobster-spy-fixture", 17);
        changedFuture.loadDataSource("hybrid", "lobster-spy-fixture", 17);
        first.launchScenario("spoofing_like_wall");
        changedFuture.launchScenario("spoofing_like_wall");

        JsonNode firstStep = first.stepForTest();
        JsonNode changedFutureStep = changedFuture.stepForTest();
        List<JsonNode> firstSynthetic = new ArrayList<>();
        List<JsonNode> changedSynthetic = new ArrayList<>();
        firstStep.path("exchange_events").forEach(event -> {
            if (event.hasNonNull("scenario_id")) firstSynthetic.add(event);
        });
        changedFutureStep.path("exchange_events").forEach(event -> {
            if (event.hasNonNull("scenario_id")) changedSynthetic.add(event);
        });

        assertThat(firstSynthetic).isNotEmpty();
        assertThat(changedSynthetic).isEqualTo(firstSynthetic);
        assertThat(firstStep.path("market_data").path("source_sequence").longValue()).isEqualTo(1);
        assertThat(changedFutureStep.path("market_data").path("source_sequence").longValue())
                .isEqualTo(1);
    }

    private LiveArenaService arena(Path output, JsonNode runnerResponse) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> {
            JsonNode response = runnerResponse.deepCopy();
            if (response.path("intents").isArray()) {
                response.path("intents").forEach(intent -> ((ObjectNode) intent)
                        .put("tick", snapshot.path("tick").longValue()));
            }
            return CompletableFuture.completedFuture(response);
        };
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(URI.create("http://runner:9100/")), client);
        return new LiveArenaService(mapper, orchestrator, new ArenaJournal(output, mapper));
    }

    private LiveArenaService historicalArena(Path output, int rowsPerTick) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(), client);
        return new LiveArenaService(
                mapper,
                orchestrator,
                new ArenaJournal(output, mapper),
                output.resolve("unused-parquet"),
                HistoricalCsvMarketDataSourceTest.fixtureRoot(),
                rowsPerTick);
    }

    private LiveArenaService lobsterArena(Path output, Path registry, int rowsPerTick) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(), client);
        return new LiveArenaService(
                mapper,
                orchestrator,
                new ArenaJournal(output, mapper),
                registry,
                output.resolve("unused-canonical"),
                rowsPerTick,
                42);
    }

    private static Path createLobsterDataset(Path registry) throws Exception {
        return createLobsterDataset(registry, 0);
    }

    private static Path createLobsterDataset(Path registry, long futureBidQuantityDelta)
            throws Exception {
        String datasetId = "lobster-spy-fixture";
        Path dataset = Files.createDirectories(registry.resolve(datasetId));
        Path events = dataset.resolve("events.parquet");
        Path books = dataset.resolve("book_snapshots.parquet");
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:");
                Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE events AS
                    SELECT i::BIGINT source_sequence,
                           (34200000000000 + CASE WHEN i = 4 THEN 3 ELSE i END)::BIGINT
                               timestamp_ns_since_midnight,
                           'ADD'::VARCHAR event_kind, 1::TINYINT source_event_code,
                           (1000 + i)::BIGINT source_order_id, 10::BIGINT size,
                           1000000::BIGINT price_x10000, 1::TINYINT direction,
                           'BUY'::VARCHAR book_side, NULL::VARCHAR aggressor_side,
                           NULL::VARCHAR halt_state
                    FROM range(1, 9) values(i)
                    """);
            statement.execute("COPY events TO '" + sqlPath(events) + "' (FORMAT PARQUET)");
            statement.execute("""
                    CREATE TABLE books AS
                    SELECT i::BIGINT source_sequence,
                           (34200000000000 + CASE WHEN i = 4 THEN 3 ELSE i END)::BIGINT
                               timestamp_ns_since_midnight,
                           2::SMALLINT depth,
                           [{'level': 1::SMALLINT, 'price_x10000': 1001000::BIGINT, 'quantity': 200::BIGINT},
                            {'level': 2::SMALLINT, 'price_x10000': 1002000::BIGINT, 'quantity': 300::BIGINT}] asks,
                           [{'level': 1::SMALLINT, 'price_x10000': 1000000::BIGINT,
                             'quantity': (100 + i + CASE WHEN i > 1 THEN %d ELSE 0 END)::BIGINT},
                            {'level': 2::SMALLINT, 'price_x10000': 999000::BIGINT, 'quantity': 400::BIGINT}] bids
                    FROM range(1, 9) values(i)
                    """.formatted(futureBidQuantityDelta));
            statement.execute("COPY books TO '" + sqlPath(books) + "' (FORMAT PARQUET)");
        }
        Files.writeString(dataset.resolve("manifest.json"), """
                {
                  "dataset_id": "%s",
                  "status": "ready",
                  "source_type": "lobster",
                  "symbol": "SPY",
                  "trade_date": "2012-06-21",
                  "start_time_ms": 34200000,
                  "end_time_ms": 34260000,
                  "depth": 2,
                  "row_count": 8,
                  "source_files": [
                    {"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
                    {"sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
                  ],
                  "output_files": [
                    {"name": "events.parquet", "size_bytes": %d, "sha256": "%s"},
                    {"name": "book_snapshots.parquet", "size_bytes": %d, "sha256": "%s"}
                  ]
                }
                """.formatted(
                datasetId,
                Files.size(events),
                sha256(events),
                Files.size(books),
                sha256(books)));
        return registry;
    }

    private static String sqlPath(Path path) {
        return path.toAbsolutePath().normalize().toString().replace("'", "''");
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }
}
