# Governed Corpus and ML Benchmark Protocol

This protocol is a hard gate before training or comparing a learned detector.
Its purpose is to prevent misleading performance from questionable historical
negatives, adjacent-window leakage, duplicated sessions, or row-level
uncertainty estimates.

## Versioned policy

The machine-readable policy is
[`governed-benchmark-v2-float32.json`](../configs/benchmark/governed-benchmark-v2-float32.json).
The original
[`governed-benchmark-v1.json`](../configs/benchmark/governed-benchmark-v1.json)
remains available for legacy float64 feature releases.
`backend.app.corpus.models.GovernedBenchmarkProtocol` validates it and computes
a canonical SHA-256 hash. Every corpus, split, feature run, evaluation, and
release manifest must record that protocol ID and hash.

The default minimum corpus coverage is 30 complete sessions, three instruments,
ten dates, every supported attack family, and at least three seeds per family.
Those values are a coverage floor rather than a statistical-power claim.

## Label policy

Historical data is nullable ground truth by default. The only permitted
governed states are:

- `unreviewed`;
- `candidate_clean`;
- `verified_clean`;
- `ambiguous`;
- `excluded`; and
- `synthetic_attack`.

Only `verified_clean` creates label zero. It requires two independent reviewers
who are blind to model output, complete evidence hashes, and adjudication of
conflicts. Only existing synthetic scenario execution creates
`synthetic_attack`. Other states are excluded from supervised denominators.

A verified control window may transfer to hybrid only outside the attack causal
neighbourhood and only after exact control/hybrid equivalence is proven.

Feature export represents these decisions as explicit half-open label-zero
windows. It never changes the session-wide default from null. Each feature run
records the clean-window IDs, adjudication file hash, label-specification hash,
corpus hash, protocol hash, and local artifact-verification mode. Positive
scenario windows and transferred negative windows that match the same feature
row fail closed instead of being resolved by ordering.

## Split policy

The immutable group is venue, instrument, session date, and session ID. Control
and all attack families, seeds, injection times, and duplicate imports of the
same base session stay together. Sessions are sorted chronologically into
train, validation, and test folds.

The effective purge duration is the maximum of the longest feature window,
alert matching horizon, causal tail, and label-boundary uncertainty. The
default protocol also embargoes one complete session at fold boundaries. The
test split is frozen before training and may change only in a new protocol
version.

## Authoritative inputs

Evaluation accepts canonical Java replay bundles containing versioned events,
snapshots, separate labels, alerts, replay metadata, and validation results.
Artifact hashes and replay identities must agree. UI state, mock frontend
features, and alternative simulators are not evaluation inputs.

## Statistics and metrics

The primary uncertainty unit is the base session. The default protocol uses
2,000 deterministic session-cluster bootstrap resamples and paired resampling
for model comparisons.

Required reporting includes TP, FP, FN, TN, precision, recall, F1, false alerts
per million evaluable canonical events, attack-level recall,
detection-before-benefit, detection latency, duplicate-alert load, attribution
quality, regime matrices, and worst-decile results. TN is calculated only
inside explicitly governed labeled windows.

## Streaming gate

Full-session feature generation must consume iterators or paginated Java event
cursors and write bounded Parquet row groups. Chunk sizes may change physical
layout but must not change ordered feature values, labels, quality counts, or
logical hashes. Memory growth after warm-up must be bounded by active-book and
rolling-window state rather than session length.

Generate the signed-release input evidence from a complete historical-control
replay by processing it at two different Parquet row-group sizes:

```bash
backend/.venv/bin/python scripts/benchmark_feature_streaming.py \
  --replay-manifest /secure/corpus/session/control-replay-manifest.json \
  --artifact-root /secure/corpus/artifacts \
  --corpus outputs/governed/client-corpus-v1/corpus-manifest.json \
  --protocol configs/benchmark/governed-benchmark-v2-float32.json \
  --output outputs/features/client-session-stream-primary \
  --comparison-output outputs/features/client-session-stream-comparison \
  --report outputs/governed/evidence/client-session-streaming.json
```

