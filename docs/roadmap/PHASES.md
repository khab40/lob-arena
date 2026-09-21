# Project phases

[Current status](CURRENT_STATUS.md) owns dated progress; [main roadmap](ROADMAP-MAIN.md)
owns milestone dates. This document owns forward feature scope and acceptance.

## Completed demo foundation

The initial phases delivered the live arena, remote agents, liquidity invariant,
rules/incidents, Nebius endpoint/job integration, experiment manager and challenge
evidence. Java superseded the original Python live-runtime ownership.
Detailed completed checklists remain in the
[pre-compaction revision](https://github.com/khab40/lob-arena/blob/63fe41d277732875628d0e72449a1f8e992ae07b/docs/roadmap/PHASES.md).
For today's boundaries see [architecture](../architecture.md); historical
challenge results are linked from the [submission index](../publication/challenge-submission.md).

## Retained demo follow-ups

These are historical follow-ups, not a current backlog; revalidate them against
[current status](CURRENT_STATUS.md) and the original dated record before acting.

- **Phase 3B: Baseline Liquidity And Quote Ownership:** `[todo]` browser controls for ladder and quote-cap tuning.
- **Phase 3B: Baseline Liquidity And Quote Ownership:** `[todo]` dynamic reference-price model for drifting market regimes.
- **Phase 4: Nebius Benchmark And Explanation Runtime:** `[partial]` Four sanitized runtime/UI screenshots are committed under
  `assets/screenshots/`; dedicated real Nebius console log/metric screenshots
  are still needed for the remaining review-evidence gap.
- **Phase 4: Nebius Benchmark And Explanation Runtime:** `[partial]` Deployment documentation includes commands; real Nebius logs/metrics screenshots are still needed for final review.
- **Phase 5: Polish And Submission Assets:** `[partial]` architecture diagrams exist in Mermaid docs; standalone assets under `assets/diagrams/` are still optional/future work.
- **Phase 5: Polish And Submission Assets:** `[partial]` demo narration scripts and captions under `assets/demo-video/`; rendered demo video is still missing.
- **Future work:** `[partial]` The project includes research notes, a blog draft, GitHub banner, UI controls, demo narration, sanitized screenshots, and committed benchmark evidence; the rendered video and published article URL remain publication work.

Additional retained future scope from the demo plan:

- Durable backend organization/workspace, case assignment, and audit-log persistence APIs.
- Formal benchmark artifact schema versioning and advanced Judge Mode timeline selectors.
- Richer multi-user workflows and additional scenario families.

## Active Roadmap: Full Learned-Detector E2E Demonstration

Status: `[in progress]`

Roadmap decision date: 2026-08-16

Status reconciliation date: 2026-08-27

### Commercial North Star And Deliberate Parking Decision

The commercial product thesis is **BYO data + BYO detector adapter**:

1. a customer brings historical or live market data;
2. an inbound adapter maps it into the canonical governed dataset contract;
3. LOB Arena trains its LightGBM, Transformer and hybrid reference detectors
   offline;
4. the customer brings a detector adapter as the system under test;
5. the platform first certifies it on immutable replay and hybrid ground truth;
6. a later real-time shadow mode compares it with the frozen reference
   detectors without allowing any detector to mutate the exchange; and
7. LOB Arena publishes comparable quality, false-alert, delay, latency,
   availability, drift, disagreement and evidence reports.

This is the intended commercial direction, but Features #87 and #88 are
deliberately `[parked]` for the current milestone. Nasdaq ITCH and LOBSTER are
the first-party reference data adapters, LightGBM is the first reference
comparator, and the planned Transformer/hybrid paths must remain compatible
with the future adapter contract. The customer's detector will be the system
under test when this commercial track resumes.

### Current Milestone

Deliver **one complete, reproducible and CEO-demoable E2E flow** before
commercial adapter productization:

```text
approved Nasdaq samples + repository LOBSTER sample
  -> selective acquisition / validation / normalization
  -> control + deterministic hybrid replay
  -> one governed corpus, split and model projections
  -> LightGBM baseline
  -> standalone market-sequence Transformer
  -> Transformer-to-LightGBM hybrid
  -> identical-row comparison + LOBSTER robustness challenge
  -> one verified evidence package
  -> secure CEO-facing UI and narrative (after the backend flow works)
```

Nasdaq is the primary train/validation/final-test research benchmark. LOBSTER
is a separately reported cross-source robustness challenge after candidate
selection; it is not silently pooled into training or used for retuning. A
single campaign/release identity must connect source manifests, replay domains,
model inputs, model bundles, comparison rows, metrics, cost and the final demo
report.

Use the dated [roadmap snapshot](CURRENT_STATUS.md) for live issue status.
Older board counts are superseded; epics, features and stories overlap and
are not additive engineering progress. The active
detector sequence is GitHub Feature #16: Wave 1 / Story #23 is in progress;
Wave 2 / Story #24, Wave 3 / Story #25, integrated evidence / Story #90 and
secure demo UI / Story #91 remain Todo. No Transformer or
Transformer-to-LightGBM implementation is claimed yet.

The active learned-detector work is deliberately sequential. Governed LightGBM
v1 is already implemented locally, so the first wave is not a second LightGBM
implementation. It is the production-shaped Nebius qualification of the
existing release boundary. Transformer work starts only after that baseline is
measured and frozen. The combined design then uses causal Transformer outputs
as additional LightGBM inputs so GPU-heavy sequence learning can improve a
CPU-efficient serving path. UI simplification begins only after the complete
model/data/evidence path can be run without manual artifact repair.

### Shared Data Foundation: Selective Nasdaq To Nebius S3

The [four-date data flow](../data/nasdaq-public-sample-v1-data-flow.md) owns
the delivered source, normalization and projection path. Current completion
evidence is in [status](CURRENT_STATUS.md); the original seven-date proposal,
amendments and execution gates remain in the
[public-data history](../archive/nebius-public-market-data-lightgbm-plan.md).
Do not interpret its old task counts or Job budget as new execution authority.

### Execution Order And Gates

| Wave | Status | Primary Nebius resource | Outcome | Exit gate before next wave |
| --- | --- | --- | --- | --- |
| 1. Nebius LightGBM baseline | `[in progress]` | CPU Serverless AI Jobs, Standard Object Storage, shared MLflow | Train, calibrate, evaluate and package governed LightGBM v1 on immutable cloud inputs; publish runtime, throughput and cost evidence | Reproducible bundle verifies; declared quality/latency gates pass; cost per million scored rows is measured; no frozen-test reruns for tuning |
| 2. Market-sequence Transformer | `[todo]` | Time-boxed GPU Serverless AI Jobs with CPU preprocessing/evaluation | Train and calibrate a causal sequence challenger on the same split and label contracts | Standalone Transformer bundle verifies; GPU hours/cost and inference latency are recorded; comparison with Wave 1 uses identical evaluation rows |
| 3. Transformer to LightGBM cascade | `[todo]` | Ephemeral GPU batch feature extraction followed by CPU Serverless AI Jobs | Materialize versioned causal Transformer embeddings/scores and train LightGBM with those features plus the existing tabular set | Ablation proves or rejects incremental value; serving-cost and failure-mode gates pass; champion/rollback decision is signed |
| 4. Integrated E2E evidence flow | `[todo; GitHub Story #90]` | Existing CPU/GPU Jobs, Object Storage and MLflow | Run one campaign from Nasdaq/LOBSTER source manifests through all three detector paths and one comparison/evidence package | One command or bounded orchestration path verifies every identity, metric, artifact and cost record without manual repair |
| 5. Secure CEO demo UI | `[todo after Wave 4; GitHub Story #91]` | Existing React/FastAPI/Java surfaces plus selectively restored Google Auth | Deliver Sign in → Data → Replay → Experiments → Management Summary from verified campaign artifacts | A non-technical reviewer can run or replay the demo, explain the outcome and limitations, and cannot access sensitive shared data without backend authorization |

### Wave 1: Qualify LightGBM On Nebius First

Goal: establish the cheapest, fastest learned-detector baseline before paying
for sequence-model development.

Planned work:

- `[done]` Establish the Wave 1 project, budget controls, four governed bucket
  boundaries, three least-privilege identities, development-to-final denial
  proof, Container Registry path, and shared MLflow stack.
- `[done]` Replace the failed S3 filesystem-mount design with the July-proven
  pattern: MysteryBox environment credentials plus prefix-scoped S3 API
  download/upload through ephemeral job disk.
- `[done]` Close G4. Two mount-based Jobs stalled before container start;
  three no-volume Jobs failed on an old image or incorrect entrypoint; attempt
  6 reached the runner but failed before training on an AWS CLI v1/v2 pager
  incompatibility. Attempt 7 then completed the governed workload, matched the
  reviewed resources and image identity, and published 25 result objects plus
  `SUCCESS`. Seven of the 20 development-job slots are consumed and 13 remain.
  Spend was reconciled at USD 8.57 including VAT; all 16 gates passed, MLflow
  is stopped and G5 is unlocked. No rerun is authorized or needed.
- `[done]` Complete C0–C4: governed four-date corpus/split and fold-isolated
  tabular/sequence projections, including C4 lineage and data boundaries.
- `[done]` Complete G5 deterministic repeats and G6 validation-only tuning and
  calibration. Freeze the selected candidate in G7; development usage is 20/20.
- `[done for rehearsal]` Verify native scored-payload recovery, authenticated
  MLflow round trips and independent S3 readback. These prove recovery mechanics,
  not original Java comparison evidence or final model quality.
- `[in progress]` Complete the production package, verify original comparison
  and lineage inputs, and run the separately authorized G8 replacement once.
- `[todo]` Publish independently verified final C4 comparison/calibration and
  resource/throughput evidence under the contract's explicit research limitations.
- `[blocked on G8]` Record G9's signed quality/resource/cost disposition and
  verified model baseline. Promotion is not automatic from a successful Job.

Why this is first:

- LightGBM training and inference are CPU-friendly and already implemented.
- Serverless Jobs terminate when work completes, avoiding idle VM cost while
  preserving container, log and resource evidence.
- Standard Object Storage is the low-cost durable boundary; enhanced-throughput
  storage is deferred until measured I/O shows that it is needed.
- The resulting quality, latency and cost baseline determines whether a
  Transformer is worth its additional complexity and GPU spend.

Wave 1 exit criteria:

- Three identical repeat runs produce matching governed identities and
  equivalent metrics within declared tolerances.
- Preserve the frozen operating modes and R4 test-access history; any replacement
  final evaluation requires its own package-bound approval.
- Cloud artifacts include job ID, image digest, Git SHA, input hashes,
  checksums, resource shape, timestamps, measured throughput and estimated
  cost.
- Performance claims remain scoped to synthetic/fixture or separately governed
  licensed data, as applicable.

#### G8 Recovery And Completion Plan

See the [current roadmap snapshot](CURRENT_STATUS.md) for milestone dependencies
and the source revision used by this documentation review.

Status reconciled on 2026-09-21 against merged PRs #200, #201 and #207:
`[G0-G7 complete; G8 open; G9 blocked]`. The goal is one separately authorized
final evaluation of the frozen LightGBM candidate on the governed C4 release,
with independently verified comparison, quality, lineage and execution evidence.
G9 then records the signed baseline/exit decision before Transformer work.

R4 (`nasdaq-g8-final-r4-20260913`, Job `aijob-e00vtamgkr07mwzt4t`) downloaded
the final release but failed before scoring. Preserve its consumed approval and
four prior submissions. The candidate, calibration, features and thresholds remain
frozen; no replacement authorization follows from this plan.

Completed engineering evidence:

- Corrected C4 loading, original-format comparison and MLflow report integration;
  scored-payload retention before logging, same-run recovery and marker-last
  publication are implemented.
- The [native recovery rehearsal](../evidence/g8-native-recovery-20260917.json)
  scored once, deliberately failed, and recovered after Job/workspace loss.
  Independent authenticated MLflow readback verified 24 metrics, 30 dataset
  inputs and four artifact hashes. The later [independent S3 readback](../evidence/g8-independent-s3-readback-20260917.json)
  verified all 64 objects and closes the earlier AccessDenied verification gap.
- Merged PR #201 adds the native production bootstrap and v3 replacement binding.
  The [production review package](../operations/g8/g8-production-package.md) for
  `nasdaq-g8-replacement-r5-20260917` is prepared but unsigned and not executable.
  Synthetic comparison/lineage fixtures and transport checks do not establish
  production model quality or execution of the changed production entrypoint.

Completion evidence and remaining work, in order:

1. **Verify original comparison and lineage evidence.** Locate and verify all
   27 original Java/C3 checkpoints, their preparation binding and 30 replay domains;
   verify genuine C4 dataset registration. Complete the frozen projection,
   profile, comparison inventory and input-location metadata. Use retained metadata
   first; preserve the separate gate for protected final-data access. Missing
   original evidence is a blocker, not permission to regenerate rules or use fixtures.
   September 21: the approved [metadata audit](../evidence/g8-original-comparison-metadata-20260921.json)
   verified all 27 checkpoint inventories, 30 replay domains and the frozen projection.
   All 89 metadata reads passed; temporary permissions were removed and denial
   reverified. Metadata bindings are prepared. The [live C4 registration](../evidence/g8-capacity-registration-20260921.json)
   now verifies four metadata artifacts and all 30 final-tabular lineage entries;
   [Original payload verification](../evidence/g8-original-payload-verification-20260921.json)
   is now complete: 294 objects / 2,632,277,460 bytes staged and all 377 payload/metadata
   files independently rehashed. All 37 temporary grants were removed; the original
   policy is restored and access denied again. The VM is stopped. Payload rows were
   not parsed in that byte audit. The later approved semantic Job
   `aijob-e00ezdakxbj7m0xxfy` [failed with ValidationError](../evidence/g8-comparison-semantics-20260921.json).
   The local comparison metadata lacks required `preparation.logical_name`; the
   redacted log cannot establish the exact failure stage or completed parsing.
   Original evidence is preserved; the [retry proposal](../evidence/g8-comparison-semantics-retry-proposal-20260921.json)
   adds only that field in a new tree, rebinds its inventory and adds safe diagnostics.
   One-Job approval was consumed; no retry has run. Semantics remain unverified.
2. **Verify the production transport on Nebius.** Exercise the actual bootstrap,
   imports, mount checks and signed-context handoff without production final scoring.
   Record exact package/image/source hashes and actual Job/filesystem identities.
   Run model and frozen-runtime work on Serverless only, with declared resources,
   finite timeout and intended Job count. Assess the rehearsal's nonfatal provider
   mount error against actual mount observations; retain its unresolved history.
   September 21: the [production transport probe](../evidence/g8-production-transport-probe-20260921.json)
   passed on Job `aijob-e00samq5cpe1bysr4x`: 12 exact runtime overlays, read-only
   package/bootstrap, native mount identity and signed actual-Job context verified.
   The unsigned entrypoint and wrong context both failed closed. All 25 package
   files were independently rehashed and archived; VM stopped, final key inactive.
   The provider mount warning recurred despite successful runtime checks/readback;
   its root cause remains unresolved. No protected rows, training or scoring ran.
   Transport verification is complete. The failed semantic audit's compute was
   released; VM stopped and final key inactive. Approve the corrected one-Job retry
   before further protected parsing. Snapshot Parquet scope remains hash/footer-only;
   snapshot row/schema consistency and prediction joins are not verified by this audit.
3. **Complete package and preflight.** Check current identity/permissions, versioned
   secrets, pinned image alias, MLflow readiness, native capacity and output/intent
   state. The approved [32 GiB expansion](../evidence/g8-capacity-registration-20260921.json)
   is applied and mounted capacity verified; the original 10 GiB limit could not
   accommodate the 2.451 GiB comparison payload. The new unsigned September 21 review
   binds verified comparison/lineage evidence and the 4 GiB checkpoint bound to
   32 GiB storage. Recheck 20 GiB actual free space at execution; finish the canonical
   request and complete v3 plan after runtime verification and approval. Rebind the
   production review to the corrected comparison path/hash after successful audit;
   the retained unsigned review still points to the defective metadata. Keep
   scored/recovery evidence durable. Follow the [validation policy](../ml/model-validation-execution-policy.md);
   do not reinstate historical billing-freshness, package-expiry or fixed-VM gates.
4. **Obtain replacement-specific approval and sign.** Review the concrete package,
   run scope and resource bounds, then obtain the exception for at most one
   replacement. Bind fresh authorization files and sign the complete plan;
   R4's consumed approval is unusable. Sign actual Job context separately from
   provider readback after submission; preparation is not final-test authority.
5. **Execute once and recover without rescoring.** Persist submission intent and
   resolve ambiguous creates by readback. Seal scored payloads before logging,
   retain one MLflow evaluation run and publish SUCCESS last. Post-scoring recovery
   uses the retained seal; a failure without that seal requires explicit disposition.
6. **Independently verify and close G8.** Download and verify S3 inventories/hashes;
   cross-check MLflow metrics, original lineage and artifacts. Report actual C4
   quality, uncertainty, coverage and resource/throughput evidence, including failed
   thresholds. Update Issue #23, this plan, the roadmap and ARD-0035 with production
   receipts. Stop idle compute and retire temporary access within approved scope;
   retain evidence pending verified and approved cleanup. G9 then records the
   signed quality/resource/cost disposition using the operator-managed policy.

The [C4 contract](../operations/g8/g8-c4-evaluation-contract.md) covers one test date and three
symbol sessions, with row-level metrics and research/synthetic labels. It does not
establish seven-date benchmark or production/client acceptance. Successful execution
cannot guarantee acceptance thresholds. The September 23 G7–G9 exit is at risk;
retain downstream baseline dates until an evidence-backed replan is approved.

### Wave 2: Add The Market-Sequence Transformer

Goal: measure whether causal temporal context improves the frozen Wave 1
baseline enough to justify GPU training and a larger operational surface.

Planned work:

- `[todo]` Define a versioned causal sequence contract with event-time cutoff,
  sequence length, stride, padding/masking, feature ordering and split binding.
- `[todo]` Use CPU Jobs for sequence materialization and time-boxed GPU Jobs for
  training; do not use the vLLM investigation endpoint for this classifier.
- `[todo]` Run architecture-size, sequence-length, encoding, class-weight/focal
  loss and seed-stability experiments using validation only.
- `[todo]` Register preprocessing, model weights, calibration, thresholds,
  checkpoint hash, parameter count, GPU hours and cost metadata.
- `[todo]` Compare standalone Transformer and LightGBM on the exact same frozen
  observations and operational gates.

Wave 2 exit criteria:

- No future event or post-cutoff aggregation enters a sequence representation.
- GPU endpoints/jobs are bounded by timeout and budget and leave no idle GPU
  compute after the campaign.
- The Transformer either clears a predeclared incremental-value gate or is
  retained as research evidence without promotion.

### Wave 3: Combine Transformer Outputs Into LightGBM

Goal: test a cost-aware cascade in which the Transformer becomes an offline or
bounded-batch temporal feature extractor and LightGBM remains the final
tabular decision layer.

Planned work:

- `[todo]` Freeze a `transformer_feature_release_v1` contract containing the
  source model/checkpoint hash, sequence contract hash, row/replay identity,
  causal cutoff, embedding or score schema, null policy and content checksum.
- `[todo]` Materialize Transformer-derived features without exposing labels or
  future events, then join them to `lob_features_v2` only by governed row and
  replay identities.
- `[todo]` Train a new LightGBM candidate with the existing feature set plus
  Transformer scores/embeddings. Do not overwrite the Wave 1 model family.
- `[todo]` Run ablations for tabular-only LightGBM, standalone Transformer,
  Transformer-to-LightGBM, and any late-fusion comparator on identical inputs.
- `[todo]` Measure incremental quality against GPU feature-generation cost,
  CPU inference throughput, staleness, unavailable-feature fallback and
  operational complexity.

Wave 3 exit criteria:

- The cascade wins only if it clears predeclared quality, clean-window,
  calibration, latency, throughput and cost gates.
- The Wave 1 tabular LightGBM bundle remains a verified rollback and fallback
  when Transformer features are absent, stale or incompatible.
- The promotion record identifies every model, feature, split and evaluation
  hash and documents whether the cascade was accepted or rejected.

### Wave 4: Integrate And Package The CEO-Demoable E2E Flow

Goal: prove the complete product-shaped technical story before optimizing its
presentation.

Planned work:

- `[todo]` Add one bounded orchestration entrypoint and campaign manifest that
  links selective Nasdaq preparation, the repository LOBSTER challenge,
  replay/features, LightGBM, Transformer, hybrid and final comparison.
- `[todo]` Run rules, LightGBM, standalone Transformer and hybrid on identical
  immutable Nasdaq evaluation rows; report LOBSTER robustness separately with
  no retuning.
- `[todo]` Produce one verified demo package containing source/release hashes,
  model identities, metrics, latency/throughput, CPU/GPU cost, limitations and
  the accepted or rejected incremental value of each model.
- `[todo]` Provide a deterministic small rehearsal mode that uses already
  verified artifacts and a full evidence mode that references the governed
  Nebius runs.
- `[todo]` Freeze a short CEO narrative: problem, trusted data, three detector
  approaches, fair comparison, result, operational cost and commercial BYO
  next step.

Exit gate: a clean environment can execute or replay the documented flow from
one campaign identity, every artifact verifies, and the demo does not imply
production surveillance qualification.

### Wave 5: Deliver The Secure CEO Demo UI

Status: `[todo after Wave 4; GitHub Story #91]`

Goal: expose a short guided story rather than the internal research workflow:
**Sign in → Data → Replay → Experiments → Management Summary**. Most UI work
starts only after Story #90 verifies the backend campaign. Authentication and
backend authorization are the exception: that security gate may start earlier
and must exit before a shared deployment exposes sensitive Nasdaq or future
customer/BYO data.

Planned work:

- `[todo]` **Google authentication and secure workspace entry.** Selectively
  restore and adapt the archived implementation from commits `a55d8c3`,
  `22ffa3a` and `d27b52b`, now preserved under `archived/google-auth` after
  `68fb0c3`. Keep Google verification and app-session completion behind the
  backend boundary; add deployed-secret handling, expiry/logout/revocation,
  backend workspace authorization and auditable user attribution. Keep local
  demo mode clearly separate and never let it grant fallback access to a
  sensitive shared deployment.
- `[todo]` **Data ingestion panel.** Select Nasdaq ITCH or LOBSTER and show the
  approved session/file, symbol, bounded window, provenance, license/use role,
  acquisition/quarantine, normalization, Nebius S3 publication, manifest/hash,
  split/fold and model-projection state. Surface actionable progress,
  validation failure and safe bounded retry without creating an arbitrary URL
  crawler.
- `[todo]` **Nasdaq-aware replay.** Select dataset/session, symbol, window and
  historical-control or hybrid-plus-attack mode. Show source, timestamp/timezone
  convention, sequence coverage, split/fold and immutable artifact identity;
  load large inputs asynchronously and keep historical activity visibly
  separate from synthetic labels/overlays.
- `[todo]` **Experiments, results and reports.** Present rules, LightGBM,
  standalone Transformer and hybrid under one campaign with truthful job state,
  MLflow identities, verified artifacts, calibration/quality, latency,
  throughput, alert load and CPU/GPU cost. Compare identical Nasdaq final-test
  rows, show the LOBSTER no-retuning challenge separately, distinguish
  development/calibration/final evaluation and expose negative or rollback
  decisions.
- `[todo]` **Management summary.** Build a one-page, exportable CEO/customer
  view of objective, trusted data, three detector approaches, fair comparison,
  false-alert/delay trade-off, result, cost, limitations and champion/rollback
  decision. Keep the research-only claim boundary visible and end with the
  parked BYO data/BYO detector-adapter commercial next step.
- `[todo]` Preserve the existing advanced controls outside the guided path and
  add UI/API tests proving that displayed status, metrics and reports trace to
  verified campaign artifacts rather than browser-local or mock state.

Exit gate: a non-technical reviewer can complete the five-step flow and explain
the result and limitations; Nasdaq versus LOBSTER and the three learned models
cannot be confused; authentication tests cover allowed, expired, revoked and
denied access before sensitive data is exposed. A deterministic rehearsal uses
frozen verified artifacts and cannot trigger unbounded cloud spend.

Planning estimate with limited Codex availability: approximately 8-12 focused
working days, or 1.5-2.5 calendar weeks after backend contracts stabilize.
Google OAuth/deployment configuration and Story #90 API/artifact stability are
the principal schedule risks.

### Feature: Extensible Inbound Data Adapter Framework

Status: `[parked; GitHub Feature #87; commercial Tier-1 after the E2E demo; partial source-adapter foundation exists]`

Goal: make future batch or streaming market-data sources—including vendors and
formats not known today—addable through a versioned adapter package instead of
source-specific changes across ingestion, replay, feature and model code. This
does not imply automatic understanding of an unknown format; each source still
requires an explicitly reviewed adapter implementation and mapping.

Current foundation:

- `IngestionSourceAdapter` already defines candidate discovery and bounded
  import, and LOBSTER/Nasdaq ITCH implement peer adapters.
- Normalized Parquet, source-neutral manifests, canonical Java replay and
  causal features provide a usable downstream target.
- Registration and source types are still hard-coded, capability discovery is
  absent, and there is no third-party adapter conformance kit.

Planned work:

- `[todo]` Version an `inbound_data_adapter_v1` descriptor and protocol for
  discovery, authorization, acquisition/streaming, validation, normalization,
  provenance, retention and capability reporting.
- `[todo]` Add an explicit registry/factory so an approved adapter can be added
  without editing the core ingestion service or downstream model programs.
- `[todo]` Keep vendor fields inside versioned provenance/extensions while
  requiring canonical events, snapshots, timestamps, lifecycle semantics and
  immutable checksummed manifests at the adapter output.
- `[todo]` Support declared batch, object-storage and bounded streaming modes
  with allowlists, secret isolation, byte/time/resource quotas and fail-closed
  schema/version negotiation.
- `[todo]` Publish a conformance kit with golden fixtures for deterministic
  repeat import, causal-prefix invariance, lifecycle integrity, malformed-input
  rejection, resource bounds and Java replay equivalence.
- `[todo]` Require licence/terms and redistribution metadata, retention policy,
  source hash, adapter/config hash and a review record before a new adapter can
  feed a governed corpus.

Exit gate: a fixture third adapter can be registered through configuration,
passes the conformance kit, produces the canonical immutable dataset contract
and runs through replay/features without source-specific downstream branches.

Parking rule: do not generalize the registry during Waves 1-5 unless a narrow
compatibility seam is required to keep Nasdaq/LOBSTER from blocking the later
contract. When resumed, this becomes a commercial Tier-1 feature rather than a
research convenience.

### Feature: Pluggable Detector Adapter And Test Harness

Status: `[parked; GitHub Feature #88; commercial Tier-1 after the E2E demo; model-specific adapter and external-alert evaluation foundations exist]`

Goal: let LOB Arena test LightGBM, Transformer, the hybrid cascade, approved
third-party detectors and future detector extensions through one versioned
adapter contract and the same governed scenarios, rows, metrics and evidence
pipeline. An adapter may be in-process, a remote API, a container or a batch
scorer, but it never receives exchange-write, label or future-data access.

Current foundation:

- The governed benchmark already accepts a fully verified LightGBM release as
  an external alert source, and detector tournaments produce normalized metrics
  and artifacts.
- The existing runtime detector adapter is deliberately LightGBM-specific;
  Transformer and cascade implementations do not yet exist, and there is no
  common detector contract, registry or black-box conformance suite.

Planned work:

- `[todo]` Version a `detector_adapter_v1` capability, request, response,
  health and error contract for in-process, synchronous API, asynchronous and
  batch scorers.
- `[todo]` Send only the approved causal event/feature prefix plus governed row,
  replay and cutoff identities; never send labels, future events, reviewer
  decisions or unopened final-fold metadata.
- `[todo]` Normalize probabilities, scores, alerts, evidence pointers, model
  version, timing and failure state into the canonical detector observation
  schema used by evaluation and reports.
- `[todo]` Implement contract wrappers for rules, governed LightGBM,
  standalone Transformer and Transformer-to-LightGBM cascade, plus a reference
  external detector adapter and extension template.
- `[todo]` Add an approved adapter registry with endpoint/image allowlists,
  scoped secrets, TLS/auth policy, timeouts, retry/idempotency rules, rate and
  payload limits, backpressure, circuit breaking and complete audit metadata.
- `[todo]` Add a conformance harness for contract compatibility, deterministic
  replay where declared, causal isolation, row coverage, malformed output,
  timeout/partial failure, calibration, latency, throughput and data-minimizing
  logs/artifacts.
- `[todo]` Run every registered detector type through the existing tournament
  and governed paired metrics on identical immutable rows, reporting
  unavailable or incomparable outputs explicitly rather than imputing success.

Exit gate: the LightGBM wrapper, a Transformer-compatible fixture, a hybrid
wrapper fixture and one out-of-process detector all pass the same conformance
suite and produce comparable signed evidence. Java remains the only exchange
writer, and failure of one adapter does not disable the other verified detector
paths.

Parking rule: Waves 1-5 may use internal model-specific wrappers, but their
causal input and canonical observation identities must not prevent a later
customer adapter. When resumed, the customer detector is the system under test;
rules, LightGBM, Transformer and hybrid are reference comparators.

### Cost And Operations Guardrails

- Use Serverless AI Jobs for bounded training, batch inference and evaluation;
  they use Compute pricing but remove idle job VMs and disks after completion.
- Use CPU resources for LightGBM, preprocessing, calibration and final cascade
  scoring. Reserve GPUs for Transformer training and bounded feature
  materialization.
- Keep interactive GPU endpoints stopped by default and delete them after a
  campaign when fast restart is unnecessary; stopped endpoint disks may still
  incur storage cost. The existing vLLM endpoint remains an AI Investigator
  surface and is not a detector-training dependency.
- Use Standard Object Storage in the same region by default. Promote selected
  data to Enhanced Throughput only after a measured I/O bottleneck and explicit
  cost comparison.
- Every campaign has a maximum job count, timeout, resource preset and spending
  envelope. Record actual billed usage before increasing scale.
- No Transformer or cascade work begins until the preceding wave has a verified
  evidence bundle and recorded go/no-go decision.
- No CEO presentation-panel redesign begins until the integrated E2E campaign
  can be verified from backend artifacts; presentation must follow evidence,
  not substitute for it. Google authentication and backend authorization may
  begin earlier and must gate any shared sensitive-data deployment.
- No broad BYO adapter framework implementation begins until the E2E demo exits,
  except for compatibility seams needed to avoid a later dead end.

Primary architecture records:

- `docs/roadmap/nebius-lightgbm-wave1-implementation-plan.md`
- `docs/architecture/ARD-0035-nebius-lightgbm-first.md`
- `docs/architecture/ARD-0036-market-sequence-transformer.md`
- `docs/architecture/ARD-0037-transformer-to-lightgbm-cascade.md`
