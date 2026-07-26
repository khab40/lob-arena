# Benchmark Methodology

> Learned-model training and comparison must follow the stricter
> [Governed Corpus and ML Benchmark Protocol](governed-corpus-benchmark-protocol.md).
> The synthetic tournament below remains the deterministic detector smoke and
> regression benchmark; it is not by itself a governed ML evaluation corpus.

The benchmark path evaluates detector behavior on labeled synthetic simulations.

## Scenario Families

- Spoofing-like: large visible orders are placed away from the touch and canceled after influencing book pressure.
- Layering-like: multiple same-side levels create persistent apparent pressure before cancellation.
- Quote Stuffing Burst: high-frequency order and cancel bursts stress event-rate features.
- Liquidity shock: depth evaporates quickly, widening spreads and reducing executable liquidity.

## Metrics

- Precision: detected incidents that correspond to injected labels.
- Recall: injected labels that were detected.
- F1: harmonic mean of precision and recall.
- False positives: detector alerts outside labeled windows.
- False negatives: injected labels without matching detector alerts.

## Reporting

Each benchmark run should persist:

- raw events and snapshots
- injected scenario labels
- detector outputs
- aggregate metrics
- per-scenario observations
- charts suitable for challenge submission material
