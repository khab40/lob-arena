# ARD-0036: Governed Market-Sequence Transformer Challenger

Status: Proposed

Date: 2026-08-16

## Implementation Status

Status: `[planned after ARD-0035 exit gates]`

No Transformer detector implementation is claimed by this record.

## Context

The tabular LightGBM detector observes causal rolling features but cannot learn
arbitrary temporal structure across an ordered event window. A market-sequence
Transformer may capture attack phase, cancellation choreography, refill and
liquidity response patterns that are difficult to express as fixed aggregates.

Sequence training adds material GPU cost, more leakage risk and a distinct
serving surface. Its value must therefore be measured after the cheaper
LightGBM baseline is frozen, on the same governed data and operational metrics.
This classifier is separate from the generative vLLM AI Investigator.

## Decision

After ARD-0035 exits, develop one bounded causal Transformer challenger with a
versioned sequence contract containing:

- corpus, split and source-feature hashes;
- event-time cutoff and proof that no later event is visible;
- ordered inputs, sequence length, stride, padding and attention masks;
- replay/session grouping and label horizon;
- normalization or tokenization fitted on training only; and
- deterministic row-to-sequence identity.

Use CPU Jobs for sequence materialization and evaluation. Use time-boxed GPU
Serverless AI Jobs for training and batch inference. Do not serve or train this
classifier through vLLM unless a later ARD intentionally changes it into a
compatible generative architecture.

Development covers a bounded matrix of sequence length, encoding,
architecture size, optimizer schedule, class weighting or focal loss and seed
stability. Validation selects checkpoints, calibration and operating modes.
Final test evaluation happens once after those choices are frozen.

The registered candidate contains preprocessing/tokenization, model weights,
calibration, thresholds, sequence schema, checkpoint checksum and a model card.
MLflow records learning curves, parameter count, GPU hours, peak memory,
runtime, cost and the same detector metrics used for LightGBM.

## Exit Gates

Transformer-derived features may be consumed by LightGBM only after:

1. the standalone Transformer bundle verifies from immutable inputs;
2. causal-cutoff and split-leakage tests pass;
3. standalone LightGBM and Transformer are evaluated on identical rows;
4. incremental quality is reported alongside detection delay, throughput,
   failure behavior and GPU cost; and
5. a go/no-go record approves the model as a feature producer even if it is not
   selected as a standalone champion.

## Cost And Operations

- Cap the experiment matrix before starting the GPU campaign.
- Start with the smallest architecture and shortest useful sequence.
- Use early stopping, resumable checkpoints and small smoke datasets before
  full runs.
- Prefer ephemeral Job execution; no interactive GPU endpoint is required for
  training.
- Record actual active GPU time and remaining credit after every campaign.
- Stop unused GPU endpoints immediately and delete them when fast restart is
  unnecessary because retained disks may still incur storage cost. Completed
  Jobs remove their associated VM and disk; retain governed checkpoints and
  evidence in Object Storage.

## Alternatives Considered

### Start with the Transformer before LightGBM

Rejected because the project already has a complete CPU-friendly LightGBM
boundary and needs its measured baseline to justify GPU spend.

### Use vLLM for the detector

Rejected because vLLM serves autoregressive language models, while this design
is a causal market-sequence classifier with different input, output and latency
contracts.

### Promote the Transformer on quality alone

Rejected. A surveillance candidate must also satisfy clean-window, calibration,
latency, throughput, reproducibility and cost gates.

## Consequences

The project can test richer temporal context without weakening the existing
governance boundary. Training and optional inference introduce GPU cost and
additional artifacts, but the staged gate makes that spend explicit and
reversible.

## Related Records

- [ARD-0024: Versioned Causal Feature Engineering](ARD-0024-versioned-causal-feature-engineering.md)
- [ARD-0025: Governed Corpus And ML Benchmark](ARD-0025-governed-corpus-and-ml-benchmark.md)
- [ARD-0035: Nebius-First LightGBM](ARD-0035-nebius-lightgbm-first.md)
- [ARD-0037: Transformer-To-LightGBM Cascade](ARD-0037-transformer-to-lightgbm-cascade.md)
- [Project phases](../PHASES.md)
