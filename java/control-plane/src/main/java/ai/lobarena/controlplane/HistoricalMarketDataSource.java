package ai.lobarena.controlplane;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HexFormat;
import java.util.List;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** Replays the vendor-neutral normalized historical Parquet contract. */
final class HistoricalMarketDataSource implements ReplayMarketDataSource {
    private static final Logger LOGGER = LoggerFactory.getLogger(HistoricalMarketDataSource.class);
    private static final Pattern SAFE_DATASET_ID = Pattern.compile("[A-Za-z0-9._-]+");
    private static final int EVENT_WINDOW = 100;
    private static final int DEFAULT_REPLAY_BATCH_ROWS = 4_096;
    private final ObjectMapper mapper;
    private final Path registryRoot;
    private final int rowsPerTick;
    private final DuckDbResourceLimits resourceLimits;
    private final int replayBatchRows;
    private final Deque<ObjectNode> eventTail = new ArrayDeque<>();
    private Connection connection;
    private PreparedStatement statement;
    private ResultSet rows;
    private Path replayEventsPath;
    private Path replayBooksPath;
    private JsonNode manifest;
    private ArrayNode asks;
    private ArrayNode bids;
    private volatile String datasetId;
    private long sourceSequence;
    private long replayPosition;
    private long timestampNs;
    private volatile long tick;
    private long totalRows;
    private long pairedRows;
    private String eventsParquetSha256;
    private String booksParquetSha256;
    private volatile boolean running;
    private boolean eof;
    private boolean kernelCursorStarted;

    HistoricalMarketDataSource(ObjectMapper mapper, Path registryRoot, int rowsPerTick) {
        this(mapper, registryRoot, rowsPerTick, DuckDbResourceLimits.defaults());
    }

    HistoricalMarketDataSource(
            ObjectMapper mapper,
            Path registryRoot,
            int rowsPerTick,
            DuckDbResourceLimits resourceLimits) {
        this(mapper, registryRoot, rowsPerTick, resourceLimits, DEFAULT_REPLAY_BATCH_ROWS);
    }

    HistoricalMarketDataSource(
            ObjectMapper mapper,
            Path registryRoot,
            int rowsPerTick,
            DuckDbResourceLimits resourceLimits,
            int replayBatchRows) {
        this.mapper = mapper;
        this.registryRoot = registryRoot.toAbsolutePath().normalize();
        this.rowsPerTick = Math.max(1, rowsPerTick);
        this.resourceLimits = resourceLimits;
        this.replayBatchRows = Math.max(1, replayBatchRows);
    }

