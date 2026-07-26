package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ArenaControllerTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void exposesArenaLifecycleScenarioIncidentAndReplayContracts(@TempDir Path output) {
        ArenaController controller = new ArenaController(arena(output));

        assertThat(controller.state().path("running").booleanValue()).isFalse();
        assertThat(controller.start().path("running").booleanValue()).isTrue();
        assertThat(controller.launchScenario("spoofing-like").path("scenario_family").textValue())
                .isEqualTo("spoofing_like_wall");
        controller.internalStep();
        controller.internalStep();
        controller.internalStep();

        JsonNode incidents = controller.incidents();
        assertThat(incidents).hasSize(1);
        String incidentId = incidents.get(0).path("id").textValue();
        assertThat(controller.incident(incidentId).path("scenario_family").textValue())
                .isEqualTo("spoofing_like_wall");
        assertThat(controller.exchangeEvents(0, 10).path("events")).isNotEmpty();
        assertThat(controller.metricsState().path("tick").longValue()).isEqualTo(3);
        assertThat(controller.metricsState().path("incidents_count").longValue()).isEqualTo(1);
        assertThat(controller.pause().path("running").booleanValue()).isFalse();
        assertThat(controller.reset().path("tick").longValue()).isZero();
    }

    @Test
    void rejectsUnknownScenarioAndInvalidReplayBounds(@TempDir Path output) {
        ArenaController controller = new ArenaController(arena(output));

        assertThatThrownBy(() -> controller.launchScenario("unknown"))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        exception -> assertThat(exception.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> controller.exchangeEvents(-1, 0))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        exception -> assertThat(exception.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
    }

    @Test
    void readsMetricsStateWithoutWaitingForTheArenaMonitor(@TempDir Path output) throws Exception {
        LiveArenaService arena = arena(output);
        CountDownLatch monitorHeld = new CountDownLatch(1);
        CountDownLatch releaseMonitor = new CountDownLatch(1);
        Thread holder = Thread.ofPlatform().start(() -> {
            synchronized (arena) {
                monitorHeld.countDown();
                try {
                    releaseMonitor.await();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            }
        });
        try {
            assertThat(monitorHeld.await(1, TimeUnit.SECONDS)).isTrue();
            org.junit.jupiter.api.Assertions.assertTimeoutPreemptively(
                    Duration.ofSeconds(1), arena::metricsState);
        } finally {
            releaseMonitor.countDown();
            holder.join(1_000);
        }
        assertThat(holder.isAlive()).isFalse();
    }

    private LiveArenaService arena(Path output) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(), client);
        return new LiveArenaService(mapper, orchestrator, new ArenaJournal(output, mapper));
    }
}
