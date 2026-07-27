package ai.lobarena.controlplane;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

final class ArenaEventMetrics {
    ArenaEventMetrics(MeterRegistry registry, LiveArenaService arena) {
        Gauge.builder(
                        "lob.arena.events.retained",
                        arena,
                        value -> value.retainedEventCountMetric())
                .description("Canonical exchange events retained in live JVM memory")
                .register(registry);
        Gauge.builder(
                        "lob.arena.events.latest.sequence",
                        arena,
                        value -> value.latestSequenceMetric())
                .description("Latest canonical exchange event sequence in the active stream")
                .register(registry);
        Gauge.builder(
                        "lob.arena.events.archive.bytes",
                        arena,
                        value -> value.archiveBytesMetric())
                .description("Bytes persisted for the active canonical event stream")
                .baseUnit("bytes")
                .register(registry);
    }
}