    public synchronized JsonNode load(String requestedDatasetId) {
        if (!SAFE_DATASET_ID.matcher(requestedDatasetId).matches()) {
            throw new IllegalArgumentException("invalid dataset id");
        }
        clearState();
        Path dataset;
        try {
            dataset = registryRoot.resolve(requestedDatasetId).toRealPath();
            if (!dataset.startsWith(registryRoot.toRealPath())) {
                throw new IllegalArgumentException("historical dataset escapes the registry");
            }
        } catch (IOException exception) {
            throw new IllegalArgumentException("unknown historical dataset");
        }
        if (!Files.isDirectory(dataset)) throw new IllegalArgumentException("unknown historical dataset");
        Path manifestPath = dataset.resolve("manifest.json");
        Path eventsPath = dataset.resolve("events.parquet");
        Path booksPath = dataset.resolve("book_snapshots.parquet");
        if (!Files.isRegularFile(manifestPath) || !Files.isRegularFile(eventsPath) || !Files.isRegularFile(booksPath)) {
            throw new IllegalArgumentException("historical dataset is incomplete");
        }
        try {
            manifest = mapper.readTree(Files.readString(manifestPath));
            if (!"ready".equals(manifest.path("status").asText())
                    || !requestedDatasetId.equals(manifest.path("dataset_id").asText())) {
                throw new IllegalArgumentException("historical manifest is not ready");
            }
            datasetId = requestedDatasetId;
            totalRows = manifest.path("row_count").longValue();
            if (totalRows <= 0) {
                throw new IllegalArgumentException("historical manifest row_count must be positive");
            }
            eventsParquetSha256 = verifyOutputFile(eventsPath, "events.parquet");
            booksParquetSha256 = verifyOutputFile(booksPath, "book_snapshots.parquet");
            connection = DriverManager.getConnection("jdbc:duckdb:");
            resourceLimits.apply(connection);
            validateNormalizedTables(eventsPath, booksPath);
            replayEventsPath = eventsPath.toAbsolutePath().normalize();
            replayBooksPath = booksPath.toAbsolutePath().normalize();
            statement = connection.prepareStatement("""
                    SELECT e.source_sequence, e.timestamp_ns_since_midnight, e.event_kind,
                           e.source_event_code, e.source_order_id, e.size, e.price_x10000,
                           e.direction, e.book_side, e.aggressor_side, e.halt_state,
                           to_json(b.asks) AS asks_json, to_json(b.bids) AS bids_json
                    FROM (
                        SELECT * FROM read_parquet(?)
                        WHERE source_sequence > ?
                        LIMIT ?
                    ) e
                    POSITIONAL JOIN (
                        SELECT * FROM read_parquet(?)
                        WHERE source_sequence > ?
                        LIMIT ?
                    ) b
                    """);
            openReplayBatch(Long.MIN_VALUE);
            tick = 0;
            replayPosition = 0;
            running = false;
            eof = false;
            kernelCursorStarted = false;
            eventTail.clear();
            if (!readNext()) {
                throw new IllegalArgumentException("historical dataset is empty");
            }
            return state();
        } catch (IOException | SQLException exception) {
            LOGGER.warn("Failed to load historical dataset {}", requestedDatasetId, exception);
            clearState();
            throw new IllegalArgumentException("failed to load historical dataset: " + exception.getMessage(), exception);
        } catch (RuntimeException exception) {
            LOGGER.warn("Rejected historical dataset {}", requestedDatasetId, exception);
            clearState();
            throw exception;
        }
    }

    public boolean loaded() {
        return datasetId != null;
    }

    public synchronized void clear() {
        clearState();
    }

    public synchronized JsonNode start() {
        requireLoaded();
        running = !eof;
        return state();
    }

    public synchronized JsonNode pause() {
        requireLoaded();
        running = false;
        return state();
    }

    public synchronized JsonNode reset() {
        requireLoaded();
        return load(datasetId);
    }

    public synchronized void advance() {
        requireLoaded();
        if (!running || eof) return;
        tick++;
        for (int index = 0; index < rowsPerTick; index++) {
            if (!readNext()) {
                eof = true;
                running = false;
                break;
            }
            if (eof) break;
        }
    }

    synchronized List<HistoricalSnapshotRecord> nextKernelBatch() {
        requireLoaded();
        if (eof && kernelCursorStarted) return List.of();
        List<HistoricalSnapshotRecord> result = new ArrayList<>();
        if (!kernelCursorStarted) {
            kernelCursorStarted = true;
            result.add(currentRecord());
        }
        while (result.size() < rowsPerTick && !eof) {
            if (!readNext()) {
                eof = true;
                break;
            }
            result.add(currentRecord());
        }
        if (replayPosition >= totalRows) eof = true;
        return List.copyOf(result);
    }

    synchronized boolean eof() {
        return eof && kernelCursorStarted;
    }

    synchronized long currentTimestampNs() {
        return timestampNs;
    }

    synchronized long replayPosition() {
        return replayPosition;
    }

    synchronized long rowCount() {
        return totalRows;
    }

    synchronized String datasetId() {
        requireLoaded();
        return datasetId;
    }

    synchronized String symbol() {
        requireLoaded();
        return manifest.path("symbol").asText();
    }

