package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ai.lobarena.kernel.determinism.DeterministicValues;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class MarketProfileRuntimeTest {
    private static final String PROFILE_SHA = "476a8403a61f80fc8b0a0171833cee70b5e25964feeaf0a1048e0222625fe9f7";
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void profileSelectionBindsTheRunAndDrivesSeededDynamicBaseline(@TempDir Path root)
            throws Exception {
        Path profiles = Files.createDirectories(root.resolve("profiles"));
        writeProfile(profiles, "fixture-profile");
        AtomicReference<JsonNode> agentObservation = new AtomicReference<>();
        LiveArenaService arena = arena(root.resolve("output"), profiles, agentObservation);

        JsonNode loaded = arena.loadDataSource("synthetic_profile", "fixture-profile", 99);

        assertThat(arena.marketProfileSummaries()).hasSize(1);
        assertThat(loaded.path("market_data").path("source_type").textValue())
                .isEqualTo("synthetic_profile");
        assertThat(loaded.path("market_data").path("profile_sha256").textValue())
                .isEqualTo(PROFILE_SHA);
        assertThat(loaded.path("market_data").path("run_binding_sha256").textValue())
                .matches("[0-9a-f]{64}");
        assertThat(loaded.path("book").path("best_bid").doubleValue()).isEqualTo(99.995);
        assertThat(loaded.path("book").path("bids").get(0).path("quantity").doubleValue())
                .isEqualTo(100.0);

        arena.start();
        JsonNode advanced = arena.stepForTest();
        assertThat(agentObservation.get().path("market_profile").path("profile_sha256").textValue())
                .isEqualTo(PROFILE_SHA);
        assertThat(agentObservation.get()
                        .path("market_profile")
                        .path("simulation_parameters")
                        .path("reference_price_ticks")
                        .longValue())
                .isEqualTo(100_000);
        long direction = Math.floorMod(
                        DeterministicValues.deriveStreamSeed(
                                99, "market-profile-reference:" + PROFILE_SHA + ":1"),
                        3)
                - 1;
        assertThat(advanced.path("market_data").path("current_reference_price_ticks").longValue())
                .isEqualTo(100_000 + direction * 2);

        arena.reset();
        arena.start();
        JsonNode repeated = arena.stepForTest();
        assertThat(repeated.path("book")).isEqualTo(advanced.path("book"));
        assertThat(repeated.path("market_data").path("run_binding_sha256"))
                .isEqualTo(advanced.path("market_data").path("run_binding_sha256"));

        JsonNode hardcoded = arena.loadDataSource("synthetic", "", 99);
        assertThat(hardcoded.has("market_data")).isFalse();
        assertThat(hardcoded.path("book").path("best_bid").doubleValue()).isEqualTo(68_124.0);
    }

    @Test
    void rejectsUnknownAndInvalidProfiles(@TempDir Path root) throws Exception {
        Path profiles = Files.createDirectories(root.resolve("profiles"));
        writeProfile(profiles, "fixture-profile");
        Files.writeString(
                profiles.resolve("invalid-profile.json"),
                "{\"schema_version\":\"market_profile_v1\",\"profile_id\":\"invalid-profile\"}");
        LiveArenaService arena = arena(root.resolve("output"), profiles);

        assertThatThrownBy(() -> arena.loadDataSource("synthetic_profile", "missing"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unknown market profile");
        assertThatThrownBy(() -> arena.loadDataSource("synthetic_profile", "invalid-profile"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("SHA-256");
    }

    @Test
    void committedFixtureProfileHasAJavaVerifiableCanonicalChecksum() {
        Path working = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        Path profiles = List.of(
                        working.resolve("configs/market-profiles"),
                        working.resolve("../configs/market-profiles"),
                        working.resolve("../../configs/market-profiles"))
                .stream()
                .map(Path::normalize)
                .filter(path -> Files.isRegularFile(path.resolve("fixture-aapl-itch-v1.json")))
                .findFirst()
                .orElseThrow();

        MarketProfileRegistry.MarketProfile profile =
                new MarketProfileRegistry(mapper, profiles).load("fixture-aapl-itch-v1");

        assertThat(profile.sha256())
                .isEqualTo("3f4666a5cf985b754ddab7894d09f8960123e02b93d81e715efe71b0cd993ad8");
        assertThat(profile.symbol()).isEqualTo("AAPL");
    }

    private LiveArenaService arena(Path output, Path profiles) {
        return arena(output, profiles, new AtomicReference<>());
    }

    private LiveArenaService arena(
            Path output, Path profiles, AtomicReference<JsonNode> agentObservation) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> {
            agentObservation.set(snapshot.deepCopy());
            return CompletableFuture.completedFuture(
                    mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        };
        AgentOrchestrator orchestrator =
                new AgentOrchestrator(List.of(URI.create("http://profile-agent.test")), client);
        return new LiveArenaService(
                mapper,
                orchestrator,
                new ArenaJournal(output, mapper),
                output.resolve("historical"),
                output.resolve("canonical"),
                10,
                42,
                50_000,
                25_000,
                20L * 1024 * 1024 * 1024,
                DuckDbResourceLimits.defaults(),
                profiles);
    }

    private static void writeProfile(Path profiles, String profileId) throws Exception {
        Files.writeString(
                profiles.resolve(profileId + ".json"),
                """
                {
                  "schema_version": "market_profile_v1",
                  "profile_id": "%s",
                  "profile_sha256": "%s",
                  "source": {
                    "dataset_id": "itch-training-window",
                    "trade_date": "2026-01-02"
                  },
                  "simulation_parameters": {
                    "symbol": "TEST",
                    "venue": "SIM",
                    "reference_price_ticks": 100000,
                    "baseline_levels": 2,
                    "level_spacing_ticks": 5,
                    "base_quantity_lots": 100000,
                    "depth_increment_lots": 50000,
                    "reference_update_interval_ticks": 1,
                    "reference_max_step_ticks": 2
                  }
                }
                """.formatted(profileId, PROFILE_SHA));
    }
}
