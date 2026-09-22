# Independent LightGBM retention audit

## User story and readiness

As a validation engineer,
I want to retrieve the frozen candidate's stored evidence and verify its MLflow lineage,
So that I can establish retention and traceability before requesting final evaluation.

- **Actor:** validation engineer, with the platform operator controlling the existing MLflow VM.
- **Goal:** verify exact stored development artifacts and the selected MLflow run.
- **Value:** detect missing, corrupted or mismatched evidence before final authorization.
- **Acceptance scenarios:** exact retrieval, lineage mismatch, component resumption,
  automatic shutdown and unavailable-service reporting below.
- **Out of scope:** retraining, scoring, historical-run repair, new IAM grants,
  registry promotion and final-test access.
- **Verification method:** inert automated tests plus checksum-bound live receipts;
  successful test fixtures alone cannot satisfy the live retrieval scenario.
- **Assumptions:** the reviewed inventory hash is trusted, approved credentials
  remain valid, and the operator's Mac and provider API remain available. The
  local watchdog prevents idle sleep but cannot guarantee a cloud stop after
  host power loss or a provider/network outage.

## Acceptance criteria

```gherkin
Feature: Verify frozen LightGBM retention and lineage

  Scenario: Verify stored development evidence
    Given the reviewed inventory of the frozen candidate
    When the validation engineer retrieves its exact development result objects
    Then every retrieved object's size and hash match the inventory
    And the receipt identifies the candidate and inventory used

  Scenario: Verify the selected MLflow run
    Given the selected development run is available
    When the validation engineer audits its metadata and seven governed artifacts
    Then its parameters, thresholds and per-shard lineage match the inventory
    And all seven artifacts match their recorded sizes and hashes

  Scenario: Reject mismatched lineage
    Given a run refers to a different feature release or shard hash
    When the validation engineer audits that run
    Then the receipt reports the mismatch without marking tracking as verified
    And the historical run remains unchanged

  Scenario: Resume incomplete tracking verification
    Given exact storage retrieval has already been verified
    When the validation engineer requests only MLflow verification
    Then the audit makes no new result-object reads
    And its receipt identifies only MLflow as the requested component

  Scenario: Stop the temporary tracking session after completion
    Given the existing MLflow VM was stopped before the audit
    When the temporary tracking session completes or fails
    Then the operator receives a verified stopped-state receipt

  Scenario: Stop when the audit controller disappears
    Given an independent stop watchdog was armed before VM startup
    And the operator host and provider API remain available
    When the audit controller disappears
    Then the watchdog initiates shutdown by the ten-minute deadline
    And it verifies the provider reports the VM stopped

  Scenario: Report an unavailable tracking service
    Given the tracking service does not become ready within the session allowance
    When the readiness deadline expires
    Then tracking remains unverified
    And the temporary VM session is stopped without another startup retry
```

## Implementation plan and verification mapping

1. Validate the anchored inventory and compare exact object bytes and run lineage.
   `test_lightgbm_retention_audit.py` covers hash/lineage mismatch and component plans.
2. Arm a detached watchdog before startup; verify shutdown after normal completion,
   startup failure and controller loss. `test_nebius_mlflow_watchdog.py` covers these
   paths with inert processes and provider doubles; it never starts a cloud resource.
3. Resolve approved credentials before startup, allow a bounded readiness wait,
   and run the MLflow-only audit through a loopback SSH tunnel.
4. Retain live readback, diagnostic and shutdown receipts, update current status,
   and mark each live criterion satisfied only when those receipts demonstrate it.

