package ai.lobarena.controlplane;

import ai.lobarena.exchange.v1.Side;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * Strict adapter for immutable, vendor-neutral historical CSV records.
 *
 * <p>The adapter validates the source lifecycle once, keeps an immutable record list, and exposes
 * deterministic batches to the authoritative integer matching engine. It never assigns labels.
 */
final class HistoricalCsvMarketDataSource {
    private static final long NANOS_PER_DAY = 86_400_000_000_000L;
    private static final Pattern SAFE_DATASET_ID = Pattern.compile("[A-Za-z0-9._-]+");
    private static final Pattern SAFE_SOURCE_ID = Pattern.compile("[A-Za-z0-9._-]+");
    private static final String HEADER =
            "source_sequence,timestamp_ns,event_type,order_id,participant_id,side,price_ticks,quantity_lots";

    private final ObjectMapper mapper;
    private final Path registryRoot;
    private final int rowsPerTick;
    private Dataset dataset;
    private int cursor;

    HistoricalCsvMarketDataSource(ObjectMapper mapper, Path registryRoot, int rowsPerTick) {
        this.mapper = mapper;
        this.registryRoot = registryRoot.toAbsolutePath().normalize();
        this.rowsPerTick = Math.max(1, rowsPerTick);
    }

    synchronized JsonNode load(String requestedDatasetId) {
        dataset = readDataset(requestedDatasetId);
        cursor = 0;
        return context("historical");
    }