    synchronized String venue() {
        requireLoaded();
        return manifest.path("venue").asText("LOBSTER");
    }

    synchronized String format() {
        requireLoaded();
        return manifest.path("format").asText("lobster_parquet_v1");
    }

    synchronized String historicalSourceType() {
        requireLoaded();
        return manifest.path("source_type").asText("lobster");
    }

    synchronized long priceTickSizeNanos() {
        return 100_000L;
    }

    synchronized long quantityLotSizeNanos() {
        return 1_000_000_000L;
    }

    synchronized String eventsSha256() {
        requireLoaded();
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
        manifest.path("source_files").forEach(file ->
                digest.update(file.path("sha256").asText().getBytes(StandardCharsets.US_ASCII)));
        return HexFormat.of().formatHex(digest.digest());
    }

    synchronized JsonNode integrity() {
        requireLoaded();
        ObjectNode result = mapper.createObjectNode()
                .put("validated", true)
                .put("format", format())
                .put("source_type", historicalSourceType())
                .put("venue", venue())
                .put("row_count", totalRows)
                .put("paired_rows", pairedRows);
        copyManifestField(result, "parser_version");
        copyManifestField(result, "source_name");
        copyManifestField(result, "source_url");
        copyManifestField(result, "source_stream_sha256");
        copyManifestField(result, "parser_config_sha256");
        copyManifestField(result, "filters");
        copyManifestField(result, "message_counts");
        copyManifestField(result, "truncation_limits");
        result.putObject("output_sha256")
                .put("events.parquet", eventsParquetSha256)
                .put("book_snapshots.parquet", booksParquetSha256);
        return result;
    }

    synchronized JsonNode context(String sourceType) {
        requireLoaded();
        return mapper.createObjectNode()
                .put("source_type", sourceType)
                .put("historical_source_type", historicalSourceType())
                .put("dataset_id", datasetId)
                .put("format", format())
                .put("symbol", symbol())
                .put("venue", venue())
                .put("trade_date", manifest.path("trade_date").asText())
                .put("depth", manifest.path("depth").intValue())
                .put("source_sequence", sourceSequence)
                .put("replay_position", replayPosition)
                .put("exchange_timestamp_ns", timestampNs)
                .put("row_count", totalRows)
                .put("progress", totalRows == 0 ? 0 : Math.min(1.0, (double) replayPosition / totalRows))
                .put("eof", eof())
                .put("events_sha256", eventsSha256());
    }

    synchronized JsonNode datasets() {
        ArrayNode result = mapper.createArrayNode();
        if (!Files.isDirectory(registryRoot)) return result;
        try (var paths = Files.list(registryRoot)) {
            paths.filter(Files::isDirectory).sorted().forEach(path -> {
                Path manifestPath = path.resolve("manifest.json");
                if (!Files.isRegularFile(manifestPath)
                        || !Files.isRegularFile(path.resolve("events.parquet"))
                        || !Files.isRegularFile(path.resolve("book_snapshots.parquet"))) return;
                try {
                    JsonNode candidate = mapper.readTree(Files.readString(manifestPath));
                    if (!"ready".equals(candidate.path("status").asText())) return;
                    result.add(mapper.createObjectNode()
                            .put("dataset_id", candidate.path("dataset_id").asText())
                            .put("source_type", candidate.path("source_type").asText("lobster"))
                            .put("symbol", candidate.path("symbol").asText())
                            .put("venue", candidate.path("venue").asText("LOBSTER"))
                            .put("format", candidate.path("format").asText("lobster_parquet_v1"))
                            .put("trade_date", candidate.path("trade_date").asText())
                            .put("start_time", formatMilliseconds(candidate.path("start_time_ms").longValue()))
                            .put("end_time", formatMilliseconds(candidate.path("end_time_ms").longValue()))
                            .put("depth", candidate.path("depth").intValue())
                            .put("row_count", candidate.path("row_count").longValue()));
                } catch (IOException ignored) {
                    // Invalid datasets are not advertised.
                }
            });
        } catch (IOException exception) {
            throw new IllegalStateException("failed to list historical datasets", exception);
        }
        return result;
    }

