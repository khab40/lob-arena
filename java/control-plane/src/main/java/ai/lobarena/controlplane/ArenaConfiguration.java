package ai.lobarena.controlplane;

import io.micrometer.core.instrument.MeterRegistry;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
class ArenaConfiguration {
    @Bean
    ArenaJournal arenaJournal(
            ObjectMapper mapper,
            @Value("${lob.arena.output-dir:../outputs}") String outputDir) {
        return new ArenaJournal(normalizePath(outputDir), mapper);
    }

    @Bean
    ArenaEventMetrics arenaEventMetrics(MeterRegistry registry, LiveArenaService arena) {
        return new ArenaEventMetrics(registry, arena);
    }

    @Bean
    LiveArenaService liveArenaService(
            ObjectMapper mapper,
            AgentOrchestrator orchestrator,
            ArenaJournal journal,
            @Value("${lob.arena.historical-data-dir:../../data/processed/lobster}") String historicalDataDir,
            @Value("${lob.arena.historical-csv-data-dir:../../data/historical}") String historicalCsvDataDir,
            @Value("${lob.arena.market-profiles-dir:../../configs/market-profiles}") String marketProfilesDir,
            @Value("${lob.arena.historical-rows-per-tick:250}") int historicalRowsPerTick,
            @Value("${lob.arena.master-seed:42}") long masterSeed,
            @Value("${lob.arena.event-history-capacity:50000}") int eventHistoryCapacity,
            @Value("${lob.arena.event-archive-segment-events:25000}") int archiveSegmentEvents,
            @Value("${lob.arena.event-archive-max-stream-bytes:21474836480}") long archiveMaxStreamBytes,
            @Value("${lob.arena.duckdb.memory-limit:1GB}") String duckDbMemoryLimit,
            @Value("${lob.arena.duckdb.threads:2}") int duckDbThreads,
            @Value("${lob.arena.duckdb.temp-directory:/tmp/lob-arena-duckdb}") String duckDbTempDirectory,
            @Value("${lob.arena.duckdb.max-temp-directory-size:8GB}") String duckDbMaxTempDirectorySize) {
        return new LiveArenaService(
                mapper,
                orchestrator,
                journal,
                normalizePath(historicalDataDir),
                normalizePath(historicalCsvDataDir),
                historicalRowsPerTick,
                masterSeed,
                eventHistoryCapacity,
                archiveSegmentEvents,
                archiveMaxStreamBytes,
                new DuckDbResourceLimits(
                        duckDbMemoryLimit,
                        duckDbThreads,
                        normalizePath(duckDbTempDirectory),
                        duckDbMaxTempDirectorySize),
                normalizePath(marketProfilesDir));
    }

    static Path normalizePath(String value) {
        return Path.of(value).toAbsolutePath().normalize();
    }
}
