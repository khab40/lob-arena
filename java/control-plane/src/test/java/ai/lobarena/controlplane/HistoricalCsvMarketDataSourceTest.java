package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class HistoricalCsvMarketDataSourceTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final Path fixtures = fixtureRoot();

    @Test
    void parsesAndBatchesCanonicalCsvDeterministically() {
        HistoricalCsvMarketDataSource source =
                new HistoricalCsvMarketDataSource(mapper, fixtures, 5);

        JsonNode context = source.load("sample-btcusdt-0945");
        var first = source.nextBatch();
        var second = source.nextBatch();

        assertThat(context.path("format").stringValue()).isEqualTo("canonical_csv_v1");
        assertThat(first).hasSize(5);
        assertThat(first).extracting(record -> record.sourceSequence())
                .containsExactly(1L, 2L, 3L, 4L, 5L);
        assertThat(second.getFirst().sourceSequence()).isEqualTo(6);
        assertThatThrownBy(() -> first.set(0, first.getFirst()))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void advertisesOnlyValidatedDatasetsAndRejectsTraversal() {
        HistoricalCsvMarketDataSource source =
                new HistoricalCsvMarketDataSource(mapper, fixtures, 5);

        assertThat(source.datasets()).hasSize(1);
        assertThat(source.datasets().get(0).path("dataset_id").stringValue())
                .isEqualTo("sample-btcusdt-0945");
        assertThat(source.supports("../sample-btcusdt-0945")).isFalse();
        assertThatThrownBy(() -> source.load("../sample-btcusdt-0945"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsInvalidOrderLifecycleEvenWhenChecksumIsValid(@TempDir Path registry) throws Exception {
        Path dataset = Files.createDirectories(registry.resolve("invalid-lifecycle"));
        String csv = """
                source_sequence,timestamp_ns,event_type,order_id,participant_id,side,price_ticks,quantity_lots
                1,35100000000000,ADD,bid-001,participant-001,BUY,68124000,5000
                2,35100001000000,CANCEL,bid-001,participant-001,BUY,,1
                """;
        Files.writeString(dataset.resolve("events.csv"), csv, StandardCharsets.UTF_8);
        String checksum = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(csv.getBytes(StandardCharsets.UTF_8)));
        Files.writeString(dataset.resolve("manifest.json"), """
                {
                  "dataset_id": "invalid-lifecycle",
                  "status": "ready",
                  "format": "canonical_csv_v1",
                  "symbol": "BTCUSDT",
                  "venue": "TEST",
                  "trade_date": "2026-07-23",
                  "price_tick_size_nanos": 1000000,
                  "quantity_lot_size_nanos": 1000000,
                  "row_count": 2,
                  "events_sha256": "%s"
                }
                """.formatted(checksum), StandardCharsets.UTF_8);
        HistoricalCsvMarketDataSource source =
                new HistoricalCsvMarketDataSource(mapper, registry, 5);

        assertThatThrownBy(() -> source.load("invalid-lifecycle"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("CANCEL price_ticks must be empty");
    }

    static Path fixtureRoot() {
        return Stream.of(
                        Path.of("data/historical"),
                        Path.of("../data/historical"),
                        Path.of("../../data/historical"))
                .map(path -> path.toAbsolutePath().normalize())
                .filter(Files::isDirectory)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("historical fixture directory not found"));
    }
}
