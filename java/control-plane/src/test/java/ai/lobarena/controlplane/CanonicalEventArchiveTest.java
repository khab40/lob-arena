package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ai.lobarena.exchange.v1.EventMetadata;
import ai.lobarena.exchange.v1.EventSource;
import ai.lobarena.exchange.v1.ExchangeEvent;
import ai.lobarena.exchange.v1.LobSnapshot;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class CanonicalEventArchiveTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void rotatesSegmentsAndReplaysAcrossTheirBoundary(@TempDir Path output) throws Exception {
        CanonicalEventArchive archive =
                new CanonicalEventArchive(output, mapper, 2, 1_000_000, this::json);
        String streamId = archive.beginStream();
        archive.append(event(1));
        archive.append(event(2));
        archive.append(event(3));
        archive.flushCompletedTick();

        assertThat(archive.readAfter(streamId, 1, 10))
                .extracting(item -> item.path("sequence").longValue())
                .containsExactly(2L, 3L);
        assertThat(Files.readString(
                        output.resolve("history/exchange-events")
                                .resolve(streamId)
                                .resolve("manifest.json")))
                .contains("\"latest_sequence\":3");
        assertThat(Files.isRegularFile(
                        output.resolve("history/exchange-events")
                                .resolve(streamId)
                                .resolve("segment-000000000001.jsonl")))
                .isTrue();
    }

    @Test
    void rejectsACompletedTickThatExceedsTheStreamQuota(@TempDir Path output) {
        CanonicalEventArchive archive =
                new CanonicalEventArchive(output, mapper, 2, 1, this::json);
        archive.beginStream();
        archive.append(event(1));

        assertThatThrownBy(archive::flushCompletedTick)
                .isInstanceOf(CanonicalEventArchive.ArchiveCapacityExceededException.class)
                .hasMessageContaining("stream quota");
    }

    @Test
    void deletesACompletedStreamWithoutAffectingAnother(@TempDir Path output) {
        CanonicalEventArchive archive =
                new CanonicalEventArchive(output, mapper, 2, 1_000_000, this::json);
        String first = archive.beginStream();
        archive.append(event(1));
        archive.flushCompletedTick();
        String second = archive.beginStream();
        archive.append(event(1));
        archive.flushCompletedTick();

        archive.deleteStream(first);

        assertThat(output.resolve("history/exchange-events").resolve(first)).doesNotExist();
        assertThat(archive.readAfter(second, 0, 10)).hasSize(1);
        assertThatThrownBy(() -> archive.readAfter(first, 0, 10))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unknown canonical stream id");

        archive.deleteStream(second);
        String replacement = archive.beginStream();
        archive.append(event(1));
        archive.flushCompletedTick();
        assertThat(archive.readAfter(replacement, 0, 10)).hasSize(1);
    }

    private ObjectNode json(ExchangeEvent event) {
        return mapper.createObjectNode()
                .put("sequence", event.getMetadata().getSequence())
                .put("event_type", "snapshot");
    }

    private static ExchangeEvent event(long sequence) {
        return ExchangeEvent.newBuilder()
                .setMetadata(EventMetadata.newBuilder()
                        .setSchemaVersion(1)
                        .setEventId("event-" + sequence)
                        .setSequence(sequence)
                        .setSource(EventSource.EVENT_SOURCE_SIMULATION)
                        .setSymbol("TEST")
                        .setVenue("SIM")
                        .setTick(sequence))
                .setSnapshot(LobSnapshot.newBuilder().setDepth(1))
                .build();
    }
}
