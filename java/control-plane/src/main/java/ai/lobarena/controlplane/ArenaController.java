package ai.lobarena.controlplane;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import java.util.Map;

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

    @GetMapping("/api/arena/exchange-events")
    JsonNode exchangeEvents(
            @RequestParam(defaultValue = "0") long afterSequence,
            @RequestParam(defaultValue = "100") int limit) {
        if (afterSequence < 0 || limit < 1 || limit > 1000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid replay cursor or limit");
        }
        return arena.exchangeEvents(afterSequence, limit);
    }

    @PostMapping("/api/simulation/start")
    JsonNode start() {
        return arena.start();
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

    @PostMapping("/api/arena/replay-comparison")
    JsonNode replayComparison(@RequestBody Map<String, Object> body) {
        try {
            return arena.runReplayComparison(
                    String.valueOf(body.getOrDefault("dataset_id", "")),
                    String.valueOf(body.getOrDefault("scenario_family", "")),
                    integerValue(body.get("max_ticks"), 10_000),
                    longValue(body.get("master_seed"), arena.defaultMasterSeed()));
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
}
