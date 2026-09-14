# G8 replacement integration and approval gates

Status: engineering implementation; **not final-test or provisioning authority**.
G8 remains open and G9 blocked. This follows merged PR #177, from updated main
`827ddc906f0e13f86570762f1eb4a59a83ab62d4`.

## Execution boundary

`serverless/jobs/run_lightgbm_g8_replacement.py` is a separate entrypoint. The
ordinary submitter and its Wave 1 no-volume rule are unchanged. Verification is
the default; `--command` renders the scoring command and `--recovery-command`
renders a command with `--recover`, without submitting. Both rendering flags
and the live `--execute` / `--recover` flags are mutually exclusive.
Recovery rendering uses the retention deadline, not the scoring expiry, and
retains the same signed package, run directory and filesystem; only the Job name
gets a `-recovery` suffix. Neither code nor this
document authorizes issuing the rendered command.

The canonical, Ed25519-signed `replacement.json` uses `ReplacementPlan` in
`backend/app/ml/lightgbm/g8_replacement.py`. It binds:

- The four prior submissions, R4 Job/run IDs, prior test access, monitor/log
  digests, one replacement, and the no-tuning constraint. The first-run v2 receipt
  cannot stand in for this exception. A fresh candidate authorization is required.
- The unchanged production candidate/image and original final C4 root/projection
  hashes and release URI; the corrected `artifacts` layout; the complete C4
  profile, original comparison package, request, lineage and code-file hashes.
- A single native filesystem ID at `/g8-durable`, rehearsal-observed virtiofs
  source, capacity, transfer bounds, version-pinned MysteryBox selectors and
  exact subnet. No S3/FUSE mount, nested mount, writable code injection or public
  endpoint is introduced.
- Signed, reviewed observations: native Job-loss/reattachment, authenticated
  remote round trips, original 27-checkpoint metadata inventory and billing.
  Their byte hashes are mandatory. Positive booleans are **not independently
  obtained by this verifier**: the operator must review the underlying receipts
  before signing the complete plan. No placeholder success receipts are generated.
- Observations at most one hour old, an execution expiry within one hour,
  campaign spend below $40, total exposure at most $50 and a retention/recovery
  deadline within 24 hours. Expired execution cannot restart scoring; recovery
  may continue only within its separately bounded retention window.

The exact required flat file allowlist is enforced by `ReplacementPlan`.
Each injection is at most 64 KiB; its byte count and SHA-256 are verified.
The `CODE_PATHS` mapping renders the required overlay mounts as well as package
copies, and the live CLI verifies the installed runtime files against the plan.
No unsigned production example is presented as ready.

After the operator submits the reviewed command **once**, they retain the actual
Nebius API readback and stage an operator-signed context at
`/g8-durable/contexts/<run-id>.json` and `<run-id>.sig`. Its exact keys are
`execution_package_sha256`, `filesystem_id`, `context` (a
`Wave1ExecutionContext` with the actual `aijob-...` ID), and
`job_readback_sha256`, and `purpose` (`execute`). Sign with the same trusted operator key. Review the actual
Job image, injected file identities, one volume, resources, credentials selectors,
network and restart policy before releasing this context. The runner waits at
most five minutes, bounded by execution expiry, without accessing final data.
An ambiguous Job-create response is **not permission to submit again**; recover
the exact API Job identity. The signer, not the runner, attests to API readback.
For an explicit recovery Job, stage `<run-id>-recovery.json`/`.sig`, with purpose
`recover` and that recovery Job's actual identity. The CLI returns the current
executing Job ID separately; it never replaces the original scoring identity in
the immutable release or MLflow logging plan. Retain these signed contexts and
CLI receipts with the API readbacks in the execution audit archive.

## Durable lifecycle

1. Validate signatures, fixed identities, actual native mount and Job context.
   After waiting for context, recheck the package and the native mount immediately
   before execution or recovery acquires its filesystem lock. A missing mount,
   changed source/type/options or changed kernel mount identity fails closed.
2. Exclusively create `/g8-durable/<new-run-id>` and hold a filesystem lock.
   An occupied directory cannot execute again. Verify MLflow readiness, claim
   the conditional S3 intent, and durably reserve one MLflow run before final
   access. Ambiguous intent/run creation never permits another scoring execution.
3. Keep the entire workspace on that filesystem. Verify the candidate, mark final
   access, download the final release once and invoke the frozen `_run_final`
   once with the approved C4 evaluator/logger hook. Keep the legacy failure
   publisher out of this path; exceptions preserve the workspace and checkpoints.
