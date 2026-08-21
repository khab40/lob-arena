# ARD-0037: Transformer-Derived Features Into LightGBM

Status: Proposed

Date: 2026-08-16

## Implementation Status

Status: `[planned after ARD-0036 exit gates]`

No cascade implementation or performance benefit is claimed by this record.

## Context

A standalone Transformer can model temporal context but is more expensive to
train and serve than LightGBM. A late ensemble combines final decisions but
does not let the tabular model learn conditional interactions between temporal
state and microstructure features.

The requested combined direction is Transformer to LightGBM: use the governed
Transformer as a causal feature producer, then let a new LightGBM candidate
combine its outputs with `lob_features_v2`. This can retain a fast CPU decision
layer, but only if feature generation, freshness and fallback costs are
acceptable.

## Decision

Create an immutable `transformer_feature_release_v1` before training the
cascade. Each release binds:

- source corpus, split and replay identities;
- source Transformer model, checkpoint and sequence-contract hashes;
- prediction timestamp and causal event cutoff;
- ordered embedding/score columns, dtype, shape and null policy;
- row count, row identity and content checksum; and
- feature-generation Job ID, image digest, runtime and cost evidence.

Join Transformer-derived features to `lob_features_v2` only by governed row,
session and replay identities. Positional or timestamp-nearest joins are not
allowed. Labels, post-cutoff events and final-test feedback cannot enter the
feature producer.

Train the cascade as a new model family. It must not overwrite the standalone
LightGBM v1 artifacts or registry identities. The Wave 1 LightGBM bundle remains
the required rollback and missing-feature fallback.

The governed comparison includes at least:

- deterministic rules;
- tabular-only LightGBM;
- standalone Transformer;
- Transformer-to-LightGBM cascade; and
- a simple late-fusion comparator when useful for interpreting whether learned
  feature interaction adds value.

All candidates use identical immutable evaluation rows. Promotion gates cover
per-family quality, PR-AUC, clean-window false alerts, calibration, detection
delay, CPU/GPU throughput, cost, feature staleness, missing-feature behavior and
artifact verification.

## Serving Modes

Two modes may be evaluated without preselecting one:

1. **Offline/batch enrichment:** generate Transformer features for a bounded
   corpus or completed incident, then score the joined rows with LightGBM on
   CPU. This is the default cost-oriented mode.
2. **Bounded online enrichment:** serve Transformer features through a dedicated
   classifier endpoint and pass compatible outputs to LightGBM. This mode is
   accepted only if latency and active-GPU cost justify it.

If Transformer features are absent, stale, checksum-invalid or schema-invalid,
the system fails closed to the verified tabular LightGBM path and records the
fallback. It must not silently impute an apparently valid temporal signal.

## Exit Gates

The cascade is promoted only when:

1. feature release and join integrity verify independently;
2. ablation demonstrates incremental value beyond both standalone models;
3. improvements clear predeclared confidence intervals and operational gates;
4. active GPU cost and end-to-end latency fit the declared serving mode; and
5. candidate, champion and rollback pointers are changed through a signed,
   auditable promotion record.

If the gates fail, the negative result is retained and standalone LightGBM
remains the champion or rollback candidate.

## Alternatives Considered

### Average the two model probabilities only

Retained as a comparison, not the target architecture. It is simpler but cannot
learn interactions between sequence state and tabular microstructure.

### Feed LightGBM outputs into the Transformer

Deferred. It makes the expensive model the final serving dependency and does
not match the intended Transformer-to-LightGBM direction.

### Recompute Transformer features synchronously for every market tick

Rejected as the default because it couples detector availability and cost to a
GPU path before the value and latency are established.

## Consequences

The cascade can concentrate GPU work in training and bounded feature
generation while preserving a CPU-efficient decision layer. In exchange, the
project gains a second governed feature release, more lineage, staleness rules
and a fallback contract. Its value remains an empirical question rather than an
assumed architectural benefit.

## Related Records

- [ARD-0024: Versioned Causal Feature Engineering](ARD-0024-versioned-causal-feature-engineering.md)
- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0031: Complete Governed LightGBM v1](ARD-0031-complete-lightgbm-v1.md)
- [ARD-0035: Nebius-First LightGBM](ARD-0035-nebius-lightgbm-first.md)
- [ARD-0036: Market-Sequence Transformer](ARD-0036-market-sequence-transformer.md)
- [Project phases](../PHASES.md)
