# Transformer research disposition and integration plan — 8 October 2026

Tracking: [Bug #353](https://github.com/khab40/lob-arena/issues/353), under
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[settings #314](https://github.com/khab40/lob-arena/issues/314),
[backend #90](https://github.com/khab40/lob-arena/issues/90),
[GUI #91](https://github.com/khab40/lob-arena/issues/91),
[Project #3](https://github.com/users/khab40/projects/3).

## Decision and its scope

**Continue bounded Transformer research and the previously requested first demo
mock.** The current frozen training, confirmation, calibration, paired comparison
and authorized December evaluation are complete and independently verified.
This is `continue_research`; full #24 completion and production qualification
remain open. G8/G9 stay closed, with LightGBM retained as the research baseline.

Operator instruction retained verbatim on 8 October:

> any other fixes to apply? can we go ahead and continue to work on our recent plan to extend Transformer/complete this work and attach to the rest of the system?

This applies the earlier instruction to complete Transformer research before
attaching the selected detector to backend/GUI for the first mock. It authorizes
continuing that scoped engineering work. It grants no new model workload,
final-test access, spend, promotion, merge or deletion authority.

## Verified outcome and limitations

The [verified report and plots](transformer-holdout-report-20261007.md) cover
15,160 ordered rows / 135 positives. At frozen balanced operating points:

| Detector | Precision | Recall | F1 | False positives |
| --- | ---: | ---: | ---: | ---: |
| Transformer | 100% | 91.11% | 95.35% | 0 |
| Frozen LightGBM | 85.58% | 65.93% | 74.48% | 15 |

LightGBM's high-recall point catches three more positive rows with 851 false
positives. Both detect all 27 labelled campaigns. The Transformer misses nine
layering-like and three spoofing-like-wall positive rows. This supports further
research; it does not establish general market-abuse detection performance.

One date, three base sessions, synthetic attack labels and repeated variants
limit generalization. December was unseen by this frozen Transformer but had
already been evaluated by LightGBM. The three-session bootstrap is a weak
conditional summary. No thresholds or model choices changed after holdout access.
The disclosed post-hoc verifier arithmetic repair preserves original outputs.

The selected candidate remains width 128, learning rate 0.0003, seed 42, epoch 4;
temperature `0.9984971167248549`, all three thresholds `0.996423148187864`.
The [immutable settings](../../configs/releases/transformer/selected-settings-20261005.json)
bind 60 features, missingness, causal 64-step windows and train-only normalization.
Settings SHA-256: `2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab`.
Full holdout verification SHA-256:
`329158009e8de6b73ff7571acd414cab5cbcfcc760edd8963d61884349a81869`.

Recorded GPU scoring took 32.7658 seconds for 15,160 rows; this is batch timing,
not event-to-alert latency. Actual billing and online MLflow remain unreconciled.
Existing reservations stay held under the recorded operator-managed policy;
this decision neither releases them nor establishes a new budget.

## Selected-settings acceptance

#314's persistence, feature-order, artifact-integrity, normalization, calibration,
schema and immutable-publication scenarios have metadata/adversarial test evidence
from [PR #319](https://github.com/khab40/lob-arena/pull/319).
[PR #321](https://github.com/khab40/lob-arena/pull/321) added the strict CUDA consumer.
The authorized holdout verified its ordered logits against 64 saved development
reference windows before final input reads.

The [additional aggregate acceptance receipt](../evidence/transformer-settings-reference-acceptance-20261008.json)
completes the explicit probability/decision check on those same retained windows.
It applies unchanged temperature and thresholds to authenticated saved/reference
CUDA logits offline. The original logit bounds are `atol=1e-5`, `rtol=1e-6`;
the sigmoid derivative bound propagates these as
`(atol + rtol * abs(reference_logit)) / (4*T)`, with two scalar rounding ULPs.
Maximum derived probability difference is `2.7711841110722446e-7`;
all 64 rows pass their bounds and all three modes have exactly equal decisions.

This is **derived arithmetic evidence**, not a direct capture/comparison of
original-Job reference probabilities or a fresh inference run. Seven inert
boundary tests and independent agent review pass. Scripts, tests and the private
source receipts are retained in root `outputs/transformer-research-continuation-20261008/`;
only the aggregate receipt is published. Its SHA-256 is
`2c99cf477869bb42ebdc214fd66a809371429b9754debf3d03de2e3e69bc0dbb`.
No model, cloud call, final payload read or collector modification occurred.
The separate holdout one-ULP probability/eight-ULP reduction policy is unchanged.

The scoped #314 acceptance is met; closure follows this reconciliation's merge.
Real-time integration and online MLflow are explicitly outside #314's scope.
#24 stays open for its remaining MLflow lineage, dedicated serving-path and
resource/cost acceptance. No cascade is approved by this continuation decision.

## Next medium PRs

1. **Saved-score mock — #90/#91.** Load an explicitly configured private verified
   campaign, authenticate its version/size/hash receipts, and expose bounded ordered
   playback with Transformer/LightGBM selection, source identity, pause/resume/speed,
   calibrated score, frozen threshold and alert provenance. Clearly label saved
   research predictions; reject corrupt evidence and unavailable detectors.
   This needs no model run. Public aggregates cannot substitute for private rows.
   Use a separate allowlisted private store outside the generic artifact-serving
   directory, opaque IDs and local-only access. Do not put row payloads in Git,
   frontend fixtures, website assets or unauthenticated shared deployment.
2. **Research inference adapter — #24/#90.** Prepare a dedicated selected-state
   export/loader and classifier adapter, binding architecture, weights, normalizer,
   temperature and thresholds. Preserve original checkpoints and production denial;
   verify contracts with inert tests before any numerical rehearsal.
3. **Causal event integration — #90.** Reuse canonical feature processing with
   per-stream 64-row state, exact 60-feature order/missingness, timestamp-tie cutoff,
   warm-up and reset/gap behavior. Keep Python inference outside Java book mutation.
   The Arena's nine display features cannot replace the trained input contract.
4. **Bounded fresh replay rehearsal.** Prepare exact data, resources, timeout,
   Job count and spend; dry-run, review and obtain execution/access authorization
   before Nebius scoring. Measure parity, alert identity, lag and throughput.
   New packages use `RetainingReadbackStore`; frozen collectors remain unchanged.
5. **Reconcile full acceptance.** Register the same retained artifacts/lineage in
   MLflow under #19, reconcile costs, and assess #24/#90/#91 against their full
   criteria. Shared sensitive-data deployment needs #91's authentication gate.
   LOBSTER robustness and #25 hybrid results are unavailable until separately verified.

The first mock replays score/alert evidence, not an order book or newly inferred
market events. Keep the existing heuristic Arena display separate; its family
confidence meters and severity cutoffs are not calibrated model probabilities.

Use analyse → plan → applicable human approval → code → focused tests/measurement
→ separate-agent review → publication for each chunk and every correction.
