# Independent LightGBM retention audit

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

Exit `0` means plan generated or both live audits verified. Exit `2` means a live
audit is incomplete. Inspect `status` to distinguish planning from verification.
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
VM window exceeded its proposed 15-minute bound; the VM was then stopped, with no
further startup retry. A future bounded startup must have an independent automatic
stop watchdog installed before it begins, including during operator approval waits.