    public synchronized JsonNode state() {
        requireLoaded();
        ObjectNode result = mapper.createObjectNode();
        result.put("tick", tick);
        result.put("running", running);
        ArrayNode events = result.putArray("events");
        eventTail.forEach(events::add);
        result.putArray("exchange_events");
        ArrayNode historical = result.putArray("historical_events");
        eventTail.forEach(historical::add);
        ObjectNode book = book();
        result.set("book", book);
        copyNullable(result, book, "best_bid");
        copyNullable(result, book, "best_ask");
        copyNullable(result, book, "mid");
        copyNullable(result, book, "spread");
        result.putArray("active_agents");
        result.putNull("active_scenario");
        result.set("features", features(book));
        ObjectNode detectors = result.putObject("detectors");
        detectors.putArray("scores");
        detectors.putArray("alerts");
        result.putArray("incidents");
        ObjectNode context = result.putObject("market_data");
        context.put("source_type", "historical");
        context.put("historical_source_type", historicalSourceType());
        context.put("dataset_id", datasetId);
        context.put("format", format());
        context.put("venue", venue());
        context.put("symbol", manifest.path("symbol").asText());
        context.put("trade_date", manifest.path("trade_date").asText());
        context.put("depth", manifest.path("depth").intValue());
        context.put("source_sequence", sourceSequence);
        context.put("replay_position", replayPosition);
        context.put("exchange_timestamp_ns", timestampNs);
        context.put("row_count", totalRows);
        context.put("progress", totalRows == 0 ? 0 : Math.min(1.0, (double) replayPosition / totalRows));
        context.put("eof", eof);
        return result;
    }

    JsonNode metricsState() {
        return mapper.createObjectNode()
                .put("tick", tick)
                .put("running", running)
                .put("incidents_count", 0);
    }

    private boolean readNext() {
        try {
            if (!rows.next()) {
                if (replayPosition >= totalRows) {
                    finishEof();
                    return false;
                }
                openReplayBatch(sourceSequence);
                if (!rows.next()) {
                    throw new IllegalStateException(
                            "historical replay ended before the validated row count");
                }
            }
            sourceSequence = rows.getLong("source_sequence");
            replayPosition++;
            timestampNs = rows.getLong("timestamp_ns_since_midnight");
            ObjectNode event = mapper.createObjectNode()
                    .put("type", rows.getString("event_kind").toLowerCase())
                    .put("event_kind", rows.getString("event_kind"))
                    .put("source_event_code", rows.getInt("source_event_code"))
                    .put("source_sequence", sourceSequence)
                    .put("timestamp_ns_since_midnight", timestampNs)
                    .put("source_order_id", rows.getLong("source_order_id"))
                    .put("order_id", Long.toString(rows.getLong("source_order_id")))
                    .put("quantity", rows.getLong("size"))
                    .put("price_x10000", rows.getLong("price_x10000"))
                    .put("symbol", manifest.path("symbol").asText())
                    .put("source", "historical");
            putNullable(event, "side", rows.getString("book_side"), true);
            putNullable(event, "aggressor_side", rows.getString("aggressor_side"), true);
            putNullable(event, "halt_state", rows.getString("halt_state"), false);
            if (rows.getLong("price_x10000") > 1) event.put("price", rows.getLong("price_x10000") / 10_000.0);
            asks = (ArrayNode) mapper.readTree(rows.getString("asks_json"));
            bids = (ArrayNode) mapper.readTree(rows.getString("bids_json"));
            eventTail.addFirst(event);
            while (eventTail.size() > EVENT_WINDOW) eventTail.removeLast();
            if (replayPosition >= totalRows) {
                finishEof();
            }
            return true;
        } catch (SQLException exception) {
            throw new IllegalStateException("historical replay failed", exception);
        }
    }