    synchronized boolean supports(String requestedDatasetId) {
        if (requestedDatasetId == null || !SAFE_DATASET_ID.matcher(requestedDatasetId).matches()) {
            return false;
        }
        try {
            Path directory = resolveDataset(requestedDatasetId);
            return Files.isRegularFile(directory.resolve("manifest.json"))
                    && Files.isRegularFile(directory.resolve("events.csv"));
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    synchronized boolean loaded() {
        return dataset != null;
    }

    synchronized void clear() {
        dataset = null;
        cursor = 0;
    }

    synchronized void reset() {
        requireLoaded();
        cursor = 0;
    }

    synchronized List<HistoricalCsvRecord> nextBatch() {
        requireLoaded();
        if (eof()) {
            return List.of();
        }
        int end = Math.min(dataset.records().size(), cursor + rowsPerTick);
        List<HistoricalCsvRecord> result = dataset.records().subList(cursor, end);
        cursor = end;
        return result;
    }

    synchronized boolean eof() {
        return dataset != null && cursor >= dataset.records().size();
    }

    synchronized int replayPosition() {
        return cursor;
    }

    synchronized long currentTimestampNs() {
        if (dataset == null || cursor == 0) {
            return 0;
        }
        return dataset.records().get(cursor - 1).timestampNs();
    }

    synchronized long currentSourceSequence() {
        if (dataset == null || cursor == 0) {
            return 0;
        }
        return dataset.records().get(cursor - 1).sourceSequence();
    }

    synchronized String datasetId() {
        requireLoaded();
        return dataset.datasetId();
    }

    synchronized String symbol() {
        requireLoaded();
        return dataset.symbol();
    }

    synchronized String venue() {
        requireLoaded();
        return dataset.venue();
    }

    synchronized long priceTickSizeNanos() {
        requireLoaded();
        return dataset.priceTickSizeNanos();
    }

    synchronized long quantityLotSizeNanos() {
        requireLoaded();
        return dataset.quantityLotSizeNanos();
    }

    synchronized int rowCount() {
        requireLoaded();
        return dataset.records().size();
    }

    synchronized String eventsSha256() {
        requireLoaded();
        return dataset.eventsSha256();
    }

    synchronized JsonNode context(String sourceType) {
        requireLoaded();
        ObjectNode result = mapper.createObjectNode()
                .put("source_type", sourceType)
                .put("dataset_id", dataset.datasetId())
                .put("format", "canonical_csv_v1")
                .put("symbol", dataset.symbol())
                .put("venue", dataset.venue())
                .put("trade_date", dataset.tradeDate())
                .put("depth", 0)
                .put("source_sequence", currentSourceSequence())
                .put("replay_position", cursor)
                .put("exchange_timestamp_ns", currentTimestampNs())
                .put("row_count", dataset.records().size())
                .put("progress", dataset.records().isEmpty() ? 0.0 : (double) cursor / dataset.records().size())
                .put("eof", eof())
                .put("events_sha256", dataset.eventsSha256());
        return result;
    }

    synchronized JsonNode datasets() {
        ArrayNode result = mapper.createArrayNode();
        if (!Files.isDirectory(registryRoot)) {
            return result;
        }
        try (Stream<Path> paths = Files.list(registryRoot)) {
            paths.filter(Files::isDirectory)
                    .sorted()
                    .forEach(path -> {
                        String id = path.getFileName().toString();
                        if (!supports(id)) {
                            return;
                        }
                        try {
                            Dataset candidate = readDataset(id);
                            result.add(mapper.createObjectNode()
                                    .put("dataset_id", candidate.datasetId())
                                    .put("source_type", "canonical_csv")
                                    .put("symbol", candidate.symbol())
                                    .put("venue", candidate.venue())
                                    .put("trade_date", candidate.tradeDate())
                                    .put("start_time", formatTimestamp(candidate.records().getFirst().timestampNs()))
                                    .put("end_time", formatTimestamp(candidate.records().getLast().timestampNs()))
                                    .put("depth", 0)
                                    .put("row_count", candidate.records().size())
                                    .put("events_sha256", candidate.eventsSha256()));
                        } catch (IllegalArgumentException ignored) {
                            // Invalid datasets are not advertised as runnable.
                        }
                    });
        } catch (IOException exception) {
            throw new IllegalStateException("failed to list historical CSV datasets", exception);
        }
        return result;
    }

    private Dataset readDataset(String requestedDatasetId) {
        Path directory = resolveDataset(requestedDatasetId);
        Path manifestPath = directory.resolve("manifest.json");
        Path eventsPath = directory.resolve("events.csv");
        if (!Files.isRegularFile(manifestPath) || !Files.isRegularFile(eventsPath)) {
            throw new IllegalArgumentException("historical CSV dataset is incomplete");
        }
        try {
            JsonNode manifest = mapper.readTree(Files.readString(manifestPath, StandardCharsets.UTF_8));
            if (!"ready".equals(manifest.path("status").asString())
                    || !"canonical_csv_v1".equals(manifest.path("format").asString())
                    || !requestedDatasetId.equals(manifest.path("dataset_id").asString())) {
                throw new IllegalArgumentException("historical CSV manifest is not ready");
            }
            String symbol = requiredText(manifest, "symbol");
            String venue = requiredText(manifest, "venue");
            String tradeDate = requiredText(manifest, "trade_date");
            long priceTickSizeNanos = positiveLong(manifest, "price_tick_size_nanos");
            long quantityLotSizeNanos = positiveLong(manifest, "quantity_lot_size_nanos");
            String expectedSha256 = requiredText(manifest, "events_sha256").toLowerCase();
            String actualSha256 = sha256(eventsPath);
            if (!expectedSha256.equals(actualSha256)) {
                throw new IllegalArgumentException("historical CSV checksum does not match manifest");
            }
            List<HistoricalCsvRecord> records = parseRecords(eventsPath);
            if (manifest.path("row_count").longValue() != records.size()) {
                throw new IllegalArgumentException("historical CSV row count does not match manifest");
            }
            validateLifecycle(records);
            return new Dataset(
                    requestedDatasetId,
                    symbol,
                    venue,
                    tradeDate,
                    priceTickSizeNanos,
                    quantityLotSizeNanos,
                    actualSha256,
                    List.copyOf(records));
        } catch (IOException exception) {
            throw new IllegalArgumentException("failed to read historical CSV dataset", exception);
        }
    }

    private List<HistoricalCsvRecord> parseRecords(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        if (lines.isEmpty() || !HEADER.equals(lines.getFirst())) {
            throw new IllegalArgumentException("historical CSV header does not match canonical_csv_v1");
        }
        List<HistoricalCsvRecord> records = new ArrayList<>();
        for (int index = 1; index < lines.size(); index++) {
            String line = lines.get(index);
            if (line.isBlank()) {
                continue;
            }
            String[] fields = line.split(",", -1);
            if (fields.length != 8) {
                throw new IllegalArgumentException("historical CSV row " + (index + 1) + " must have 8 fields");
            }
            records.add(parseRecord(fields, index + 1));
        }
        if (records.isEmpty()) {
            throw new IllegalArgumentException("historical CSV dataset is empty");
        }
        return records;
    }

    private HistoricalCsvRecord parseRecord(String[] fields, int rowNumber) {
        try {
            long sourceSequence = Long.parseLong(fields[0]);
            long timestampNs = Long.parseLong(fields[1]);
            String eventType = fields[2].toUpperCase();
            String orderId = safeSourceId("order_id", fields[3]);
            String participantId = safeSourceId("participant_id", fields[4]);
            Side side = switch (fields[5].toUpperCase()) {
                case "BUY" -> Side.SIDE_BUY;
                case "SELL" -> Side.SIDE_SELL;
                default -> throw new IllegalArgumentException("side must be BUY or SELL");
            };
            Long priceTicks = fields[6].isBlank() ? null : Long.parseLong(fields[6]);
            long quantityLots = fields[7].isBlank() ? 0 : Long.parseLong(fields[7]);
            return new HistoricalCsvRecord(
                    sourceSequence,
                    timestampNs,
                    eventType,
                    orderId,
                    participantId,
                    side,
                    priceTicks,
                    quantityLots);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "invalid historical CSV row " + rowNumber + ": " + exception.getMessage(), exception);
        }
    }

    private void validateLifecycle(List<HistoricalCsvRecord> records) {
        long previousSequence = 0;
        long previousTimestamp = 0;
        Set<String> seenOrderIds = new HashSet<>();
        Map<String, OrderState> resting = new HashMap<>();
        for (HistoricalCsvRecord record : records) {
            if (record.sourceSequence() <= previousSequence) {
                throw new IllegalArgumentException("historical source_sequence must be strictly increasing");
            }
            if (record.timestampNs() < 0 || record.timestampNs() >= NANOS_PER_DAY) {
                throw new IllegalArgumentException(
                        "historical timestamp_ns must be nanoseconds since midnight");
            }
            if (record.timestampNs() < previousTimestamp) {
                throw new IllegalArgumentException("historical timestamp_ns must be non-decreasing");
            }
            previousSequence = record.sourceSequence();
            previousTimestamp = record.timestampNs();
            switch (record.eventType()) {
                case "ADD" -> {
                    requirePositive(record.priceTicks(), "ADD price_ticks");
                    requirePositive(record.quantityLots(), "ADD quantity_lots");
                    if (!seenOrderIds.add(record.orderId())) {
                        throw new IllegalArgumentException("historical order_id is reused: " + record.orderId());
                    }
                    resting.put(record.orderId(), OrderState.from(record));
                }
                case "MODIFY" -> {
                    requirePositive(record.quantityLots(), "MODIFY quantity_lots");
                    OrderState existing = requireResting(resting, record);
                    requireSameIdentity(existing, record);
                    long price = record.priceTicks() == null ? existing.priceTicks() : record.priceTicks();
                    requirePositive(price, "MODIFY price_ticks");
                    resting.put(record.orderId(), new OrderState(
                            record.participantId(), record.side(), price, record.quantityLots()));
                }
                case "CANCEL" -> {
                    if (record.priceTicks() != null || record.quantityLots() != 0) {
                        throw new IllegalArgumentException(
                                "CANCEL price_ticks must be empty and quantity_lots must be 0");
                    }
                    OrderState existing = requireResting(resting, record);
                    requireSameIdentity(existing, record);
                    resting.remove(record.orderId());
                }
                case "MARKET" -> {
                    requirePositive(record.quantityLots(), "MARKET quantity_lots");
                    if (record.priceTicks() != null) {
                        throw new IllegalArgumentException("MARKET price_ticks must be empty");
                    }
                    if (!seenOrderIds.add(record.orderId())) {
                        throw new IllegalArgumentException("historical order_id is reused: " + record.orderId());
                    }
                }
                default -> throw new IllegalArgumentException(
                        "unsupported historical event_type: " + record.eventType());
            }
        }
    }

    private Path resolveDataset(String requestedDatasetId) {
        if (requestedDatasetId == null || !SAFE_DATASET_ID.matcher(requestedDatasetId).matches()) {
            throw new IllegalArgumentException("invalid dataset id");
        }
        try {
            Path dataset = registryRoot.resolve(requestedDatasetId).toRealPath();
            if (!dataset.startsWith(registryRoot.toRealPath()) || !Files.isDirectory(dataset)) {
                throw new IllegalArgumentException("historical CSV dataset escapes the registry");
            }
            return dataset;
        } catch (IOException exception) {
            throw new IllegalArgumentException("unknown historical CSV dataset");
        }
    }

    private static OrderState requireResting(
            Map<String, OrderState> resting, HistoricalCsvRecord record) {
        OrderState existing = resting.get(record.orderId());
        if (existing == null) {
            throw new IllegalArgumentException(
                    record.eventType() + " references unknown order_id: " + record.orderId());
        }
        return existing;
    }

    private static void requireSameIdentity(OrderState existing, HistoricalCsvRecord record) {
        if (!existing.participantId().equals(record.participantId()) || existing.side() != record.side()) {
            throw new IllegalArgumentException(
                    record.eventType() + " changes historical order ownership or side");
        }
    }

    private static String requiredText(JsonNode node, String field) {
        String value = node.path(field).asString("");
        if (value.isBlank()) {
            throw new IllegalArgumentException("historical CSV manifest requires " + field);
        }
        return value;
    }

    private static long positiveLong(JsonNode node, String field) {
        long value = node.path(field).longValue();
        requirePositive(value, field);
        return value;
    }

    private static void requirePositive(Long value, String field) {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(field + " must be positive");
        }
    }

