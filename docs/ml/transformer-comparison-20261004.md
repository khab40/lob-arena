# Checkpoint compatibility and comparison packaging — 4 October 2026

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
Operator requested this next step after verified confirmations in merged PR #308.
Implementation/preparation is authorized; model execution needs separate exact
request and spend approval. Preserve the existing $25 commitment and frozen G8/G9.

As a researcher,
I want to compare the original selected Transformer checkpoint with frozen LightGBM,
So that the research decision uses calibrated, aligned development predictions.

Actor: researcher; platform operator admits the bounded Job.
Goal: load seed 42 / epoch 4 without changing its historical bindings.
Value: complete the predeclared comparison without retraining or selecting a lucky seed.
Out of scope: model/search/optimizer changes, final data, new IAM, promotion, merge, deletion.
Verification: inert contract/adversarial tests, exact artifact/hash inspection,
image equivalence, provider dry-run, then separate authorized cloud result readback.

```gherkin
Feature: Compare the verified selected checkpoint across execution versions
  Scenario: Load the unchanged selected checkpoint
    Given all five original and two replacement publications are verified
    And seed stability passed with seed 42 retained
    When the comparison worker loads the original selected checkpoint
    Then its checksum and original trial and input bindings must match
    And the new execution identity is recorded separately

  Scenario: Reject changed prerequisites before scoring
    Given a changed publication version, origin, checkpoint or normalization
    When the comparison request or checkpoint is verified
    Then verification fails before model inference or calibration

  Scenario: Keep the comparison scope fixed
    Given the exact one-hour development comparison request
    When the package is admitted
    Then it permits only calibration and operating-point roles
    And no training or final-test access is authorized

  Scenario: Observe startup before submission
    Given the pinned local dependencies, files and signing custody pass preflight
    When the operator prepares to create the Job
    Then the attester and status observer must already be live
    And failure or an ambiguous write stops the attempt without resubmission
```

1. Start from current main in the clean reused worktree; preserve retired #308 refs.
2. Add an inference-only namespace with seven exact publication/origin references.
   Preserve all v1/v2 request behavior and their immutable hashes.
3. Validate selected checkpoint metadata against original bindings; compare all
   data/normalization fields to current inputs and retain both origins in results.
4. Cover tampering, omitted/swapped dependencies, self readback, foreign namespace,
   calibration bounds and input alignment using inert tests; no local model workload.
5. Prepare operator preflight/supervision for a one-hour comparison and start its
   observer before submission. Verify dependencies and all needed local files
   before any credential, attester or Job action.
6. Build a digest image from the existing sealed numerical image, explicitly
   inspecting changed execution files; retain original model/training/evaluation
   bytes. Check <=64-character repository before build/upload/dry-run.
7. Prepare one exact 1-L40S / 8-vCPU / 32-GiB / 100-GiB request, restart never,
   one attempt, one-hour timeout, bounded publication and spend. Refresh prices,
   verify unused name/prefix, run exact dry-run, publish PR with CI and evidence.
8. Request exact execution/spend approval only for that concrete package. On a
   later authorized run, verify C temperature/O thresholds and saved baseline
   alignment independently, retain plots and present continue/stop/inconclusive.

No inference/calibration Job may be created by this preparation step.