    private void openReplayBatch(long afterSequence) throws SQLException {
        if (rows != null) {
            rows.close();
            rows = null;
        }
        statement.setString(1, replayEventsPath.toString());
        statement.setLong(2, afterSequence);
        statement.setInt(3, replayBatchRows);
        statement.setString(4, replayBooksPath.toString());
        statement.setLong(5, afterSequence);
        statement.setInt(6, replayBatchRows);
        rows = statement.executeQuery();
    }

    private HistoricalSnapshotRecord currentRecord() {
        return new HistoricalSnapshotRecord(
                sourceSequence,
                timestampNs,
                asks == null ? mapper.createArrayNode() : asks.deepCopy(),
                bids == null ? mapper.createArrayNode() : bids.deepCopy());
    }

    private ObjectNode book() {
        ObjectNode book = mapper.createObjectNode();
        ArrayNode askLevels = book.putArray("asks");
        ArrayNode bidLevels = book.putArray("bids");
        appendLevels(asks, askLevels);
        appendLevels(bids, bidLevels);
        Double bestAsk = priceAt(askLevels);
        Double bestBid = priceAt(bidLevels);
        if (bestAsk == null) book.putNull("best_ask"); else book.put("best_ask", bestAsk);
        if (bestBid == null) book.putNull("best_bid"); else book.put("best_bid", bestBid);
        if (bestAsk == null || bestBid == null) {
            book.putNull("mid");
            book.putNull("spread");
        } else {
            book.put("mid", (bestAsk + bestBid) / 2.0);
            book.put("spread", bestAsk - bestBid);
        }
        return book;
    }

    private void appendLevels(ArrayNode source, ArrayNode target) {
        if (source == null) return;
        source.forEach(level -> target.add(mapper.createObjectNode()
                .put("price", level.path("price_x10000").longValue() / 10_000.0)
                .put("quantity", level.path("quantity").longValue())));
    }

    private ObjectNode features(ObjectNode book) {
        double bidDepth = depth(book.path("bids"));
        double askDepth = depth(book.path("asks"));
        double total = bidDepth + askDepth;
        double mid = book.path("mid").asDouble(0);
        double spread = book.path("spread").asDouble(0);
        return mapper.createObjectNode()
                .put("spread_bps", mid == 0 ? 0 : spread / mid * 10_000)
                .put("depth_top_n", total)
                .put("imbalance", total == 0 ? 0 : (bidDepth - askDepth) / total)
                .put("message_rate", rowsPerTick)
                .put("cancel_to_trade_ratio", 0)
                .put("order_lifetime_ms", 0)
                .put("wall_size_ratio", 1)
                .put("depth_change_pct", 0);
    }

    private double depth(JsonNode levels) {
        double result = 0;
        for (JsonNode level : levels) result += level.path("quantity").doubleValue();
        return result;
    }

    private Double priceAt(ArrayNode levels) {
        return levels == null || levels.isEmpty() ? null : levels.get(0).path("price").doubleValue();
    }

    private void requireLoaded() {
        if (!loaded()) throw new IllegalStateException("no historical dataset is loaded");
    }

    private String verifyOutputFile(Path path, String name) throws IOException {
        JsonNode expected = null;
        for (JsonNode output : manifest.path("output_files")) {
            if (name.equals(output.path("name").asText())) {
                expected = output;
                break;
            }
        }
        if (expected == null) {
            throw new IllegalArgumentException("historical manifest is missing output metadata for " + name);
        }
        String expectedHash = expected.path("sha256").asText();
        if (!expectedHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("historical manifest has an invalid SHA-256 for " + name);
        }
        long expectedSize = expected.path("size_bytes").longValue();
        long actualSize = Files.size(path);
        if (expectedSize != actualSize) {
            throw new IllegalArgumentException("historical output size does not match manifest for " + name);
        }
        String actualHash = sha256(path);
        if (!expectedHash.equals(actualHash)) {
            throw new IllegalArgumentException("historical output SHA-256 does not match manifest for " + name);
        }
        return actualHash;
    }

