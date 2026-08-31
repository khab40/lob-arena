package ai.lobarena.controlplane;

import ai.lobarena.exchange.v1.ExchangeEvent;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** Durable, segmented JSONL archive for canonical exchange events. */
final class CanonicalEventArchive implements AutoCloseable {
    private static final String MANIFEST_FILE = "manifest.json";

    private final Path root;
    private final ObjectMapper mapper;
    private final int segmentEvents;
    private final long maxStreamBytes;
    private final Function<ExchangeEvent, ObjectNode> serializer;
    private final List<ArchivedEvent> pending = new ArrayList<>();

    private String streamId;
    private Path streamRoot;
    private long latestPersistedSequence;
    private long archiveBytes;

    CanonicalEventArchive(
            Path outputRoot,
            ObjectMapper mapper,
            int segmentEvents,
            long maxStreamBytes,
            Function<ExchangeEvent, ObjectNode> serializer) {
        if (segmentEvents <= 0) {
            throw new IllegalArgumentException("segmentEvents must be positive");
        }
        if (maxStreamBytes <= 0) {
            throw new IllegalArgumentException("maxStreamBytes must be positive");
        }
        this.root = outputRoot.resolve("history/exchange-events").normalize();
        this.mapper = mapper;
        this.segmentEvents = segmentEvents;
        this.maxStreamBytes = maxStreamBytes;
        this.serializer = serializer;
    }

    synchronized String beginStream() {
        // Completed ticks are flushed by the arena before publication. Any
        // pending rows here belong to a failed, unpublished tick and must not
        // prevent a reset from establishing a fresh stream.
        pending.clear();
        streamId = UUID.randomUUID().toString();
        streamRoot = root.resolve(streamId).normalize();
        if (!streamRoot.startsWith(root)) {
            throw new IllegalStateException("generated stream path escapes archive root");
        }
        latestPersistedSequence = 0;
        archiveBytes = 0;
        pending.clear();
        try {
            Files.createDirectories(streamRoot);
            writeManifest();
        } catch (IOException exception) {
            throw new IllegalStateException("failed to initialize canonical event archive", exception);
        }
        return streamId;
    }

    synchronized void append(ExchangeEvent event) {
        requireStream();
        long expected = latestPersistedSequence + pending.size() + 1L;
        long sequence = event.getMetadata().getSequence();
        if (sequence != expected) {
            throw new IllegalStateException(
                    "canonical archive sequence gap: expected " + expected + " but received " + sequence);
        }
        ObjectNode row = mapper.createObjectNode()
                .put("stream_id", streamId)
                .set("event", serializer.apply(event));
        pending.add(new ArchivedEvent(sequence, row));
    }

    synchronized void flushCompletedTick() {
        if (pending.isEmpty()) {
            return;
        }
        requireStream();
        try {
            List<SegmentBatch> batches = new ArrayList<>();
            int cursor = 0;
            long pendingBytes = 0;
            while (cursor < pending.size()) {
                ArchivedEvent first = pending.get(cursor);
                long segmentIndex = (first.sequence() - 1) / segmentEvents;
                long segmentEnd = (segmentIndex + 1) * segmentEvents;
                StringBuilder payload = new StringBuilder();
                long lastSequence = first.sequence();
                while (cursor < pending.size() && pending.get(cursor).sequence() <= segmentEnd) {
                    ArchivedEvent item = pending.get(cursor++);
                    payload.append(mapper.writeValueAsString(item.row())).append(System.lineSeparator());
                    lastSequence = item.sequence();
                }
                byte[] encoded = payload.toString().getBytes(StandardCharsets.UTF_8);
                pendingBytes = Math.addExact(pendingBytes, encoded.length);
                batches.add(new SegmentBatch(segmentIndex, encoded, lastSequence));
            }
            if (archiveBytes + pendingBytes > maxStreamBytes) {
                throw new ArchiveCapacityExceededException(
                        "canonical event archive exceeded configured stream quota of "
                                + maxStreamBytes + " bytes");
            }
            for (SegmentBatch batch : batches) {
                Files.write(
                        segmentPath(batch.segmentIndex()),
                        batch.encoded(),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND);
                archiveBytes += batch.encoded().length;
                latestPersistedSequence = batch.lastSequence();
            }
            pending.clear();
            writeManifest();
        } catch (IOException exception) {
            throw new IllegalStateException("failed to persist canonical event batch", exception);
        }
    }

