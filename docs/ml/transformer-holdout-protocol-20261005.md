# Fixed-candidate December holdout protocol

Historical plan/execution record; reconciled 8 October 2026. The fixed protocol was later executed once under separate exact approval and independently verified.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

Date: 2026-10-05. Original planning status: implementation approved; execution not yet authorized at that date.
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Story #314](https://github.com/khab40/lob-arena/issues/314),
[Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).

As a researcher,
I want the fixed Transformer evaluated on later-date governed Nasdaq sequences,
So that I can assess temporal holdout performance before investing in serving or a cascade.

Actor: researcher; validation engineer independently verifies results.
Goal: assess the development advantage on the same later-date rows as LightGBM.
Out of scope: acquisition, relabeling, resplitting, training, recalibration,
threshold/seed selection, cascade, live serving, promotion and a G8 rerun.
Verification: local inert tests; later one exactly authorized Nebius GPU Job;
independent saved-artifact verification without running weights locally.

## Freeze before access

The [protocol configuration](../../configs/experiments/transformer/c4-holdout-20261005.json)
binds the [selected research settings](transformer-settings-release.md).
Width 128 / rate 0.0003 / seed 42 / epoch 4, original checkpoint, all 60 features,
64-step windows, train-only normalization, C-only temperature and O thresholds
remain fixed. Primary operating mode is balanced; other named modes and 0.5
diagnostics are predeclared. No choice is made using December outcomes.
The protocol-lock regression compares every duplicated candidate field (width,
learning rate, seed, epoch and checkpoint checksum) with the immutable settings.
[Bug #320](https://github.com/khab40/lob-arena/issues/320) closes the missing
width/rate/seed assertions; isolated mutations of those fields must fail.

Use prepared C4 **2019-12-30 AAPL/MSFT/NVDA, 10:00–10:30 ET**. Existing G8
evidence expects 15,160 retained rows, 135 positives, 15,025 research-control
negatives, 27 observed campaigns, three base sessions and 30 replay domains.
These are expected counts, not a newly verified final inventory. The next package
must authenticate exact keys, versions, sequence/tabular identities, labels and
saved G8 baseline predictions before results can be accepted.

December was excluded from Transformer train/S/C/O. Preflight must confirm this
against every consumed inventory. LightGBM already evaluated December in G8,
and its results are known: this is a holdout for the fixed Transformer, **not a
globally untouched or blind benchmark**. Labels remain synthetic attacks and
unadjudicated controls. One date cannot establish market-wide generalization.

Use original saved G8 LightGBM prediction bytes and frozen calibration/thresholds.
Do not rescore LightGBM, invoke the G8 runner or compare different row populations.
Preserve the development denial of final reads; implement a distinct authorized
holdout consumer. Separate old checkpoint provenance from new execution bindings.

## Reports and research decision

Primary comparisons are paired average precision and log loss. Report balanced
precision/recall/F1/confusion, Brier/ECE, all fixed modes, per-symbol/family support
and recall, negative-row false positives and observed-campaign coverage. Undefined
metrics remain null with an explanation; do not silently omit unsupported groups.
False-positive rates use retained observations, never the canonical event denominator.

Use 2,000 paired whole-base-session bootstrap draws, seed 20260828, preserving
all replay/seed variants within their source session. Three clusters on one date
make intervals weak conditional summaries; do not claim statistical independence
or population significance from them. No row-level resampling.

Retain the existing 0.90 precision floor for high_precision and 0.90 recall floor
for high_recall as research gates. Report balanced trade-offs and quality deltas;
passing floors alone is insufficient for promotion. Retain a verified poor result.
A lineage/execution failure is inconclusive. The operator decides continue,
repair/development rescoping or stop; no automatic tuning or replacement follows.

Save logits/probabilities, unchanged labels, exact row ledger, baseline references,
versioned artifacts/events and SUCCESS last. Independently recompute saved metrics.
One Markdown report carries PR, reliability, confusion and family plots; no new
epoch curves are expected because this study has no training. Measure Transformer
batch inference, GPU memory, transfers and runtime. Saved baseline predictions
cannot establish LightGBM latency or a speedup. Reconcile MLflow later under #19.

## Execution gate and next chunks

1. **5–6 October:** settings/protocol chunk, local metadata checks and review.
2. **6–7 October:** separate holdout adapter, request, worker, publisher and reader;
   exact row/cutoff/mask/reset tests and bounded development-reference parity.
3. **7–8 October:** digest image, dependency/context checks, exact dry-run and
   combined final-access/run/spend proposal. Review IAM/removal if necessary.
4. **After exact approval:** one inference-only L40S Job; reference parity passes
   before December payload access; then score all approved targets once.
5. **8–10 October:** independently verify/report, operator decision and later
   MLflow reconciliation. Dates are targets conditional on review and capacity.

Proposed bounds: one non-preemptible L40S / 8 vCPU / 32 GiB / 100 GiB, batch 64,
one hour execution, 600-second continuous startup/image-pull limit, two hours
create-to-terminal, concurrency one, restart never. Proposed additional cap is
**$6.25 excluding VAT**, not approved yet. Bound publication to 2 GiB,
collection/egress to 16 GiB and requests to 10,000; review retention after 90 days.
Admission must show a complete scoped estimate below the cap. Prior commitments
remain held. Read-only retries: 30-second initial call, then up to 60/90/120 seconds
inside the enclosing deadline; mutation retries zero, no automatic replacement.
Exact keys/versions, authority, output identity and cleanup handoffs remain pending.

```gherkin
Feature: Fixed-candidate later-date Nasdaq validation
  Scenario: Keep candidate choices unchanged
    Given a verified settings release and a predeclared protocol
    When the authorized holdout evaluation begins
    Then weights, normalization, calibration and thresholds remain unchanged

  Scenario: Reject an incomplete paired population
    Given saved LightGBM predictions and approved December targets
    When an identity or label is duplicated, missing or different
    Then no comparison result is accepted

  Scenario: Retain a disappointing verified result
    Given a completed authorized evaluation with poor quality
    When its report is published
    Then its metrics and limitations remain available
    And no fitting or replacement evaluation starts automatically
```

G8/G9 remain closed under [#23](https://github.com/khab40/lob-arena/issues/23).
[#25](https://github.com/khab40/lob-arena/issues/25) remains Todo; a cascade requires
a separately justified scope. This protocol is not execution or final-access authority.