    private void validateNormalizedTables(Path eventsPath, Path booksPath) throws SQLException {
        long startNs;
        long endNs;
        try {
            startNs = Math.multiplyExact(manifest.path("start_time_ms").longValue(), 1_000_000L);
            endNs = Math.multiplyExact(manifest.path("end_time_ms").longValue(), 1_000_000L);
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException("historical session boundaries overflow nanoseconds", exception);
        }
        if (startNs < 0 || endNs <= startNs) {
            throw new IllegalArgumentException("historical manifest has invalid session boundaries");
        }
        TableValidation events = validateTable(eventsPath, startNs, endNs);
        TableValidation books = validateTable(booksPath, startNs, endNs);
        if (events.rowCount() != totalRows || books.rowCount() != totalRows) {
            throw new IllegalArgumentException(
                    "historical Parquet row counts do not match the manifest");
        }
        if (events.distinctSequences() != totalRows || books.distinctSequences() != totalRows) {
            throw new IllegalArgumentException(
                    "historical source_sequence values must be unique");
        }
        if (events.sequenceRegressions() != 0 || books.sequenceRegressions() != 0) {
            throw new IllegalArgumentException(
                    "historical source_sequence values must be stored in ascending order");
        }
        if (events.timestampRegressions() != 0 || books.timestampRegressions() != 0) {
            throw new IllegalArgumentException(
                    "historical timestamps regress in source_sequence order");
        }
        if (events.outOfSession() != 0 || books.outOfSession() != 0) {
            throw new IllegalArgumentException(
                    "historical timestamps fall outside the manifest session");
        }
        long unpairedRows = countUnpairedRows(eventsPath, booksPath);
        if (unpairedRows != 0) {
            throw new IllegalArgumentException(
                    "historical message and order-book rows are not synchronized");
        }
        pairedRows = events.rowCount();
    }

    private TableValidation validateTable(Path path, long startNs, long endNs) throws SQLException {
        long rowCount;
        long distinctSequences;
        long outOfSession;
        try (PreparedStatement basic = connection.prepareStatement("""
                SELECT count(*) AS row_count,
                       count(DISTINCT source_sequence) AS distinct_sequences,
                       count(*) FILTER (
                           WHERE timestamp_ns_since_midnight < ?
                              OR timestamp_ns_since_midnight >= ?
                       ) AS out_of_session
                FROM read_parquet(?)
                """)) {
            basic.setLong(1, startNs);
            basic.setLong(2, endNs);
            basic.setString(3, path.toAbsolutePath().normalize().toString());
            try (ResultSet result = basic.executeQuery()) {
                if (!result.next()) {
                    throw new IllegalArgumentException("historical integrity query returned no result");
                }
                rowCount = result.getLong("row_count");
                distinctSequences = result.getLong("distinct_sequences");
                outOfSession = result.getLong("out_of_session");
            }
        }
        long sequenceRegressions;
        long timestampRegressions;
        try (PreparedStatement ordering = connection.prepareStatement("""
                SELECT count(*) FILTER (
                           WHERE prior_sequence >= source_sequence
                       ) AS sequence_regressions,
                       count(*) FILTER (
                           WHERE prior_timestamp > timestamp_ns_since_midnight
                       ) AS timestamp_regressions
                FROM (
                    SELECT source_sequence,
                           timestamp_ns_since_midnight,
                           lag(source_sequence) OVER () AS prior_sequence,
                           lag(timestamp_ns_since_midnight) OVER () AS prior_timestamp
                    FROM read_parquet(?)
                )
                """)) {
            ordering.setString(1, path.toAbsolutePath().normalize().toString());
            try (ResultSet result = ordering.executeQuery()) {
                if (!result.next()) {
                    throw new IllegalArgumentException("historical ordering query returned no result");
                }
                sequenceRegressions = result.getLong("sequence_regressions");
                timestampRegressions = result.getLong("timestamp_regressions");
            }
        }
        return new TableValidation(
                rowCount, distinctSequences, sequenceRegressions, timestampRegressions, outOfSession);
    }