The read-only audit compares an externally anchored `lightgbm_candidate_inventory_v1`
with exact development result objects and the existing MLflow development run.
It consumes the inventory produced by [PR #216](https://github.com/khab40/lob-arena/pull/216)
without importing that producer, the model runtime or training/scoring code.
Neither a successful audit nor a PR merge authorizes G8 final evaluation.

## Prepare and run

Plan mode uses only Python 3.11+ standard-library modules. Live storage reads also
require `boto3`; the September 22 isolated audit environment pins `boto3==1.42.0`.
Keep this environment separate from model/runtime dependencies. On macOS/Linux:

```bash
python3 scripts/audit_lightgbm_retention.py \
  --inventory /path/to/inventory-final.json \
  --inventory-sha256 04d9757a9232a4d724099360557101b18a5cdb8207d05c4781fd1482daf15876 \
  --results-bucket aimada-wave1-results-e00g6zvxpr00 \
  --input-bucket aimada-wave1-dev-e00g6zvxpr00 \
  --output /existing/evidence/directory/readback-plan.json
```

The anchor is the reviewed inventory's exact file hash, not a hash accepted from
untrusted inventory content. Explicit bucket arguments bound the read scope.
Use a new output name and add `--execute` for live reads. Supply existing approved
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` and `MLFLOW_TRACKING_USERNAME`/
`MLFLOW_TRACKING_PASSWORD` through the process environment; never place secrets in
arguments or receipts. No profile or instance-credential fallback is used.

Revalidate the current VM and access rules with Nebius MCP before opening the SSH
tunnel described in [MLflow operations](mlflow-tracking-server.md#nebius-wave-1-deployment).
The default endpoint is `http://127.0.0.1:5500`; `--tracking-endpoint` accepts only
explicit loopback HTTP endpoints. Disable proxy inheritance and redirects so
Basic authentication cannot follow a server-selected destination. The source
inventory's private tracking URI is historical metadata, not an automatic target.

## Verification and bounds

- Rehash every exact result object, including `SUCCESS`, checksums and model bytes.
  No bucket listing, uploads, metadata changes, IAM changes, training or scoring.
- Compare finished/active run state and development experiment, binding hashes,
  feature-release ID/full hash, Git identity, hyperparameters, seed, preprocessing,
  feature exclusions/count, early stopping and operating-point metrics/thresholds.
- Check the exact dataset-name set, digest adapter, full artifact hash, S3 source,
  train/validation context, counts, membership hash and feature-release lineage.
- Download and hash the seven expected `governed/` artifacts using the authenticated
  MLflow artifact proxy. Unsupported artifact URI schemes fail closed. Extra
  governed artifacts are reported, never fetched automatically.
- Default total audit deadline: 300 seconds; maximum: 600. Individual network
  timeouts are 5–10 seconds, with no application retries. Maximum inventory: 500
  objects, 16 MiB each, 64 MiB total. MLflow metadata responses: 4 MiB each; artifact
  listing: at most ten pages. Every artifact body is bounded by its expected size.

Use `--component mlflow` to resume tracking verification without repeating an
already verified storage pass; it needs only the tracking credentials. The default
`--component both` checks both systems; `--component storage` checks storage only.
Unrequested components remain `not_attempted` and `verified: false` in the receipt.

Exit `0` means plan generated or all requested live components verified. Exit `2`
means a requested live audit is incomplete. Inspect `status` and
`requested_components` to distinguish planning, partial scope and verification.
Receipts preserve exact inventory/tool hashes, timestamps, scope, successful object
checks and the first failed storage path. Errors omit server bodies and credentials.
Output creation is exclusive/private; reruns cannot overwrite prior evidence.

## Limits

This checks retrieval now, not backup policy or future availability. It does not
search for extra S3 objects, download external input manifests, parse feature rows,
evaluate model quality, audit every rejected trial, create registry versions or
repair historical MLflow runs. Summary metric checks cover the inventory's early
stopping and operating points; calibration artifact hashes bind its full contents.
Per-iteration learning curves and complete configuration logging for future
campaigns remain separate work. Final access and replacement authorization remain
separate gates.

The read endpoints follow the [MLflow REST API](https://mlflow.org/docs/latest/api_reference/rest-api.html).
See the [dated readback evidence](../evidence/lightgbm-retention-audit-20260922.json)
for actual outcomes; tests and plan mode are not live verification.

The audit process deadline does not stop a hosting VM. September 22's operator-managed
VM window exceeded its proposed 15-minute bound; the VM was then stopped. The
continuation uses `scripts/nebius_mlflow_watchdog.py`: a detached local process
arms before startup, requests stop by ten minutes and verifies provider `STOPPED`.
It stops early when work finishes or fails and survives controller exit. CLI
timeouts terminate the subprocess group. It refuses to adopt a running VM or a
different resource preset. macOS idle sleep is inhibited while it is active.

The watchdog requires the Mac, network and provider API to remain available; it
is not a provider-side billing cap. Use a fresh canonical evidence directory with
`bounded_vm(directory)`, keep work within 420 seconds, and inspect the shutdown
receipt. The first live continuation failed at SSH readiness but independently
verified shutdown in 122.109 seconds. See the
[continuation receipt](../evidence/lightgbm-tracking-continuation-20260922.json).

Dataset-source verification includes the input's `projection_artifact_root` or
`feature_artifact_root` between the release URI and shard path, matching the
historical producer contract. This corrects the independent checker; frozen
datasets, model bytes and historical MLflow records remain unchanged.
