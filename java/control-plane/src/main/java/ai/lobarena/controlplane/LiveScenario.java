package ai.lobarena.controlplane;

record LiveScenario(String id, String family, String name, String agentId, long startTick, long seed) {
    long age(long tick) {
        return Math.max(0, tick - startTick);
    }

    String stage(long tick) {
        long defaultDuration = switch (family) {
            case "spoofing_like_wall" -> 3;
            case "layering_like" -> 4;
            case "quote_stuffing" -> 4;
            case "liquidity_evaporation" -> 1;
            default -> 1;
        };
        return stage(tick, defaultDuration);
    }

    String stage(long tick, long durationTicks) {
        long age = age(tick);
        if (age == 0) {
            return "armed";
        }
        return switch (family) {
            case "spoofing_like_wall" ->
                    age < durationTicks ? "wall_placed" : age < durationTicks + 2 ? "wall_cancelled" : "done";
            case "layering_like", "quote_stuffing" ->
                    age < durationTicks ? "pressure_phase" : age < durationTicks + 2 ? "cancelled" : "done";
            case "liquidity_evaporation" -> age < durationTicks ? "pressure_phase" : "done";
            default -> "done";
        };
    }
}