    private long countUnpairedRows(Path eventsPath, Path booksPath) throws SQLException {
        try (PreparedStatement pairing = connection.prepareStatement("""
                SELECT count(*) AS unpaired_rows
                FROM read_parquet(?) e
                POSITIONAL JOIN read_parquet(?) b
                WHERE e.source_sequence IS NULL
                   OR b.source_sequence IS NULL
                   OR e.source_sequence != b.source_sequence
                   OR e.timestamp_ns_since_midnight != b.timestamp_ns_since_midnight
                """)) {
            pairing.setString(1, eventsPath.toAbsolutePath().normalize().toString());
            pairing.setString(2, booksPath.toAbsolutePath().normalize().toString());
            try (ResultSet result = pairing.executeQuery()) {
                if (!result.next()) {
                    throw new IllegalArgumentException("historical pairing query returned no result");
                }
                return result.getLong("unpaired_rows");
            }
        }
    }

    private record TableValidation(
            long rowCount,
            long distinctSequences,
            long sequenceRegressions,
            long timestampRegressions,
            long outOfSession) {}

    private static String sha256(Path path) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static void copyNullable(ObjectNode target, ObjectNode source, String field) {
        if (source.path(field).isNull()) target.putNull(field); else target.set(field, source.path(field));
    }

    private void copyManifestField(ObjectNode target, String field) {
        JsonNode value = manifest.path(field);
        if (value.isMissingNode() || value.isNull()) {
            target.putNull(field);
        } else {
            target.set(field, value.deepCopy());
        }
    }

    private static void putNullable(ObjectNode target, String field, String value, boolean lowerCase) {
        if (value == null) target.putNull(field); else target.put(field, lowerCase ? value.toLowerCase() : value);
    }

    private void closeResources() {
        try {
            if (rows != null) rows.close();
        } catch (SQLException exception) {
            LOGGER.warn("Failed to close DuckDB replay result set", exception);
        }
        try {
            if (statement != null) statement.close();
        } catch (SQLException exception) {
            LOGGER.warn("Failed to close DuckDB replay statement", exception);
        }
        try {
            if (connection != null) connection.close();
        } catch (SQLException exception) {
            LOGGER.warn("Failed to close DuckDB replay connection", exception);
        }
        rows = null;
        statement = null;
        connection = null;
        replayEventsPath = null;
        replayBooksPath = null;
    }

    private void finishEof() {
        eof = true;
        running = false;
        closeResources();
    }

    synchronized boolean resourcesOpen() {
        return rows != null || statement != null || connection != null;
    }

    private void clearState() {
        closeResources();
        datasetId = null;
        manifest = null;
        asks = null;
        bids = null;
        sourceSequence = 0;
        replayPosition = 0;
        timestampNs = 0;
        tick = 0;
        totalRows = 0;
        pairedRows = 0;
        eventsParquetSha256 = null;
        booksParquetSha256 = null;
        eventTail.clear();
        running = false;
        eof = false;
        kernelCursorStarted = false;
    }

    @Override
    public synchronized void close() {
        clear();
    }

    private static String formatMilliseconds(long value) {
        long hours = value / 3_600_000;
        long remainder = value % 3_600_000;
        long minutes = remainder / 60_000;
        remainder %= 60_000;
        long seconds = remainder / 1_000;
        long milliseconds = remainder % 1_000;
        return "%02d:%02d:%02d.%03d".formatted(hours, minutes, seconds, milliseconds);
    }

    record HistoricalSnapshotRecord(
            long sourceSequence,
            long timestampNs,
            ArrayNode asks,
            ArrayNode bids) {}
}