4. Capture original scoring-process resources, Job identity, environment and
   input inventory. Seal scored artifacts plus original comparison evidence;
   fsync a separate receipt before the first evaluation-evidence logging call.
5. Use the same log-only recovery operation on normal execution and after Job/
   workspace loss. Reverify the C4 report and complete evidence, then finish the
   reserved MLflow run. No input downloader, model execution or run creation is
   reachable from `finish_retained`.
6. Reconstruct the cloud result from the seal, preserving **original** Job and
   resource measurements. `g8-recovery.json` explicitly scopes resource timing
   to the original process through pre-logging; it does not claim recovery CPU
   usage was original scoring usage. Retain a complete publication checkpoint
   and independently fsynced pointer. Reverify all publication artifacts against
   the original scored seal, even if a publication checkpoint was re-sealed.
7. Independently verify same-run MLflow again before resuming marker-last S3
   publication. Preserve matching partial objects; refuse conflicts; verify
   metadata and actual bytes. A completed repeat performs no MLflow or S3 writes.

Unsealed checkpoints, missing independent receipts/ledger or insufficient disk
space stop recovery; they do not authorize rescoring. Partial local finalization
directories are retained for diagnosis, not deleted automatically. Capacity must
cover five bounded working copies; current free space is checked before final
access and before rebuilding finalization. Cleanup may remove only reviewed
temporary copies, never the sole verified copy. Loss before the scored seal
still requires the original native workspace; this code grants no scoring retry.

## Synthetic evidence and remote observations

`serverless/jobs/g8_live_rehearsal.py` exercises `run_live`, the frozen scorer,
`LiveCheckpointLogger`, `finish_retained` and the actual conditional publisher.
It terminates the scoring process after the pre-logging seal, removes both
synthetic workspaces, terminates fresh recovery after an MLflow artifact upload,
then recovers and injects a SUCCESS-upload failure. It verifies the published
bytes, original Job identity and a zero-write completed repeat.

The synthetic harness substitutes approval inputs, native mount and remote
transport with explicit fixtures; MLflow is real but file-backed. It is not a
test of native attachment or authenticated remote writes, and uses no production
test rows. The CLI signature/mount/expiry/allowlist checks have separate negative
tests. The G8 Make target runs all of these tests and Ruff.

The [post-review pinned-image receipt](evidence/g8-live-integration-review-rehearsal-20260914.json)
records one scoring call, local MLflow run `dd651d71090044a5924600d0410ce763`,
64 byte-verified published objects, original Job identity preservation and a
zero-write completed repeat. Its publication checkpoint SHA-256 is
`799927aa33dade768743c53350bbe7eeb78df3b7555d92d80b3affac26c2bb90`.
Full temporary engineering evidence remains at
`/tmp/g8-live-review.0GVJP0/rehearsal`. Networking was disabled for this run.
This receipt binds the delivered lifecycle code and CLI hashes; CLI policy checks
were tested separately, not bypassed and then reported as live approval.
The [pre-review receipt](evidence/g8-live-integration-rehearsal-20260914.json)
is preserved as historical evidence. Eleven additional CLI regression cases cover
recovery rendering, distinct execution/retention deadlines and mount detachment,
replacement or source change during the signed-context wait on both live paths.
Final local verification: `make lightgbm-wave1-g8-check` passed **270 tests**,
Ruff and CLI smoke checks; the governed-release, canonical-evaluation-bundle and
MLflow dataset-lineage regression selection passed **15 tests**. Python 3.14
MLflow file-store deprecation warnings were non-failing.

Live read-only observation on 2026-09-14: MLflow VM
`computeinstance-e00xq8hqrzks2pf3gn` is RUNNING; MLflow, Postgres and exporter
containers are healthy. The existing governed writer authenticated and read
active experiment `3` through the VM's internal service network. No remote run
or artifact was written. Job-to-private-endpoint routing and authenticated S3/
MLflow artifact round trips still require the approved rehearsal below.

## Approved scope: synthetic native/remote rehearsal only

Operator approved **$2 maximum additional spend** on 2026-09-14, including cleanup
and stopping the existing MLflow VM afterward, subject to fresh billing reconciliation
before provisioning: stop new work at $40 campaign spend; never exceed $50 total.
The old $28.65 figure is not a current balance.

