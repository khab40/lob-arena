package ai.lobarena.controlplane;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;

@RestController
final class ArenaController {
    private final LiveArenaService arena;

    ArenaController(LiveArenaService arena) {
        this.arena = arena;
    }

    @GetMapping("/api/arena/state")
    JsonNode state() {
        return arena.state();
    }

    @GetMapping("/api/arena/metrics-state")
    JsonNode metricsState() {
        return arena.metricsState();
    }

    @GetMapping("/api/arena/runtime-limits")
    JsonNode runtimeLimits() {
        return arena.runtimeLimits();
    }

    @GetMapping("/api/arena/exchange-events")
    JsonNode exchangeEvents(
            @RequestParam(defaultValue = "0") long afterSequence,
            @RequestParam(defaultValue = "100") int limit,
            @RequestParam(required = false) String streamId) {
        if (afterSequence < 0 || limit < 1 || limit > 1000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid replay cursor or limit");
        }
        try {
            return arena.exchangeEvents(streamId, afterSequence, limit);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, exception.getMessage(), exception);
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.GONE, exception.getMessage(), exception);
        }
    }

    JsonNode exchangeEvents(long afterSequence, int limit) {
        return exchangeEvents(afterSequence, limit, null);
    }

    @DeleteMapping("/internal/arena/exchange-events/{streamId}")
    JsonNode releaseExchangeEventStream(@PathVariable String streamId) {
        try {
            return arena.releaseExchangeEventStream(streamId);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, exception.getMessage(), exception);
        } catch (IllegalStateException exception) {
            throw new ResponseStatusException(HttpStatus.GONE, exception.getMessage(), exception);
        }
    }

    @PostMapping("/api/simulation/start")
    JsonNode start() {
        try {
            return arena.start();
        } catch (CanonicalEventArchive.ArchiveCapacityExceededException exception) {
            throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_ENTITY, exception.getMessage(), exception);
        }
    }

    @PostMapping("/api/simulation/pause")
    JsonNode pause() {
        return arena.pause();
    }

    @PostMapping("/api/simulation/reset")
    JsonNode reset() {
        return arena.reset();
    }

    @PostMapping("/api/arena/data-source")
    JsonNode loadDataSource(@RequestBody Map<String, Object> body) {
        try {
            return arena.loadDataSource(
                    String.valueOf(body.getOrDefault("source_type", "")),
                    String.valueOf(body.getOrDefault("dataset_id", "")),
                    longValue(body.get("master_seed"), arena.defaultMasterSeed()));
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, exception.getMessage(), exception);
        }
    }

    @GetMapping("/api/arena/historical-datasets")
    JsonNode historicalDatasets() {
        return arena.historicalCsvDatasets();
    }

    @GetMapping("/api/arena/market-profiles")
    JsonNode marketProfiles() {
        return arena.marketProfileSummaries();
    }

    @PostMapping("/api/arena/replay-comparison")
    JsonNode replayComparison(@RequestBody Map<String, Object> body) {
        try {
            return arena.runReplayComparison(
                    String.valueOf(body.getOrDefault("dataset_id", "")),
                    String.valueOf(body.getOrDefault("scenario_family", "")),
                    integerValue(body.get("max_ticks"), 10_000),
                    longValue(body.get("master_seed"), arena.defaultMasterSeed()),
                    nullableLongValue(body.get("trigger_source_sequence"), "trigger_source_sequence"),
                    nullableLongValue(body.get("trigger_timestamp_ns"), "trigger_timestamp_ns"),
                    stringObjectMap(body.get("scenario_parameters")));
        } catch (CanonicalEventArchive.ArchiveCapacityExceededException exception) {
            throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_ENTITY, exception.getMessage(), exception);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_ENTITY, exception.getMessage(), exception);
        }
    }

    @PostMapping("/internal/arena/step")
    JsonNode internalStep() {
        return arena.stepForTest();
    }

    @PostMapping("/api/scenarios/{scenario}")
    JsonNode launchScenario(@PathVariable String scenario) {
        try {
            return arena.launchScenario(scenario);
        } catch (CanonicalEventArchive.ArchiveCapacityExceededException exception) {
            throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_ENTITY, exception.getMessage(), exception);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, exception.getMessage(), exception);
        }
    }

    @GetMapping("/api/incidents")
    JsonNode incidents() {
        return arena.incidents();
    }

    @GetMapping("/api/incidents/{incidentId}")
    JsonNode incident(@PathVariable String incidentId) {
        JsonNode incident = arena.incident(incidentId);
        if (incident == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown incident: " + incidentId);
        }
        return incident;
    }

    private static int integerValue(Object value, int defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("max_ticks must be an integer", exception);
        }
    }

    private static long longValue(Object value, long defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof Number number) {
            return number.longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("master_seed must be an integer", exception);
        }
    }

    private static Long nullableLongValue(Object value, String field) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.longValue();
        }
        try {
            return Long.parseLong(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(field + " must be an integer", exception);
        }
    }

    private static Map<String, Object> stringObjectMap(Object value) {
        if (value == null) {
            return Map.of();
        }
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalArgumentException("scenario_parameters must be an object");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        raw.forEach((key, item) -> {
            if (!(key instanceof String field)) {
                throw new IllegalArgumentException("scenario parameter names must be strings");
            }
            result.put(field, item);
        });
        return Map.copyOf(result);
    }
}