The resulting `feature_streaming_validation_v1` artifact records the bound
protocol and corpus hashes, base session, control replay manifest digest,
canonical Java stream hash, complete replay event count, bounded-state growth,
throughput, and logical hashes for both chunk sizes. Fixture-only benchmarks
omit `--corpus` and are explicitly not full-session release evidence.

## Release gate

Training may begin only when:

1. Coverage minimums pass.
2. All source and canonical replay hashes validate.
3. Negative labels have independent review provenance.
4. No base session crosses folds.
5. The test manifest is frozen.
6. Chunk equivalence and full-session resource tests pass.
7. Mandatory statistical and operational reports pass.
8. The corpus, split, and benchmark release bundle is signed.

## Commands

Run every governed unit and end-to-end check:

```bash
make governed-test
```

Build a corpus bundle after preparing session registrations and independent
adjudication JSONL:

```bash
GOVERNED_SESSIONS=/secure/corpus/sessions.json \
GOVERNED_ADJUDICATIONS=/secure/corpus/adjudications.jsonl \
GOVERNED_ARTIFACT_ROOT=/secure/corpus/artifacts \
GOVERNED_CORPUS_ID=client-corpus-v1 \
GOVERNED_CORPUS_OUTPUT=outputs/governed/client-corpus-v1 \
make build-governed-corpus
```

The command fails when the production coverage floor is not met. A provisional
failing bundle can be written only through the direct CLI's explicit
`--allow-incomplete` option and is not training-eligible.

Export locally verified negative labels into a canonical replay feature run:

```bash
backend/.venv/bin/python scripts/generate_features.py \
  --replay-manifest /secure/corpus/session/replay-manifest.json \
  --clean-adjudications /secure/corpus/adjudications.jsonl \
  --corpus-manifest outputs/governed/client-corpus-v1/corpus-manifest.json \
  --benchmark-protocol configs/benchmark/governed-benchmark-v2-float32.json \
  --config configs/features/lightgbm-v2.json \
  --artifact-root /secure/corpus/artifacts \
  --output outputs/features/client-session
```

All four governed inputs are mandatory together. Metadata-only validation is
not accepted for this path.

Freeze a chronological split:

```bash
GOVERNED_CORPUS_MANIFEST=outputs/governed/client-corpus-v1/corpus-manifest.json \
GOVERNED_SPLIT_ID=client-split-v1 \
GOVERNED_SPLIT_OUTPUT=outputs/governed/client-split-v1.json \
make generate-governed-split
```

Evaluate canonical Java replay bundles and sign the result:

```bash
GOVERNED_EVALUATION_PLAN=/secure/corpus/test-evaluation-plan.json \
GOVERNED_CORPUS_MANIFEST=outputs/governed/client-corpus-v1/corpus-manifest.json \
GOVERNED_CORPUS_VALIDATION=outputs/governed/client-corpus-v1/corpus-validation.json \
GOVERNED_SPLIT_MANIFEST=outputs/governed/client-split-v1.json \
GOVERNED_BENCHMARK_OUTPUT=outputs/governed/releases/model-v1-test \
GOVERNED_SIGNING_KEY=/secure/keys/benchmark-ed25519.pem \
GOVERNED_SIGNER="Market Surveillance QA" \
make evaluate-governed-benchmark
```

Verify the detached Ed25519 signature and every artifact digest:

```bash
GOVERNED_BENCHMARK_OUTPUT=outputs/governed/releases/model-v1-test \
make verify-governed-release
```

The evaluation plan lists every base session in exactly one frozen fold,
exactly one historical-control replay, and exactly one hybrid replay for every
registered campaign. It also names training-only regime-fit evidence, one
full-session streaming-evidence artifact per evaluated session, and baseline
session metrics for paired comparisons. Missing or duplicate replays, omitted
campaigns, mismatched Java hashes, unverified negatives, unbound regime or
streaming evidence, absent realized-benefit timestamps, and unsigned
production releases fail closed.

See [ARD-0025](architecture/ARD-0025-governed-corpus-and-ml-benchmark.md) for
the architecture decision.