- One dedicated **10 GiB network_ssd filesystem**, at most **24 hours** retention.
- At most **two cpu-d3, 4vcpu-16gb Jobs**, each with a **1-hour timeout**, 100 GiB
  ephemeral disk, no restart, no GPU. First writes/seals synthetic evidence and
  is lost/cancelled; second reattaches and performs recovery/remote readback.
- At most **four hours of the existing MLflow VM's rehearsal uptime** included
  in the allowance. Obtain consent to stop that user-started VM at the end; do
  not assume it is disposable or delete its disks.
- A unique synthetic S3 prefix and explicitly synthetic MLflow identity, scoped
  writer credentials, private routing, negative unauthenticated-access checks,
  artifact/metric/lineage hash round trips and zero-rescoring assertions.
  No final-read credential activation, production checkpoint rows, production
  scoring, training experiments or model selection.
- Archive verified synthetic receipts, revoke temporary attachment/write access,
  and remove only this rehearsal's temporary Jobs/filesystem after verifying
  independent copies. Cleanup owner: approving operator with Codex execution;
  deadline: creation +24h. Escalate if cleanup or billing reconciliation fails.

Published list-price estimate checked 2026-09-14: CPU $0.012/vCPU-hour,
RAM $0.0032/GiB-hour, SSD disk $0.071/GiB/730h and shared filesystem
$0.08/GiB/730h. Two full Job hours including disks are about $0.218;
10 GiB filesystem for 24h about $0.026; MLflow 2vCPU/8GiB plus 32GiB disk for
four hours about $0.211: **about $0.46 infrastructure subtotal**, before network,
object requests and other applicable charges. The $2 cap provides headroom, not
a provider-enforced billing cap. Check current project-specific rates and spend
before starting; do not proceed if the quoted scope cannot fit.

