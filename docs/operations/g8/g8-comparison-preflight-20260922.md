# G8 comparison and production preflight — 2026-09-22

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
