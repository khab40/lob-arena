package ai.lobarena.kernel.determinism;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import org.junit.jupiter.api.Test;

final class DeterminismContractTest {
    @Test
    void splitMix64MatchesLanguageNeutralVectors() {
        assertOutputs(0L, List.of(
                "e220a8397b1dcdaf",
                "6e789e6aa1b965f4",
                "06c45d188009454f",
                "f88bb8a8724c81ec",
                "1b39896a51a8749b"));
        assertOutputs(1L, List.of("910a2dec89025cc1", "beeb8da1658eec67", "f893a2eefb32555e"));
        assertEquals(0L, new SplitMix64(3).nextInt(BigInteger.ONE.shiftLeft(63)) >>> 63);
    }

    @Test
    void namedStreamsAndNumericRulesMatchLanguageNeutralVectors() {
        assertEquals("e607c29a25b4dcd0", hex(DeterministicValues.deriveStreamSeed(42, "agents")));
        assertEquals("32d2702900776bb0", hex(DeterministicValues.deriveStreamSeed(42, "scenarios")));
        assertEquals("263661d30d4b6d7b", hex(DeterministicValues.deriveStreamSeed(42, "baseline")));
        assertEquals(68_125, DeterministicValues.decimalToUnits("68125", 1_000_000_000));
        assertEquals(995, DeterministicValues.decimalToUnits("99.5", 100_000_000));
        assertEquals(1_500, DeterministicValues.decimalToUnits("1.5", 1_000_000));
        assertEquals(925_000, DeterministicValues.quantizeMetric("0.9250005", 6));
        assertEquals(925_002, DeterministicValues.quantizeMetric("0.9250015", 6));
        assertEquals(199, DeterministicValues.midpointTicksX2(99, 100));
        assertEquals("SIM:add:1", DeterministicValues.simulationEventId("SIM", "ADD", 1));
    }

    @Test
    void totalOrderAndValidationMatchTheFrozenContract() {
        List<IdentifiedKey> items = new ArrayList<>(List.of(
                key("snapshot", 7, 40, "EXCHANGE", 0, 0),
                key("agent-b", 7, 10, "B", 0, 0),
                key("scenario", 7, 20, "ABUSER", 0, 0),
                key("agent-a-second", 7, 10, "A", 1, 1),
                key("earlier", 6, 40, "EXCHANGE", 0, 0),
                key("agent-a-first", 7, 10, "A", 0, 0)));
        items.sort((left, right) -> left.key().compareTo(right.key()));

        assertEquals(
                List.of("earlier", "agent-a-first", "agent-a-second", "agent-b", "scenario", "snapshot"),
                items.stream().map(item -> item.id()).toList());
        assertThrows(
                IllegalArgumentException.class,
                () -> DeterministicValues.decimalToUnits("1.0000005", 1_000));
        assertThrows(
                IllegalArgumentException.class,
                () -> DeterministicValues.simulationEventId("SIM:BAD", "add", 1));
        assertThrows(
                IllegalArgumentException.class,
                () -> new EventOrderKey(1, 10, 0, "агент", 0, 0));
    }

    private static void assertOutputs(long seed, List<String> expected) {
        SplitMix64 random = new SplitMix64(seed);
        assertEquals(expected, expected.stream().map(ignored -> hex(random.nextUnsignedLong())).toList());
    }

    private static String hex(long value) {
        return HexFormat.of().toHexDigits(value);
    }

    private static IdentifiedKey key(
            String id, long logicalTime, int phase, String actorId, long sourceSequence, long insertionSequence) {
        return new IdentifiedKey(
                id,
                new EventOrderKey(logicalTime, phase, 0, actorId, sourceSequence, insertionSequence));
    }

    private record IdentifiedKey(String id, EventOrderKey key) {}
}
