# G8 comparison and production preflight — 2026-09-22

Project #3 story: [LightGBM qualification #23](https://github.com/khab40/lob-arena/issues/23).
Runtime defect: [Bug #221](https://github.com/khab40/lob-arena/issues/221), a child of #23.

**September 23 readback:** comparison audit R5 completed successfully and passed
[independent verification](../../evidence/g8-comparison-verification-20260923.json).
Job `aijob-e00p01kcjvxcb53g7e` verified all 377 files, 27 checkpoints and 30 replays
in 1728.511 provider seconds. Final access stayed inactive and compute was released.
The [R5 proposal](../../evidence/g8-comparison-monitor-fix-proposal-20260922.json)
preserves the exact executed hashes.

R4 was cancelled after 19 replay completions when the old monitor confused a
temporary log-fetch network error with absent startup. The corrected monitor
retains observed startup across outages; four inert regression tests pass. R4
is incomplete evidence, not a semantic failure or success. R5 provides the pass.
The verified runtime and package results are recorded below; final execution remains separately gated.

As a validation engineer,
I want the original comparison evidence verified and bound into a reviewed production package,
So that the frozen evaluation can be authorized against known inputs and runtime identities.

## Analysis and readiness

R2 was cancelled without a semantic result. The reviewed R3 proposal adds an
injected supervisor and progress records before native-filesystem access. The
operator approved its cloud execution in advance on September 22 as step 2 of
three separate analyse/plan/code/review/push PRs. The exact existing proposal,
worker and supervisor hashes are preserved in the execution approval receipt.

- Actor: validation engineer.
- Goal: a passing comparison audit plus current production preflight evidence.
- Value: exact original comparison/runtime binding before final authorization.
- Out of scope: model loading/scoring, final-bucket reads, replacement signing.
- Verification: provider identity/settings, unique submission intent, aggregate
  worker/supervisor results, independent hashes and current read-only preflight.
- Assumption: progress or successful startup never substitutes for a semantic pass.

```gherkin
Feature: Verified G8 comparison and production readiness
  Scenario: Complete the supervised comparison audit
    Given the exact approved proposal and verified staged original comparison
    When one bounded audit Job completes
    Then one successful worker result reports 377 files, 27 checkpoints and 30 replays
    And the supervisor exits successfully and provider compute is released

  Scenario: Fail closed on missing startup or an expired deadline
    Given the audit Job has started
    When launcher output is absent for 300 seconds or supervision exceeds 3000 seconds
    Then the Job is cancelled and its evidence retained
    And no retry or final evaluation is started implicitly

  Scenario: Bind production review only to verified evidence
    Given the comparison audit has passed independently
    When the unsigned production package and current preflight are assembled
    Then they bind the corrected comparison, frozen candidate and exact runtime
    And replacement-specific final authorization remains required
```

## Plan and resource bounds

1. Revalidate the frozen image alias, inactive final key, filesystem and unique run.
2. Rehash the 377 corrected files and 25 preserved package files; stage only R3
   metadata in a fresh directory, preserving original and corrected trees.
3. Stop the staging VM. Persist an exclusive intent, dry-run and submit one Job.
4. Monitor every minute, enforce startup/deadline cancellation, and independently
   check the complete result and compute release.
5. Rebind the unsigned production review only on success; check current identity,
   storage, image, MLflow and output state. Review evidence, test and push this PR.

Job: frozen image, `cpu-d3/4vcpu-16gb`, 100-GiB disk, one-hour provider timeout,
no restart, 2940-second worker alarm, 3000-second independent supervisor. Maximum
one Job, four vCPU-hours and 16 GiB-hours; no credentials injected. Existing
filesystem mounts read-only. Original protected comparison records may be parsed
only for the approved structural audit; snapshot Parquet checks remain byte hashes
and footer counts, not row/schema or snapshot-event consistency validation.

Staging VM: existing `cpu-e2/2vcpu-8gb`, 420-second work deadline, detached stop
watchdog armed before startup (stop begins by 600 seconds), nominal 900-second
total / 0.5 vCPU-hours / 2 GiB-hours. No new VM/filesystem or permission changes.
The local watchdog requires host/network/provider availability.

## Throughput correction within this PR

R3 verified all 377 files and 27 checkpoints and reached six completed replays,
but serial replay throughput projected beyond its 2940-second worker limit.
It was cancelled and compute released; all progress and original bytes remain.
This is a throughput finding, not a semantic pass or a reuse of R3's one-Job intent.

The next bounded attempt uses a new R4 audit identity and exactly three child
processes within the same four-vCPU / 16-GiB Job. Each child applies the unchanged
per-replay checks; the parent counts only successful completions. Linux fork
inherits the already verified in-memory bootstrap and filesystem/network guard.
Pool failure terminates children; the injected supervisor still bounds the entire
process group. One-hour provider, 2940-second worker and 3000-second supervisor
limits remain. The operator's advance cloud approval covers this planned repair;
declare one additional Job, at most four vCPU-hours / 16 GiB-hours, before submission.

```gherkin
  Scenario: Validate independent replays within the existing CPU allocation
    Given serial replay throughput cannot fit the declared audit deadline
    When a separately bound attempt validates replays with three child processes
    Then every replay receives the same complete checks
    And only successful replay completions contribute to the final count
    And child failure prevents a semantic pass
```

The development S3 reader cannot inspect the production result prefix or intent:
both metadata checks were denied. Denial is retained as unverified, never empty.
The final-access key remains inactive; current access policy must establish the
appropriate read-only preflight path before that check can pass.

## Production verification runtime repair

As a validation engineer,
I want repeated verification to reuse an independently recomputed comparison only after rechecking its input bytes,
So that checkpoint and logging checks fit a measured execution window without weakening evidence integrity.

Static review found at least ten full C4 passes before publication: initial report
(one), retention validation (one), first recovery (three), finalization's seal
validation (one), recovery (three), and snapshot validation (one). Every pass
exhausted 30 replay streams; the previous Job contract permitted only 3600 seconds.
The operator selected verification optimization followed by a Nebius benchmark.

```gherkin
Feature: Reuse an independently recomputed C4 comparison
  Scenario: First independent verification
    Given the scorer produced a C4 report
    When its first independent verification runs
    Then the original comparison is recomputed in full

  Scenario: Verify another copy of unchanged evidence
    Given this process independently recomputed the same comparison
    When another checkpoint copy passes all existing artifact and comparison hash checks
    Then verification may reuse the independently computed metrics
    And returned report mutations cannot change the retained metrics

  Scenario: Reject changed evidence before reuse
    Given an independently computed comparison is retained in memory
    When any bound input bytes change
    Then existing integrity validation fails before reuse

  Scenario: Verify in a fresh process
    Given a different process opens the retained checkpoint
    When it verifies the comparison
    Then it recomputes the comparison in full
```

Plan: retain one process-local entry keyed by the canonical profile and prediction
manifest, after unchanged release, projection and original-checkpoint validation.
Initial report generation never populates this entry. No disk cache, signed
success shortcut or cross-process reuse is introduced. Run a synthetic frozen
runtime rehearsal on Nebius, including changed-input and fresh-process checks;
measure full recomputation counts and elapsed time before declaring readiness.

## Replacement execution window

As a platform operator,
I want the signed replacement request to declare a realistic finite execution window,
So that the one authorized evaluation is not cut off during mandatory verification.

The serial audit observed six similarly sized AAPL replays by 961.436 seconds.
Scaling by compressed bytes gives an approximate 109.7 minutes for the two full
passes retained by the optimization. This is a sizing estimate, not a measured
production runtime; SQLite pairing, scoring and publication add work. Prepare a
three-hour replacement option with unchanged four vCPU, 16 GiB RAM and 100 GiB
disk, bounded to one execution (12 vCPU-hours / 48 GiB-hours maximum). Final
authorization must explicitly cover that option before submission. Standard
development requests retain their existing one-hour ceiling.

```gherkin
Feature: Bound the replacement verification window
  Scenario: Render the signed replacement request's timeout
    Given a verified replacement package binds a three-hour final request
    When its Job command is rendered
    Then the provider timeout is three hours
    And its actual execution context must match that request

  Scenario: Preserve development limits
    Given a development request exceeds one hour
    When its resource contract is validated
    Then validation fails

  Scenario: Reject a timeout outside the reviewed choices
    Given a final request asks for more than three hours
    When its resource contract is validated
    Then validation fails
```

## Verified optimization and production transport — September 23

The [Nebius synthetic benchmark receipt](../../evidence/g8-verification-reuse-verification-20260923.json)
verifies Job `aijob-e00ydpcb1xh4ksafd5`: two full comparisons, eight unchanged
checkpoint-copy verifications without recomputation, five changed-input rejections,
and one fresh-process recomputation. Initial and independent comparison took
2.227 and 2.239 seconds; all eight repeated checks took 1.639 seconds together.
These synthetic timings establish behavior, not full production duration.

The [new unsigned review](../../evidence/g8-production-review-20260923.json)
binds the passed comparison audit and verified runtime at source `450c715`.
Its SHA-256 is `80214132f645b78818f7f6fa3f28416502c75b9d8ad4dd49eb37419696d595a2`.
It contains 26 files / 13 runtime overlays, including the extended timeout contract;
the candidate, model, calibration and threshold remain frozen. Its `new_runtime_transport_verified=false`
records preparation-time state; the subsequent receipt below establishes the probe outcome
without rewriting that immutable review.

The [independently verified transport probe](../../evidence/g8-production-transport-probe-20260923.json)
completed on `aijob-e00x2v709xdvz0vb8y`. It verified all 26 package files, 13 actual
in-memory modules, the injected read-only bootstrap, native mount identity and
32-GiB capacity with 29,077,970,944 free bytes, and the signed actual-Job context
with a three-hour timeout. The unsigned entrypoint rejected execution, and a
wrong context identity was rejected. The provider emitted its recurring mount
warning, but the actual runtime and independent readback verified both mounts.

This probe used one `cpu-d3/4vcpu-16gb` Job, 100-GiB disk, a three-hour provider
cap and 600-second probe alarm, without credentials or protected-row/model access.
The existing VM's detached watchdog was armed before startup and verified its stop.
All Job compute was released; the final key remained inactive. The exact unsigned
package was hash-verified and moved to `transport-probes/g8-production-probe-20260923/unsigned-production`,
preserving evidence and leaving the canonical production path absent.

Step 2 now supplies comparison, runtime and package evidence for review. The
remaining live output-prefix/intent and authenticated MLflow checks must run under
the final-authorized identity before data access: development-reader AccessDenied
is not an empty-prefix result. Step 3 must obtain replacement-specific approval
for exactly one three-hour evaluation, preserve consumed R4 history, sign the
actual request/package/context, execute once, and independently verify published
results and lineage. Neither this probe nor CI establishes G8 model quality.

Durable evidence is in the project-root `outputs/g8-comparison-monitor-fix-20260922/`,
`outputs/g8-verification-reuse-benchmark-20260923-r2/`,
`outputs/g8-production-review-20260923-v1/` and
`outputs/g8-production-transport-probe-20260923/` directories. Earlier failed or
cancelled attempts remain retained with their distinct identities and outcomes.
