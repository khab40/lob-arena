package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class AgentOrchestratorTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void mergesValidRunnerResponsesAndSortsIntentsDeterministically() {
        URI first = URI.create("http://runner-a:9100/");
        URI second = URI.create("http://runner-b:9100/");
        Map<URI, JsonNode> responses = Map.of(
                first, mapper.readTree("""
                        {"agent_ids":["B"],"intents":[
                          {"tick":7,"agent_id":"B","kind":"market","sequence":1,"latency_bucket":2,"side":"buy","quantity":1.0}
                        ]}
                        """),
                second, mapper.readTree("""
                        {"agent_ids":["A"],"intents":[
                          {"tick":7,"agent_id":"A","kind":"set_level","side":"bid","price":99.0,"quantity":2.0},
                          {"tick":6,"agent_id":"STALE","kind":"market","side":"sell","quantity":1.0}
                        ]}
                        """));
        AgentRunnerClient client = (runner, snapshot) -> CompletableFuture.completedFuture(responses.get(runner));
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(first, second), client);

        Map<String, Object> result = orchestrator.collect(mapper.readTree("{\"tick\":7}"));

        assertThat(result.get("agent_ids")).isEqualTo(List.of("B", "A"));
        @SuppressWarnings("unchecked")
        List<JsonNode> intents = (List<JsonNode>) result.get("intents");
        assertThat(intents).extracting(node -> node.path("agent_id").stringValue()).containsExactly("A", "B");
        assertThat(intents).allSatisfy(node -> assertThat(node.path("runtime_source").stringValue())
                .isEqualTo("agent_runner"));
    }

    @Test
    void isolatesFailedRunnerAndRejectsMalformedIntents() {
        URI failed = URI.create("http://failed:9100/");
        URI valid = URI.create("http://valid:9100/");
        AgentRunnerClient client = (runner, snapshot) -> {
            if (runner.equals(failed)) {
                return CompletableFuture.failedFuture(new IllegalStateException("timeout"));
            }
            return CompletableFuture.completedFuture(mapper.readTree("""
                    {"agent_ids":["VALID"],"intents":[
                      {"tick":3,"agent_id":"VALID","kind":"set_level","side":"ask","price":101.0,"quantity":1.0},
                      {"tick":3,"agent_id":"BAD","kind":"unknown","quantity":1.0},
                      {"tick":3,"agent_id":"NEGATIVE","kind":"market","side":"buy","quantity":-1.0}
                    ]}
                    """));
        };
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(failed, valid), client);

        Map<String, Object> result = orchestrator.collect(mapper.readTree("{\"tick\":3}"));

        @SuppressWarnings("unchecked")
        List<JsonNode> intents = (List<JsonNode>) result.get("intents");
        assertThat(intents).hasSize(1);
        assertThat(intents.getFirst().path("agent_id").stringValue()).isEqualTo("VALID");
    }
}
