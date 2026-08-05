package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class HistoricalMarketDataSourceTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void replaysAlignedEventsAndSnapshotsWithoutMutatingTheSimulationKernel(@TempDir Path root) throws Exception {
        String datasetId = "lobster-aapl-2012-06-21-demo";
        Path dataset = root.resolve(datasetId);
        Files.createDirectories(dataset);
        Path events = dataset.resolve("events.parquet");
        Path books = dataset.resolve("book_snapshots.parquet");
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:");
                Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE events AS
                    SELECT 91::BIGINT source_sequence, 34200000000001::BIGINT timestamp_ns_since_midnight,
                           'ADD'::VARCHAR event_kind, 1::TINYINT source_event_code, 1001::BIGINT source_order_id,
                           100::BIGINT size, 911400::BIGINT price_x10000, 1::TINYINT direction,
                           'BUY'::VARCHAR book_side, NULL::VARCHAR aggressor_side, NULL::VARCHAR halt_state
                    UNION ALL
                    SELECT 93, 34200000000002, 'PARTIAL_CANCEL', 2, 1001, 25, 911400, 1, 'BUY', NULL, NULL
                    """);
            statement.execute("COPY events TO '" + sqlPath(events) + "' (FORMAT PARQUET)");
            statement.execute("""
                    CREATE TABLE books AS
                    SELECT 91::BIGINT source_sequence, 34200000000001::BIGINT timestamp_ns_since_midnight,
                           1::SMALLINT depth,
                           [{'level': 1::SMALLINT, 'price_x10000': 911500::BIGINT, 'quantity': 200::BIGINT}] asks,
                           [{'level': 1::SMALLINT, 'price_x10000': 911400::BIGINT, 'quantity': 100::BIGINT}] bids
                    UNION ALL
                    SELECT 93, 34200000000002, 1,
                           [{'level': 1::SMALLINT, 'price_x10000': 911500::BIGINT, 'quantity': 200::BIGINT}],
                           [{'level': 1::SMALLINT, 'price_x10000': 911400::BIGINT, 'quantity': 75::BIGINT}]
                    """);
            statement.execute("COPY books TO '" + sqlPath(books) + "' (FORMAT PARQUET)");
        }
        writeManifest(dataset, datasetId, events, books, 2);

        HistoricalMarketDataSource source = new HistoricalMarketDataSource(
                mapper, root, 1, DuckDbResourceLimits.defaults(), 1);
        JsonNode loaded = source.load(datasetId);
        assertThat(source.venue()).isEqualTo("LOBSTER");
        assertThat(source.format()).isEqualTo("lobster_parquet_v1");
        assertThat(loaded.path("market_data").path("source_sequence").longValue()).isEqualTo(91);
        assertThat(loaded.path("market_data").path("replay_position").longValue()).isEqualTo(1);
        assertThat(loaded.path("market_data").path("progress").doubleValue()).isEqualTo(0.5);
        assertThat(loaded.path("book").path("best_bid").doubleValue()).isEqualTo(91.14);
        assertThat(loaded.path("historical_events").get(0).path("price_x10000").longValue()).isEqualTo(911400);
        assertThat(source.resourcesOpen()).isTrue();

        source.start();
        source.advance();
        JsonNode advanced = source.state();
        assertThat(advanced.path("market_data").path("source_sequence").longValue()).isEqualTo(93);
        assertThat(advanced.path("market_data").path("replay_position").longValue()).isEqualTo(2);
        assertThat(advanced.path("market_data").path("progress").doubleValue()).isEqualTo(1.0);
        assertThat(advanced.path("market_data").path("eof").booleanValue()).isTrue();
        assertThat(advanced.path("running").booleanValue()).isFalse();
        assertThat(advanced.path("book").path("bids").get(0).path("quantity").longValue()).isEqualTo(75);
        assertThat(source.resourcesOpen()).isFalse();

        JsonNode reset = source.reset();
        assertThat(reset.path("market_data").path("source_sequence").longValue()).isEqualTo(91);
        assertThat(reset.path("running").booleanValue()).isFalse();
        assertThat(source.resourcesOpen()).isTrue();
        source.close();
        assertThat(source.resourcesOpen()).isFalse();

        Files.write(events, new byte[] {0}, StandardOpenOption.APPEND);
        HistoricalMarketDataSource tampered = new HistoricalMarketDataSource(mapper, root, 1);
        assertThatThrownBy(() -> tampered.load(datasetId))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("output size does not match manifest");
        assertThat(tampered.loaded()).isFalse();
    }

    @Test
    void readsSourceProvenanceFromTheManifest(@TempDir Path root) throws Exception {
        String datasetId = "itch-aapl-2026-01-02-demo";
        Path dataset = Files.createDirectories(root.resolve(datasetId));
        Path events = dataset.resolve("events.parquet");
        Path books = dataset.resolve("book_snapshots.parquet");
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:");
                Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE events AS
                    SELECT 5::BIGINT source_sequence, 34200000000004::BIGINT timestamp_ns_since_midnight,
                           'ADD'::VARCHAR event_kind, 65::TINYINT source_event_code, 1::BIGINT source_order_id,
                           100::BIGINT size, 1000000::BIGINT price_x10000, 1::TINYINT direction,
                           'BUY'::VARCHAR book_side, NULL::VARCHAR aggressor_side, NULL::VARCHAR halt_state
                    """);
            statement.execute("COPY events TO '" + sqlPath(events) + "' (FORMAT PARQUET)");
            statement.execute("""
                    CREATE TABLE books AS
                    SELECT 5::BIGINT source_sequence, 34200000000004::BIGINT timestamp_ns_since_midnight,
                           10::SMALLINT depth, [] asks,
                           [{'level': 1::SMALLINT, 'price_x10000': 1000000::BIGINT,
                             'quantity': 100::BIGINT}] bids
                    """);
            statement.execute("COPY books TO '" + sqlPath(books) + "' (FORMAT PARQUET)");
        }
        writeManifest(dataset, datasetId, events, books, 1);
        Path manifestPath = dataset.resolve("manifest.json");
        String manifest = Files.readString(manifestPath)
                .replace("\"source_type\": \"lobster\"", "\"source_type\": \"nasdaq_itch\"")
                .replace("\"symbol\": \"AAPL\"", "\"format\": \"itch_parquet_v1\",\n"
                        + "                  \"venue\": \"XNAS\",\n"
                        + "                  \"parser_version\": \"nasdaq_itch_5_0_v1\",\n"
                        + "                  \"source_stream_sha256\": \"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\",\n"
                        + "                  \"parser_config_sha256\": \"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\n"
                        + "                  \"message_counts\": {\"A\": 1},\n"
                        + "                  \"symbol\": \"AAPL\"");
        Files.writeString(manifestPath, manifest);

        HistoricalMarketDataSource source = new HistoricalMarketDataSource(mapper, root, 1);
        JsonNode loaded = source.load(datasetId);

        assertThat(source.venue()).isEqualTo("XNAS");
        assertThat(source.format()).isEqualTo("itch_parquet_v1");
        assertThat(source.historicalSourceType()).isEqualTo("nasdaq_itch");
        assertThat(loaded.path("market_data").path("historical_source_type").textValue())
                .isEqualTo("nasdaq_itch");
        assertThat(source.datasets().get(0).path("venue").textValue()).isEqualTo("XNAS");
        assertThat(source.datasets().get(0).path("format").textValue()).isEqualTo("itch_parquet_v1");
        assertThat(source.integrity().path("source_stream_sha256").textValue()).hasSize(64);
        assertThat(source.integrity().path("parser_config_sha256").textValue()).hasSize(64);
        assertThat(source.integrity().path("message_counts").path("A").intValue()).isEqualTo(1);
        source.close();
    }

    @Test
    void rejectsMessageAndBookRowsWithDifferentTimestamps(@TempDir Path root) throws Exception {
        String datasetId = "lobster-unsynchronized";
        Path dataset = Files.createDirectories(root.resolve(datasetId));
        Path events = dataset.resolve("events.parquet");
        Path books = dataset.resolve("book_snapshots.parquet");
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:");
                Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE events AS
                    SELECT 1::BIGINT source_sequence,
                           34200000000001::BIGINT timestamp_ns_since_midnight,
                           'ADD'::VARCHAR event_kind, 1::TINYINT source_event_code,
                           1001::BIGINT source_order_id, 100::BIGINT size,
                           911400::BIGINT price_x10000, 1::TINYINT direction,
                           'BUY'::VARCHAR book_side, NULL::VARCHAR aggressor_side,
                           NULL::VARCHAR halt_state
                    """);
            statement.execute("COPY events TO '" + sqlPath(events) + "' (FORMAT PARQUET)");
            statement.execute("""
                    CREATE TABLE books AS
                    SELECT 1::BIGINT source_sequence,
                           34200000000002::BIGINT timestamp_ns_since_midnight,
                           1::SMALLINT depth,
                           [{'level': 1::SMALLINT, 'price_x10000': 911500::BIGINT,
                             'quantity': 200::BIGINT}] asks,
                           [{'level': 1::SMALLINT, 'price_x10000': 911400::BIGINT,
                             'quantity': 100::BIGINT}] bids
                    """);
            statement.execute("COPY books TO '" + sqlPath(books) + "' (FORMAT PARQUET)");
        }
        writeManifest(dataset, datasetId, events, books, 1);

        HistoricalMarketDataSource source = new HistoricalMarketDataSource(mapper, root, 1);
        assertThatThrownBy(() -> source.load(datasetId))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("not synchronized");
        assertThat(source.loaded()).isFalse();
    }

    @Test
    void clearsTheLoadedStateWhenAReplacementDatasetIsInvalid(@TempDir Path root) throws Exception {
        String datasetId = "invalid-manifest";
        Path dataset = root.resolve(datasetId);
        Files.createDirectories(dataset);
        Files.writeString(dataset.resolve("manifest.json"), """
                {"dataset_id": "different-id", "status": "ready"}
                """);
        Files.createFile(dataset.resolve("events.parquet"));
        Files.createFile(dataset.resolve("book_snapshots.parquet"));
        HistoricalMarketDataSource source = new HistoricalMarketDataSource(mapper, root, 1);

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> source.load(datasetId))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("historical manifest is not ready");

        assertThat(source.loaded()).isFalse();
        source.close();
    }

    private static String sqlPath(Path path) {
        return path.toAbsolutePath().normalize().toString().replace("'", "''");
    }

    private static void writeManifest(
            Path dataset, String datasetId, Path events, Path books, long rowCount)
            throws Exception {
        Files.writeString(dataset.resolve("manifest.json"), """
                {
                  "dataset_id": "%s",
                  "status": "ready",
                  "source_type": "lobster",
                  "symbol": "AAPL",
                  "trade_date": "2012-06-21",
                  "start_time_ms": 34200000,
                  "end_time_ms": 34260000,
                  "depth": 1,
                  "row_count": %d,
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
                rowCount,
                Files.size(events),
                sha256(events),
                Files.size(books),
                sha256(books)));
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }
}
