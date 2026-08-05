package ai.lobarena.controlplane;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Comparator;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

final class MarketProfileRegistry {
    private static final Pattern PROFILE_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern SIMULATION_TOKEN = Pattern.compile("[A-Za-z0-9._-]+");

    private final ObjectMapper mapper;
    private final Path root;

    MarketProfileRegistry(ObjectMapper mapper, Path root) {
        this.mapper = mapper;
        this.root = root.toAbsolutePath().normalize();
    }

    MarketProfile load(String profileId) {
        if (profileId == null || !PROFILE_ID.matcher(profileId).matches()) {
            throw new IllegalArgumentException("invalid market profile id");
        }
        Path path = root.resolve(profileId + ".json").normalize();
        if (!path.getParent().equals(root) || !Files.isRegularFile(path)) {
            throw new IllegalArgumentException("unknown market profile: " + profileId);
        }
        try {
            JsonNode document = mapper.readTree(Files.readString(path));
            if (!document.isObject()) {
                throw new IllegalArgumentException("market profile must be a JSON object");
            }
            return parse(profileId, document);
        } catch (IOException exception) {
            throw new IllegalArgumentException("cannot read market profile: " + profileId, exception);
        }
    }

    ArrayNode summaries() {
        ArrayNode result = mapper.createArrayNode();
        if (!Files.isDirectory(root)) {
            return result;
        }
        try (Stream<Path> paths = Files.list(root)) {
            paths.filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .map(path -> path.getFileName().toString())
                    .map(name -> name.substring(0, name.length() - 5))
                    .map(this::load)
                    .map(MarketProfile::summary)
                    .forEach(result::add);
        } catch (IOException exception) {
            throw new IllegalStateException("cannot list market profiles", exception);
        }
        return result;
    }

    private MarketProfile parse(String requestedId, JsonNode document) {
        if (!"market_profile_v1".equals(document.path("schema_version").asText())) {
            throw new IllegalArgumentException("unsupported market profile schema");
        }
        if (!requestedId.equals(document.path("profile_id").asText())) {
            throw new IllegalArgumentException("market profile id does not match its filename");
        }
        String sha = document.path("profile_sha256").asText();
        if (!SHA256.matcher(sha).matches()) {
            throw new IllegalArgumentException("market profile SHA-256 is invalid");
        }
        if (!sha.equals(canonicalSha256(document))) {
            throw new IllegalArgumentException("market profile SHA-256 does not match canonical content");
        }
        JsonNode parameters = document.path("simulation_parameters");
        if (!parameters.isObject()) {
            throw new IllegalArgumentException("market profile simulation_parameters must be an object");
        }
        String symbol = requiredText(parameters, "symbol", 1, 16);
        String venue = requiredText(parameters, "venue", 1, 32);
        MarketProfile profile = new MarketProfile(
                requestedId,
                sha,
                symbol,
                venue,
                requiredLong(parameters, "reference_price_ticks", 1, 1_000_000_000_000L),
                Math.toIntExact(requiredLong(parameters, "baseline_levels", 1, 100)),
                requiredLong(parameters, "level_spacing_ticks", 1, 1_000_000_000L),
                requiredLong(parameters, "base_quantity_lots", 1, 1_000_000_000_000L),
                requiredLong(parameters, "depth_increment_lots", 0, 1_000_000_000_000L),
                requiredLong(parameters, "reference_update_interval_ticks", 1, 1_000_000L),
                requiredLong(parameters, "reference_max_step_ticks", 0, 1_000_000_000L),
                document.deepCopy(),
                mapper);
        if (profile.referenceMaxStepTicks() > profile.levelSpacingTicks()) {
            throw new IllegalArgumentException(
                    "market profile reference_max_step_ticks must not exceed level_spacing_ticks");
        }
        return profile;
    }

    private static long requiredLong(JsonNode parameters, String field, long minimum, long maximum) {
        JsonNode value = parameters.path(field);
        if (!value.isIntegralNumber()) {
            throw new IllegalArgumentException("market profile parameter " + field + " must be an integer");
        }
        long number = value.longValue();
        if (number < minimum || number > maximum) {
            throw new IllegalArgumentException(
                    "market profile parameter " + field + " must be between " + minimum + " and " + maximum);
        }
        return number;
    }

    private static String requiredText(JsonNode parameters, String field, int minimum, int maximum) {
        String value = parameters.path(field).asText("").strip();
        if (value.length() < minimum
                || value.length() > maximum
                || !SIMULATION_TOKEN.matcher(value).matches()) {
            throw new IllegalArgumentException("market profile parameter " + field + " has an invalid length");
        }
        return value;
    }

    private static String canonicalSha256(JsonNode document) {
        ObjectNode content = (ObjectNode) document.deepCopy();
        content.remove("profile_sha256");
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(canonicalJson(content).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
    }

    private static String canonicalJson(JsonNode node) {
        if (node.isObject()) {
            List<Map.Entry<String, JsonNode>> fields = new ArrayList<>();
            fields.addAll(((ObjectNode) node).properties());
            fields.sort(Map.Entry.comparingByKey());
            return fields.stream()
                    .map(field -> jsonString(field.getKey()) + ":" + canonicalJson(field.getValue()))
                    .reduce((left, right) -> left + "," + right)
                    .map(value -> "{" + value + "}")
                    .orElse("{}");
        }
        if (node.isArray()) {
            List<String> values = new ArrayList<>();
            node.forEach(value -> values.add(canonicalJson(value)));
            return "[" + String.join(",", values) + "]";
        }
        return node.toString();
    }

    private static String jsonString(String value) {
        return tools.jackson.databind.node.JsonNodeFactory.instance.stringNode(value).toString();
    }

    record MarketProfile(
            String id,
            String sha256,
            String symbol,
            String venue,
            long referencePriceTicks,
            int baselineLevels,
            long levelSpacingTicks,
            long baseQuantityLots,
            long depthIncrementLots,
            long referenceUpdateIntervalTicks,
            long referenceMaxStepTicks,
            JsonNode document,
            ObjectMapper mapper) {
        ObjectNode summary() {
            ObjectNode result = mapper.createObjectNode()
                    .put("profile_id", id)
                    .put("schema_version", "market_profile_v1")
                    .put("profile_sha256", sha256)
                    .put("symbol", symbol)
                    .put("venue", venue);
            JsonNode source = document.path("source");
            result.put("dataset_id", id);
            result.put("training_dataset_id", source.path("dataset_id").asText());
            result.put("trade_date", source.path("trade_date").asText());
            result.set("simulation_parameters", document.path("simulation_parameters").deepCopy());
            return result;
        }

        ObjectNode runtimeContext(long masterSeed, long currentReferencePriceTicks, String runBindingSha256) {
            ObjectNode result = summary();
            result.put("source_type", "synthetic_profile");
            result.put("master_seed", masterSeed);
            result.put("current_reference_price_ticks", currentReferencePriceTicks);
            result.put("run_binding_sha256", runBindingSha256);
            return result;
        }
    }
}