    private static String safeSourceId(String field, String value) {
        if (!SAFE_SOURCE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(field + " must match " + SAFE_SOURCE_ID.pattern());
        }
        return value;
    }

    private static String sha256(Path path) throws IOException {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 must be available", exception);
        }
    }

    private static String formatTimestamp(long timestampNs) {
        long milliseconds = timestampNs / 1_000_000;
        long hours = milliseconds / 3_600_000;
        long minutes = (milliseconds % 3_600_000) / 60_000;
        long seconds = (milliseconds % 60_000) / 1_000;
        long millis = milliseconds % 1_000;
        return "%02d:%02d:%02d.%03d".formatted(hours, minutes, seconds, millis);
    }

    private void requireLoaded() {
        if (dataset == null) {
            throw new IllegalStateException("no historical CSV dataset is loaded");
        }
    }

    record HistoricalCsvRecord(
            long sourceSequence,
            long timestampNs,
            String eventType,
            String orderId,
            String participantId,
            Side side,
            Long priceTicks,
            long quantityLots) {}

    private record Dataset(
            String datasetId,
            String symbol,
            String venue,
            String tradeDate,
            long priceTickSizeNanos,
            long quantityLotSizeNanos,
            String eventsSha256,
            List<HistoricalCsvRecord> records) {}

    private record OrderState(String participantId, Side side, long priceTicks, long quantityLots) {
        static OrderState from(HistoricalCsvRecord record) {
            return new OrderState(
                    record.participantId(),
                    record.side(),
                    record.priceTicks(),
                    record.quantityLots());
        }
    }
}