Sources: [Compute pricing](https://docs.nebius.com/compute/resources/pricing),
[Serverless billing](https://docs.nebius.com/serverless/pricing-quotas),
[native Job mounts](https://docs.nebius.com/serverless/jobs/manage),
[filesystem durability/encryption](https://docs.nebius.com/compute/storage/types).

This approval does **not** approve the replacement final test.
After rehearsal and original-checkpoint metadata verification, assemble/review
the actual production package and request its distinct signed exception.

### Post-merge preflight and required operator action

PR #178 merged as `0742225b00f185bc9f98980a947e7ec29d5ec378`; all its checks
passed. The new rehearsal branch starts at that commit. The
[preflight record](evidence/g8-native-rehearsal-preflight-20260914.json)
records the approved bounds, observed project billing of **$33.49 including VAT**,
healthy MLflow containers, no native filesystems and the inactive final-read key.
After finding the operator-action gate, MLflow VM
`computeinstance-e00xq8hqrzks2pf3gn` was stopped under the approved cost-control
scope and independently read back as **STOPPED**, resource version **38**.
Its disks and recorded MLflow evidence were not deleted. Restart only when the
remaining prerequisites permit the bounded rehearsal.
Billing is provider-lagged (last updated 13:52 UTC), not a real-time spend receipt;
refresh it and reconcile accrued charges immediately before submission.

No rehearsal Job, filesystem, MLflow run or S3 object was created during this
preflight. The operator applied the output policy, and independent
[readback](evidence/g8-native-rehearsal-output-access-readback-20260914.json)
confirmed bucket version **6** and exactly the eight expected rules. This closes
only the output-permission gate, not the synthetic-input or submission gates.
Do not activate the production final key or put rehearsal outputs inside an
existing production campaign.

Nebius MCP safe mode does not permit policy updates or cleanup deletions through
that connector. The initial output update was performed manually by the operator.
The operator subsequently explicitly requested execution of the two source-read
CLI commands and approved each exact update through terminal escalation. Only
those two commands were executed under that separate authorization; the connector
configuration was not changed and no broader mutation authority was inferred. The
[prepared policy patch](evidence/g8-native-rehearsal-policy-grant-20260914.json)
preserves all seven existing rules and adds only the existing development
group's object-editor access to:

- `campaigns/g8-native-rehearsal-20260914/final/synthetic-final/*`
- `campaigns/g8-native-rehearsal-20260914/final/.intents/synthetic-final.json`

This output-only patch grants no final-input bucket access, anonymous access or bucket-wide role.
It uses the active development identity; existing credentials must never be
printed or committed. This policy change does not itself validate credentials,
Job routing, native durability, comparison evidence or remote artifact recovery.

The original patch is preserved as historical evidence, bound to resource
version **5**. It has already been applied: **do not run it again**.
The command intentionally supplies only policy flags: the CLI's `--file` option
defaults updates to full-resource replacement and must not be used for this
partial policy document.

### Review correction: synthetic source read access

The first access package omitted two required reads. `run_live` always downloads
the candidate and the request input release before scoring. Output/intent access
alone is insufficient, and the offline harness's mocked downloads are not
evidence that the real Job can read its inputs. **Do not submit either paid Job
until all source staging and authenticated readback gates below pass.**

Use the same active development identity, never the production final-read key,
with the following separately scoped, temporary **read-only** additions:

| Bucket | Exact permitted synthetic source | Role |
| --- | --- | --- |
| Results | `campaigns/g8-native-rehearsal-20260914/development/synthetic-development/*` | `storage.viewer` |
| Final inputs | `releases/g8-native-rehearsal-20260914/staging/*` | `storage.viewer` |

The final bucket grant is only for the newly generated synthetic release; it
does not grant the development group `releases/*`, access to the real C4 release,
or any write permission. The pre-existing final-identity rule remains unchanged.
The production final-read key must remain inactive throughout rehearsal.

The [candidate-read patch](evidence/g8-native-rehearsal-candidate-read-20260914.json)
preserves the eight current results rules and is guarded by version **6**.
The [synthetic-input-read patch](evidence/g8-native-rehearsal-input-read-20260914.json)
preserves the final bucket's existing rule and is guarded by version **3**.
Both source-reader grants were applied on 2026-09-14 under explicit user/terminal
approval. Independent [readback](evidence/g8-native-rehearsal-source-access-readback-20260914.json)
verified results bucket version **7** (nine rules) and final-input bucket version
**4** (two rules), with exact policy matches and all other bucket settings
preserved. The original output grant was not rerun.

The following commands are retained as execution history: **do not rerun them**.

```sh
rtk proxy nebius storage bucket update --id storagebucket-e009132243970085528999 --resource-version 6 --patch --bucket-policy-rules "$(rtk proxy jq -c '.spec.bucket_policy.rules' docs/evidence/g8-native-rehearsal-candidate-read-20260914.json)" --format json
rtk proxy nebius storage bucket update --id storagebucket-e004963828556923796882 --resource-version 3 --patch --bucket-policy-rules "$(rtk proxy jq -c '.spec.bucket_policy.rules' docs/evidence/g8-native-rehearsal-input-read-20260914.json)" --format json
```

If either version changed, stop; re-read that bucket and preserve concurrent
changes before regenerating its patch. If only one command succeeds, retain that
partial state and reconcile it; do not blindly repeat both. Independently read
back both complete policies before using them.

Submission gates, in order:

1. Generate the synthetic candidate, four-date C4-shaped input and synthetic
   comparison package locally in the pinned runtime. They must contain no
   production rows or production candidate, and retain their request/profile/
   manifest/byte hashes. Use campaign `g8-native-rehearsal-20260914`, candidate run
   `synthetic-development`, and scoring run `synthetic-final`.
2. Stage the two complete synthetic source releases at the exact paths above
   with separately reviewed, exact-prefix staging authority. The rehearsal
   reader grants do **not** authorize staging writes. Publish manifests and
   checksums with `SUCCESS` last; do not treat missing sources as an IAM problem.
   Source staging and its writer-access setup are still outstanding.
3. Using the version-pinned credentials intended for the Job, authenticate and
   download/verify both complete synthetic releases against the retained hashes.
   Verify denial for a known production C4 object without downloading its body.
   Record exact source URIs, marker/manifest hashes, credential selectors and
   observation time. A policy readback or empty-prefix listing is not proof.
4. Bind that evidence, native mount plan, comparison inventory, current billing,
   remote MLflow credentials and actual injected runner to the reviewed rehearsal
   package. Do not run the offline mocked-transport harness as if it were a live
   remote rehearsal. No live rehearsal package is declared ready by these patches.
5. Only then provision/submit within the existing two-Job and USD 2 bounds, and
   retain/recover the same scored checkpoint without rescoring.

For cleanup, the operator must remove only the added output rule and the two
synthetic source-reader rules (plus any separately approved staging rules) using a fresh
resource-version-guarded patch, preserve all baseline/concurrent rules, and
manually delete only the identified temporary rehearsal resources after
independent evidence copies are verified. Existing development credentials and
MLflow disks are not disposable rehearsal resources. The rehearsal cannot start
until this operator step and the remaining live preflight checks are complete.