    synchronized List<JsonNode> readAfter(String requestedStreamId, long afterSequence, int limit) {
        if (limit <= 0) {
            return List.of();
        }
        Path requestedRoot = resolveStream(requestedStreamId);
        long latestAvailable = latestSequence(requestedStreamId);
        long target = Math.max(1, afterSequence + 1);
        long segmentIndex = (target - 1) / segmentEvents;
        List<JsonNode> result = new ArrayList<>(limit);
        try {
            while (result.size() < limit) {
                Path segment = requestedRoot.resolve(segmentName(segmentIndex));
                if (!Files.isRegularFile(segment)) {
                    break;
                }
                try (BufferedReader reader = Files.newBufferedReader(segment, StandardCharsets.UTF_8)) {
                    String line;
                    while ((line = reader.readLine()) != null && result.size() < limit) {
                        if (line.isBlank()) {
                            continue;
                        }
                        JsonNode row = mapper.readTree(line);
                        JsonNode event = row.path("event");
                        long sequence = event.path("sequence").longValue();
                        if (sequence > latestAvailable) {
                            break;
                        }
                        if (sequence > afterSequence) {
                            result.add(event.deepCopy());
                        }
                    }
                }
                segmentIndex++;
            }
            return List.copyOf(result);
        } catch (IOException | RuntimeException exception) {
            throw new IllegalStateException(
                    "failed to read canonical event archive for stream " + requestedStreamId,
                    exception);
        }
    }

    synchronized long latestSequence(String requestedStreamId) {
        Path requestedRoot = resolveStream(requestedStreamId);
        try {
            JsonNode manifest = mapper.readTree(
                    Files.readString(requestedRoot.resolve(MANIFEST_FILE), StandardCharsets.UTF_8));
            return manifest.path("latest_sequence").longValue();
        } catch (IOException | RuntimeException exception) {
            throw new IllegalStateException(
                    "failed to read canonical stream manifest for " + requestedStreamId,
                    exception);
        }
    }

    synchronized String streamId() {
        requireStream();
        return streamId;
    }

    synchronized long latestPersistedSequence() {
        return latestPersistedSequence;
    }

    synchronized long archiveBytes() {
        return archiveBytes;
    }

    long maxStreamBytes() {
        return maxStreamBytes;
    }

    synchronized int pendingCount() {
        return pending.size();
    }

    synchronized void deleteStream(String requestedStreamId) {
        Path requestedRoot = resolveStream(requestedStreamId);
        try (var paths = Files.walk(requestedRoot)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.delete(path);
                } catch (IOException exception) {
                    throw new StreamDeletionException(exception);
                }
            });
        } catch (IOException | StreamDeletionException exception) {
            throw new IllegalStateException(
                    "failed to delete canonical stream " + requestedStreamId,
                    exception instanceof StreamDeletionException ? exception.getCause() : exception);
        }
        if (requestedStreamId.equals(streamId)) {
            streamId = null;
            streamRoot = null;
            latestPersistedSequence = 0;
            archiveBytes = 0;
            pending.clear();
        }
    }

    @Override
    public synchronized void close() {
        flushCompletedTick();
    }

    private Path resolveStream(String requestedStreamId) {
        if (requestedStreamId == null || !requestedStreamId.matches("[0-9a-fA-F-]{36}")) {
            throw new IllegalArgumentException("invalid canonical stream id");
        }
        Path resolved = root.resolve(requestedStreamId).normalize();
        if (!resolved.startsWith(root) || !Files.isDirectory(resolved)) {
            throw new IllegalArgumentException("unknown canonical stream id");
        }
        return resolved;
    }

    private Path segmentPath(long segmentIndex) {
        return streamRoot.resolve(segmentName(segmentIndex));
    }

    private static String segmentName(long segmentIndex) {
        return "segment-%012d.jsonl".formatted(segmentIndex);
    }

    private void writeManifest() throws IOException {
        ObjectNode manifest = mapper.createObjectNode()
                .put("schema_version", 1)
                .put("stream_id", streamId)
                .put("first_sequence", latestPersistedSequence == 0 ? 0 : 1)
                .put("latest_sequence", latestPersistedSequence)
                .put("segment_events", segmentEvents)
                .put("archive_bytes", archiveBytes);
        ArrayNode segments = manifest.putArray("segments");
        if (latestPersistedSequence > 0) {
            long lastSegment = (latestPersistedSequence - 1) / segmentEvents;
            for (long index = 0; index <= lastSegment; index++) {
                long first = index * segmentEvents + 1;
                long last = Math.min(latestPersistedSequence, (index + 1) * segmentEvents);
                segments.add(mapper.createObjectNode()
                        .put("file", segmentName(index))
                        .put("first_sequence", first)
                        .put("last_sequence", last));
            }
        }
        Path temporary = streamRoot.resolve(MANIFEST_FILE + ".tmp");
        Path target = streamRoot.resolve(MANIFEST_FILE);
        Files.writeString(
                temporary,
                mapper.writeValueAsString(manifest) + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);
        try {
            Files.move(
                    temporary,
                    target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException ignored) {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private void requireStream() {
        if (streamId == null || streamRoot == null) {
            throw new IllegalStateException("canonical event stream has not been initialized");
        }
    }

    private record ArchivedEvent(long sequence, ObjectNode row) {}

    private record SegmentBatch(long segmentIndex, byte[] encoded, long lastSequence) {}

    private static final class StreamDeletionException extends RuntimeException {
        StreamDeletionException(IOException cause) {
            super(cause);
        }
    }

    static final class ArchiveCapacityExceededException extends IllegalStateException {
        ArchiveCapacityExceededException(String message) {
            super(message);
        }
    }
}
