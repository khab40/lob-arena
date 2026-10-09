# Current Transformer implementation

Code architecture inspected on 2026-10-03; execution status reconciled on 2026-10-08. [Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance. Related work: [Transformer ticket #24](https://github.com/khab40/lob-arena/issues/24), tracked in [GitHub Project #3](https://github.com/users/khab40/projects/3).

The implementation is a **custom, small PyTorch Transformer neural network**, trained from scratch to predict **whether an attack is active at the current market observation**. It does not use an LLM, GPT, Llama, a tokenizer, or pretrained language-model weights.

## Input preparation

Each prediction uses the latest **64 feature rows**, including the current observation. Each row contains **60 numeric market features**. These are observations, not necessarily 64 seconds.

- [pipeline.py](../../backend/app/features/pipeline.py) defines and computes the features in `FEATURE_COLUMNS`.
- [windows.py](../../backend/app/ml/transformer/windows.py) verifies that each window contains the exact causal history from its source replay. Short histories are padded on the left.
- [normalization.py](../../backend/app/ml/transformer/normalization.py) fits feature means and standard deviations using training rows only. Each training target contributes once; overlapping history and padding receive no extra weight. Zero standard deviations are replaced with one.
- [batches.py](../../backend/app/ml/transformer/batches.py) applies `(value - mean) / scale`, replaces missing values with zero, and creates separate missingness and padding masks.

For each row, the network concatenates **60 normalized values and 60 missingness indicators**, producing 120 input numbers.

## Neural-network algorithm

The entire network is in [research_model.py](../../backend/app/ml/transformer/research_model.py), principally `CausalBlock` and `SequenceClassifier`.

```text
64 × 60 normalized features + missingness indicators
    → 64 × 120 inputs
    → learned linear projection to width 64 or 128
    → add fixed sinusoidal positional encoding
    → two causal Transformer blocks
    → final LayerNorm
    → take the last valid row's representation
    → linear layer producing one logit
    → sigmoid(logit / temperature) producing attack probability
```

Each Transformer block performs:

1. Layer normalization.
2. **Four-head self-attention**, with a causal mask: a row can attend only to itself and earlier valid rows.
3. A residual connection with dropout.
4. Another layer normalization.
5. A feed-forward network: `width → 4 × width → width`, using **GELU** and dropout.
6. Another residual connection.

Dropout is **0.1**. Padding is excluded from valid attention and its representations are zeroed. Discarded padded queries receive a finite self-attention key to avoid invalid numerical outputs; valid queries cannot attend to padding.

Attention learns which earlier observations matter for interpreting the current observation. The output is one binary classification score. There are no separate attack-family output classes.

The positional encoding represents **row position**. Timestamps are checked during input preparation, but the model's `forward()` receives values and masks, not timestamps directly.

## Training and model selection

The optimizer loop is in [research_training.py](../../backend/app/ml/transformer/research_training.py). Numerical policy and configuration selection are in [research_policy.py](../../backend/app/ml/transformer/research_policy.py).

| Setting | Current implementation |
|---|---|
| Target | Binary `attack_active` label |
| Loss | Binary cross-entropy with logits |
| Weighting | Equal class mass, then equal base-session mass within each class; mean weight one |
| Optimizer | AdamW, weight decay `0.01`, betas `(0.9, 0.999)`, epsilon `1e-8` |
| Batch size | 64 |
| Maximum epochs | 30 |
| Learning-rate schedule | 5% warmup, then cosine decay to 10% of initial rate |
| Gradient clipping | Norm limit `1.0` |
| Precision | Float32; TF32 disabled |
| Reproducibility | Seeded epoch shuffle and deterministic PyTorch algorithms |
| Early stopping | Five epochs without selection-loss improvement of more than `1e-6` |

There are **four fixed search configurations**: widths `{64, 128}` multiplied by learning rates `{0.0003, 0.001}`, initially using seed `42`.

The best epoch and configuration are selected by **unweighted selection log loss**. Epoch ties retain the earlier checkpoint; configuration ties use parameter count and configuration hash. All four trials must be independently verified before selecting a winner.

The winning configuration is then checked with seeds `7` and `2027`; seed `42` remains the candidate. Across the three seeds, both selection-log-loss range and F1-at-0.5 range must be at most `0.05`. This is a bounded search.

## Calibration and comparison

[research_inputs.py](../../backend/app/ml/transformer/research_inputs.py) authenticates the input package and materializes four separate data roles:

| Role | Purpose |
|---|---|
| Training | Update network weights |
| Selection | Choose checkpoint and configuration |
| Calibration | Fit the probability temperature |
| Operating point | Choose thresholds and compare with frozen LightGBM |

[research_evaluation.py](../../backend/app/ml/transformer/research_evaluation.py) fits a single temperature `T` by minimizing unweighted calibration log loss. It uses golden-section minimization bounded to `0.05–20`, with at most 200 objective evaluations and tolerance `1e-6`.

```text
P(attack active) = sigmoid(logit / T)
```

The comparison requires exact matching ordered target IDs and labels against saved, frozen LightGBM predictions. It reports precision, recall, F1, log loss, average precision, Brier score, and calibration error. Operating-point selection uses the existing LightGBM rules with precision and recall floors of `0.9`; an unattainable floor blocks freezing. Calibration also blocks freezing if both Brier score and calibration error worsen beyond the configured tolerance.

The current execution compares Transformer and LightGBM separately. It does not feed Transformer embeddings into LightGBM or execute a combined cascade.

These are development comparisons. Thresholds are selected on the reported operating-point role; the results are not an independent final evaluation. Final-test access and production promotion remain separate gates.

## Execution

This is an **offline research workload on Nebius Serverless GPU Jobs**.

| File | Responsibility |
|---|---|
| [transformer_research_operator.py](../../scripts/transformer_research_operator.py) | Prepare requests, check prerequisites, attest Job identity, and independently collect results; it does not create Jobs |
| [research_execution_spec.py](../../backend/app/ml/transformer/research_execution_spec.py) | Define eight slots, dependencies, immutable image reference, resources, and timeouts |
| [Dockerfile](../../serverless/transformer_research/Dockerfile) | Package code, dependencies, input proofs, and frozen baseline |
| [research_worker.py](../../backend/app/ml/transformer/research_worker.py) | Container entry point: verify request/context, download and audit inputs, run the slot, and publish evidence |
| [research_run.py](../../backend/app/ml/transformer/research_run.py) | Dispatch smoke, training, confirmation, or inference/calibration/comparison |
| [research_smoke.py](../../backend/app/ml/transformer/research_smoke.py) | Check causal masking, padding, missingness, gradients, and checkpoint resume |
| [research_checkpoint.py](../../backend/app/ml/transformer/research_checkpoint.py) | Save and restore model, optimizer, progress, and execution bindings |
| [research_storage.py](../../backend/app/ml/transformer/research_storage.py) | Publish durable versioned execution artifacts |
| [research_readback.py](../../backend/app/ml/transformer/research_readback.py) | Independently verify published execution evidence |

The container starts with:

```bash
python -m app.ml.transformer.research_worker \
  /opt/research/request.json /job/research
```

The execution sequence is:

```text
Smoke → four search trials → two confirmation trials → inference/comparison
```

The smoke slot includes synthetic behavior checks and two training epochs over 1,024 selected real training rows. Each later slot requires verified receipts for its prerequisites.

The GPU preset is **one L40S, 8 vCPUs, 32 GB RAM**, with concurrency one. Smoke and inference slots have one-hour limits; training slots have two-hour limits. The planned campaign is bounded to eight GPU Jobs and 14 GPU hours. Each Job reserves 600 seconds for durable publication. Automatic replacement and restart are disabled.

The image reference is immutable and digest-pinned. The repository portion must be at most 64 characters; repository and digest metadata are kept separate. Training requires CUDA and rejects a CPU fallback.

Checkpoints and results are retained in versioned object storage with source-commit and image-digest bindings. Online MLflow is optional; later reconciliation is required. The worker's successful exit remains subject to independent artifact verification.

The detailed settings are in [c4-campaign-20260928.json](../../configs/experiments/transformer/c4-campaign-20260928.json), with execution resolutions in [research-fork-20261002.json](../../configs/experiments/transformer/research-fork-20261002.json). The latter is a protocol/package configuration, not an authorization to submit every Job.

## Recorded execution status

The repository's [October 3 smoke-status snapshot](../evidence/transformer-research-smoke-status-20261003.json) records Job `aijob-e00qpnac5v335pddbn` failing at startup with `PublicationUncertain`, **before model execution**. That snapshot contains no Transformer quality result.

This document reflects inspected code and retained repository evidence. Live Nebius state was not queried when preparing it. The neural network and research execution path are implemented, but the recorded attempt does not establish successful training, improved detection quality, or production deployment.
