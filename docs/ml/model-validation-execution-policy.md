# Execution policy through LightGBM and Transformers validation

Decision: operator instruction, **2026-09-16**. Applies immediately to model
validation, synthetic rehearsals and pre-production evaluation preparation on
Nebius. Revisit after both LightGBM and Transformers validation have recorded
outcomes; there is no calendar expiry or automatic return to the previous caps.
The operator owns spend monitoring through alerts. Agents must not inspect
billing, request balances, estimate remaining credits, or request a new spend
approval merely because time has passed.

## Removed administrative gates

- One-hour signed-package submission expiry and 24-hour recovery expiry.
- Billing receipts, freshness checks and the $2/$40/$50 validation ceilings.
- Mandatory four-hour MLflow VM sessions, three-hour stop guards and two hours
  of remaining guard time before startup.
- Mandatory 24-hour filesystem deletion. Retain sealed outputs until independent
  verification and recovery are complete; elapsed time must not force rescoring.
- Repeated authorization solely for an unchanged package after an approval delay.

These gates were introduced to limit spend and stale preflight evidence. They
blocked execution during tool-approval waits without measuring model quality.
Package integrity, actual resource identity and authorization are checked directly.
A signed package may wait without expiring; changed code, image, inputs, credentials
or execution scope still require updated bindings and review. An old package is
not made valid by editing its timestamps or relabeling its failed attempt.

## Controls that remain

- Run training, scoring and frozen-runtime tests on Nebius Serverless. Local work
  is limited to orchestration, edits, static tests and artifact inspection.
- Declare each run's resources, finite provider timeout and intended Job count.
  Keep restart `never` and resolve ambiguous creates by readback before any retry.
  The native recovery test has two phases/Jobs; this is its test design, not a
  lifetime quota for all subsequent validation experiments.
- Bind immutable image, reviewed code/input hashes, actual Job and filesystem
  identities, versioned secret references and authenticated MLflow evidence.
- Keep private access, final-data isolation, output no-overwrite checks, bounded
  transfers and the five-minute wait for signed Job context. These limits address
  hung execution, storage capacity or access integrity, not package age.
- Preserve R4 history, the frozen candidate/calibration/features/thresholds, new
  replacement run identity and one separately approved final-test execution.
  Final-test access is never inferred from this policy. A replacement-specific
  signed approval is still required when preparing the live package.
- Preserve completed scoring outputs and recover publication/tracking without
  rescoring. Stop idle compute after work; archive evidence before approved cleanup.
  An explicit timed VM stop remains available when the operator requests it.

## Implementation and migration

Native package schema `g8_native_rehearsal_plan_v5` and replacement schema
`g8_replacement_plan_v3` bind `lightgbm_transformers_validation_v1` and
`operator_managed_alerts`. Neither carries billing or expiry fields. Native
packages inject one bootstrap; bulk files use a read-only view of the existing
native filesystem after [both KMS rejections](../operations/g8/g8-native-rehearsal-package.md#kms-rejection-and-payload-headroom).
Rebuild capsule v2 from the retained frozen source tree, then sign from reviewed code;
remove old expiry, cleanup, spend and billing fields from bindings. Do not reuse
old signed packages, old submission intents or consumed final-test authorization.
The native builder no longer accepts `--billing`.

Use `g8_vm_deadline.py start --operator-managed --directory /absolute/new-start`
for a recorded, single-use VM start without a stop lease. Record the actual VM
state and stop it when idle. Existing `/tmp` orchestration copies that require
`expires_at`, billing, or guard headroom are obsolete and must not be used.

Historical receipts retain their original limits and outcomes. This decision does
not turn failed attempts into successes or establish G8 completion. Report actual
quality, including failed acceptance thresholds. G9 remains gated by G8 evidence;
Transformers work follows the recorded LightGBM exit disposition in ARD-0036.
