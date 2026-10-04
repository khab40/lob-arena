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
    Then it fits temperature on calibration and scores calibration and operating-point rows
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

## Prepared package and execution handoff

The package retains width 128, learning rate 0.0003, seed 42, epoch 4. The new
v3 request has seven exact request/SUCCESS references. Checkpoint bytes, trial,
original source/image, feature release, role manifest, ordered targets and
train-only normalization must match. New execution source/image are recorded
separately. Checkpoint deserialization and CUDA compatibility are checked in the
separately authorized Job, before scoring; no local weights were executed.

The image preserves original model, training, evaluation, worker, dependencies
and immutable inputs. Its run module differs only by checkpoint-origin handling;
the context builder reverses that patch and requires the original source hash.
The newer live training logger is not part of this sealed runtime. This Job
performs no gradient training. Existing T/S inputs are read for provenance and
train-only normalization; C fits one scalar temperature and O selects development
operating points against the frozen LightGBM predictions on exactly aligned rows.

Execution evidence is rooted at `outputs/transformer-comparison-20261004/`.
The operator interpreter is `operator-venv/bin/python` below that directory, with
`PYTHONPATH=backend:scripts` from the implementation checkout. Its seven direct
requirements are pinned by `serverless/transformer_inputs/requirements.txt`.
The old incomplete environment is retained; it is not an executable dependency.

After exact proposal/spend approval and green CI:

1. Recheck request, proposal, referenced files, assembly image and operator hashes.
   Run the pure local prerequisite preflight, inspect all pinned SDK imports,
   verify existing signing custody and confirm name/prefix remain unused.
   Refresh the estimate against the $6.25 reservation before admission.
2. Start `transformer_comparison_observer.py run` with the exact request path/hash
   and a fresh observer output directory. It records provider reads before create.
   Start `transformer_confirmation_supervisor.py run` for slot `inference`, binding
   proposal/request/operator hashes, the explicit interpreter and existing custody.
   Do not create until both inspect commands report `admission_ready: true`.
3. Run the exact create command once. Retain the returned operation and Job ID.
   An ambiguous response requires read-only reconciliation, never another create.
   The observer targets a ten-second cadence; network retries may lengthen it.
   A stale observation (over 30 seconds), dead process or failure blocks admission.
   Once a Job is seen the admission latch stays closed, even if it disappears.
4. Keep operator supervision active through provider terminal state. Cancel only
   this created Job on attester failure, uncertainty, monitoring loss, STARTING
   beyond ten minutes or create-to-terminal beyond two hours. Cancellation must
   be included in the exact run authorization. The observer only reports; it does
   not cancel automatically. One-hour provider runtime is not extended by the
   extra billing reserve. No helper restart or automatic replacement is allowed.
5. Retain SUCCESS, provider terminal readback and immutable artifact receipts.
   Collect using the pinned operator and independently check all seven prerequisites,
   original checkpoint origin, the input event, exact C/O row alignment, temperature
   optimum, frozen LightGBM calibration/thresholds and reproduced metric arithmetic.
   A completed provider state alone is not a verified result.
6. Save one comparison Markdown report with raw/calibrated/LightGBM metrics,
   calibration reliability and precision-recall plots, threshold/confusion tables,
   per-family support, measured Transformer latency and continue/stop/inconclusive
   research disposition. No epoch graph is produced for this non-training Job;
   retained training curves remain linked. Replayable artifacts precede online
   MLflow reconciliation. Do not compare unmeasured LightGBM latency or claim a
   final-test/production win from this one-instrument/date development comparison.

The proposed $6.25 is additional to the fully retained $25 confirmation cap and
$50 grid allowance, on the operator-reported $300 historical baseline. The
$381.25 planning envelope is not the current account bill. Actual charges remain
unreconciled; no estimated savings are released. Retention covers 90 days with
an operator review on 2027-01-02, without automatic deletion.

Exact create command (authorization still pending):

```sh
rtk proxy nebius ai job create --parent-id project-e00g6zvxpr00waz8t3y51k --name transformer-compare-c4-20261004-r1-inference --image cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr@sha256:5ab068aae50ef1e8dc2ff89315f5cf5cda01b20b937b48caed8194f08880d713 --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --timeout 1h --disk-size 100Gi --shm-size 1Gi --subnet-id vpcsubnet-e00ppzc4353dxv210j --restart-policy never --on-demand --env-secret AWS_ACCESS_KEY_ID=mbsec-e00arhndyprqr8egjw@mbsecver-e00rjzerny1pf9qhna --env-secret AWS_SECRET_ACCESS_KEY=mbsec-e00s7qtjj5n9ghacnh@mbsecver-e00yfn5w54jc1ybkwv --inject-file /Users/akhabalov-da_1/Documents/STUDY/nebius-ai-performance-engineering/code/ai-market-abuse-detection-arena/outputs/transformer-comparison-20261004/execution/inference/request.json:/opt/research/request.json --async --format json --retries 1 --no-browser --auth-timeout 120s
```
