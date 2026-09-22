package ai.lobarena.controlplane;

import java.net.URI;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

final class AgentOrchestrator {
    private static final Set<String> KINDS = Set.of("set_level", "market", "limit", "cancel");
    private static final Comparator<JsonNode> INTENT_ORDER = Comparator
            .comparingLong((JsonNode node) -> longValue(node, "tick"))
            .thenComparingLong(node -> longValue(node, "latency_bucket"))
            .thenComparing(node -> textValue(node, "agent_id"))
            .thenComparingLong(node -> longValue(node, "sequence"))
            .thenComparing(node -> textValue(node, "kind"));

    private final List<URI> runners;
    private final AgentRunnerClient client;

    AgentOrchestrator(List<URI> runners, AgentRunnerClient client) {
        this.runners = List.copyOf(runners);
        this.client = client;
    }

    Map<String, Object> collect(JsonNode snapshot) {
        if (snapshot == null || !snapshot.isObject() || !snapshot.path("tick").isIntegralNumber()) {
            throw new IllegalArgumentException("snapshot with an integer tick is required");
        }
        long tick = snapshot.path("tick").longValue();
        List<CompletableFuture<JsonNode>> calls = runners.stream()
                .map(runner -> client.decide(runner, snapshot).exceptionally(ignored -> null))
                .toList();
        CompletableFuture.allOf(calls.toArray(CompletableFuture[]::new)).join();

        LinkedHashSet<String> agentIds = new LinkedHashSet<>();
        List<JsonNode> intents = new ArrayList<>();
        for (CompletableFuture<JsonNode> call : calls) {
            JsonNode response = call.join();
            if (response == null || !response.isObject()) {
                continue;
            }
            JsonNode ids = response.path("agent_ids");
            if (ids.isArray()) {
                ids.forEach(id -> {
                    if (id.isString() && !id.stringValue().isBlank()) {
                        agentIds.add(id.stringValue());
                    }
                });
            }
            JsonNode responseIntents = response.path("intents");
            if (!responseIntents.isArray()) {
                continue;
            }
            responseIntents.forEach(intent -> {
                JsonNode validated = validateIntent(intent, tick);
                if (validated != null) {
                    intents.add(validated);
                    agentIds.add(validated.path("agent_id").stringValue());
                }
            });
        }
        intents.sort(INTENT_ORDER);
        return Map.of("agent_ids", List.copyOf(agentIds), "intents", List.copyOf(intents));
    }

    int runnerCount() {
        return runners.size();
    }

    private static JsonNode validateIntent(JsonNode intent, long tick) {
        if (intent == null || !intent.isObject()) {
            return null;
        }
        String agentId = textValue(intent, "agent_id");
        String kind = textValue(intent, "kind");
        JsonNode intentTick = intent.path("tick");
        if (agentId.isBlank() || !KINDS.contains(kind) || !intentTick.isIntegralNumber()
                || intentTick.longValue() != tick) {
            return null;
        }
        JsonNode quantity = intent.path("quantity");
        if (!quantity.isMissingNode() && (!quantity.isNumber() || !Double.isFinite(quantity.doubleValue())
                || quantity.doubleValue() < 0.0)) {
            return null;
        }
        ObjectNode normalized = ((ObjectNode) intent).deepCopy();
        normalized.put("runtime_source", "agent_runner");
        if (!normalized.has("sequence")) {
            normalized.put("sequence", 0);
        }
        if (!normalized.has("latency_bucket")) {
            normalized.put("latency_bucket", 0);
        }
        return normalized;
    }

    private static long longValue(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isIntegralNumber() ? value.longValue() : 0L;
    }

    private static String textValue(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isString() ? value.stringValue() : "";
    }
}
