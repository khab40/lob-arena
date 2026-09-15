# G8 replacement integration and approval gates

Next implementation slice: [native-storage and MLflow rehearsal package](g8-native-rehearsal-package.md).
The source capsule is prepared; native entrypoint and execution bindings remain open.

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

### Synthetic sources prepared on 2026-09-15

Following merged PR #179 (`5bf5c3d`),
`serverless/jobs/prepare_g8_native_sources.py` separates fixture preparation from
the mocked-transport evaluation harness. It trains only synthetic development,
creates the four-date-shaped final input plus all 27 original synthetic
comparison checkpoints, and seals a portable package. It neither submits Jobs
nor invokes final scoring, S3 transport or MLflow logging. The synthetic lineage
receipt deliberately remains a contract placeholder, **not a remotely registered
MLflow dataset**. Its ephemeral authorization key cannot approve the production
candidate. Production execution policy and its runner are unchanged.

The [pinned-runtime execution receipt](evidence/g8-native-source-preparation-20260915.json)
records successful preparation and fresh-container verification with networking
disabled. The second container mounted only the package read-only at a different
path; the original build workspace was unavailable. It verified 356 payload
files (2,652,554 bytes), 27 checkpoints, 30 replay domains and 198 synthetic test
rows without training or rescoring. This proves local source-package portability,
**not native Job-loss durability or authenticated remote recovery**.

The retained package is `outputs/g8-native-sources-reviewed-20260915` in this worktree
(ignored by Git); the independently retained package SHA-256 is
`792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9`.
The candidate and complete input releases ready for staging are respectively
`payload/sources/candidate` and `payload/sources/input`. The input includes
`comparison-evidence`; C4 paths in `payload/c4-inputs.json` are fixed relative
paths. Both releases already have locally verified `SUCCESS`/checksum envelopes.
No S3 object was staged and no existing grant was rerun.

To reproduce inside the pinned image, inject the three reviewed scripts
(`prepare_g8_native_sources.py`, `g8_rehearsal.py`, `run_lightgbm_g8.py`) in one
read-only script directory, and overlay these six modules read-only at
`/job/backend/app/ml/lightgbm/`: `tracking`, `c4_evaluation`, `c4_replay_evidence`,
`g8_benchmark_readiness`, `g8_c4_fixture`, `g8_publication_recovery`. Set
`PYTHONDONTWRITEBYTECODE=1`, `--network none`, `--platform linux/amd64` and
`--entrypoint python`. The receipt binds all nine file hashes. Run the following
arguments (the first output directory must not already exist):

```text
/rehearsal/prepare_g8_native_sources.py --output /evidence/prepared
```

Retain the emitted hash independently. Start a fresh container with only
`prepared/package` mounted read-only as `/relocated`, plus the same code, and run:

```text
/rehearsal/prepare_g8_native_sources.py --output /relocated --verify --expected-sha256 <retained-package-sha256>
```

The next gates remain: review this implementation; prepare separately reviewed
exact-prefix staging-writer authority and conditional, marker-last publication;
verify complete downloads with the pinned Job credentials and a production-object
HEAD denial; finish the actual native/remote rehearsal package; then refresh
billing and run within the existing two-Job/$2 approval. Do not run the ordinary
nonconditional input publisher or activate the final-read key as a shortcut.
The previous source-read grants are already applied and must not be rerun.

Validation for this source-preparation change: `make lightgbm-wave1-g8-check`
passed **283 tests**, Ruff and CLI smoke checks. This includes twelve new source
tests for no final scoring/MLflow logging, relocation without the original build,
tamper and symlink rejection, fixed portable C4 paths, output preservation,
synthetic-only campaigns, relative output paths and rejection of R4's wrong
projection layout. The two SDK retry tests required local loopback permission;
the initial sandbox-only run's socket-bind failures were environmental.

### Conditional source staging implementation (2026-09-15)

PR #181 merged as `546c95e`; the next branch starts from that updated main.
`stage_g8_native_sources.py` defaults to local verification. `--publish` accepts
only the two source URIs in the sealed synthetic package. It validates both
remote prefixes before its first write, preserves matching partial uploads,
uses `If-None-Match: *` with a private hash-checked copy for every PUT, and checks
all payload bytes before each top-level `SUCCESS`. Ambiguous PUT responses are
resolved by readback, never by overwriting or deleting. Repeating a completed
publication makes zero PUT calls. Production publication/recovery code is not
changed; its bounded transfer subprocess is reused without passing unsupported
keywords to the frozen `_aws_json` helper.

`--readback --destination <new-directory>` downloads every synthetic source
object, preserves the bytes locally, rechecks the complete remote inventories
and verifies the candidate, projection and 30 comparison domains. The six
non-source package metadata files are explicitly copied from the retained local
package, not represented as S3 downloads. It then issues only HEAD for the known
production frozen-root object. Only explicit 403/AccessDenied/Forbidden counts
as denial; 404, invalid key/signature, timeout and successful access all fail.
No production object body is requested. Failed readbacks remain for diagnosis;
their directories must not be overwritten or counted as successful receipts.

Credentials must be explicitly supplied through the process environment; the
tool never retrieves secrets, uses profile/instance-role fallback, changes IAM,
creates Jobs, scores or writes MLflow. It records a hash of the access-key ID,
not the key or secret. Environment credentials alone do **not** prove which
MysteryBox versions were injected. Receipts therefore explicitly leave
`pinned_job_credentials_verified`, native durability and remote MLflow false.
The approved Job/secret-injection readback must establish that separate binding.

Operator-reviewed invocation inside the pinned image, with the same six module
overlays listed above and the additional `stage_g8_native_sources.py` script:

```text
/rehearsal/stage_g8_native_sources.py --package /package --expected-sha256 792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9
/rehearsal/stage_g8_native_sources.py --package /package --expected-sha256 792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9 --publish
/rehearsal/stage_g8_native_sources.py --package /package --expected-sha256 792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9 --readback --destination /evidence/source-readback
```

Only the first command is offline. The other two require reviewed networking,
approved credentials and source-write setup below. Mount `/package` read-only;
retain emitted receipts independently. Neither command starts the evaluation.

#### Proposed temporary staging-writer permission — not applied

Fresh Nebius readbacks still show results bucket version **7** and final-input
bucket version **4**. The [proposal](evidence/g8-source-staging-access-proposal-20260915.json)
preserves those entire existing policies and adds one `storage.object-editor`
rule per bucket, for development group `group-e00wb5ptvpq0q7dpaf`, on exactly:

- `campaigns/g8-native-rehearsal-20260914/development/synthetic-development/*`
- `releases/g8-native-rehearsal-20260914/staging/*`

This temporarily adds source-write authority to the existing development
identity; it does not create a new writer identity. It grants no production
final access or bucket-wide access. The role also permits deletion, but the
staging code never performs it. This new authority requires explicit operator
approval. MCP safe mode cannot apply it; use operator-run CLI or separately
approved terminal execution. **Do not rerun any historical output/reader grant.**

After approval and immediately refreshed version/policy checks, the proposed
partial updates are:

```sh
rtk proxy nebius storage bucket update --id storagebucket-e009132243970085528999 --resource-version 7 --patch --bucket-policy-rules "$(rtk proxy jq -c '.buckets[0].proposed_update.spec.bucket_policy.rules' docs/evidence/g8-source-staging-access-proposal-20260915.json)" --format json
rtk proxy nebius storage bucket update --id storagebucket-e004963828556923796882 --resource-version 4 --patch --bucket-policy-rules "$(rtk proxy jq -c '.buckets[1].proposed_update.spec.bucket_policy.rules' docs/evidence/g8-source-staging-access-proposal-20260915.json)" --format json
```

If a version or policy differs, stop and reconcile concurrent changes; never
reuse these stale arrays. Read back both applied policies before publication.
Allow only one staging session; revoke the two appended writer rules within
one hour and **before any rehearsal Job**, preserving the reader/output rules.
This is an operator-enforced window, **not automatic IAM expiration**. Cleanup
requires fresh GETs and their resource versions, removing only these exact
appended rules and preserving concurrent changes. Verify viewer-only source
access afterward, then do the authenticated reader check. Partial grant or
staging failure requires reconciliation/cleanup, never a broader grant.

No new grant, S3 upload, remote MLflow run or paid resource was created while
preparing this change. Review and grant approval remain the next live gate.

The [pinned-runtime protocol receipt](evidence/g8-source-staging-frozen-rehearsal-20260915.json)
records 350 verified synthetic source objects, 349 retained through an injected
top-level marker failure, 30 reverified comparison domains and zero PUTs on a
completed repeat. `g8_source_staging_rehearsal.py` uses the same retained package
read-only, simulates only S3 transport, and runs with networking disabled. Its
denial response is simulated; **no real authenticated S3 or native-storage result
is claimed**. No candidate was retrained or final fold rescored by this protocol
rehearsal. Validation: the full G8 target passed **301 tests**, Ruff and smoke
checks; after adding the final inventory-race regression, all **19 staging tests**
passed. The final two-line remote-inventory recheck also passed the repeated
pinned-image protocol rehearsal. Concurrent docs/password-helper PR #182 was
fast-forwarded into this uncommitted branch before delivery; it changed none of
these runtime paths.

### Approved staging window closed (2026-09-15)

The operator approved the two temporary source-writer rules after PR #183 merged
as `3861df4`. Both rules were applied and independently read back: results bucket
**7 → 8**, input bucket **4 → 5**. The publication ran only against the approved
synthetic prefixes using the exact development MysteryBox versions resolved
directly into process memory. No secret values were printed or persisted.

Publication was stopped proactively after the frozen x86 AWS CLI, running
through Rosetta on this Mac, spent over six minutes verifying the 25-object
candidate source. At that observed throughput, the full 350-object sequential
publication was unlikely to fit the one-hour window. This was an operator stop,
not a model evaluation failure or a reached timeout. All uploaded objects were
preserved; no retry of scoring/training occurred.

Both temporary rules were removed, with cleanup independently verified:
results **8 → 9**, input **5 → 6**. The full original bucket specs and their
reader/output rules match the pre-grant state. The conservative permission
window was **445.857 seconds (7 minutes 26 seconds)**, from
`2026-09-15T04:12:14.376560+00:00` to
`2026-09-15T04:19:40.264690+00:00`. No cloud Job was created. The historical
version-7/version-4 staging grant commands above must **not** be rerun.

The [closed-session receipt](evidence/g8-source-staging-session-20260915.json)
contains the actual post-grant GET snapshots (`policy_checks[].independent_granted`)
retained from the session audit, the post-revocation GET snapshots
(`independent_after`), and subsequent authenticated, read-only candidate
verification. Grant verification is checked against each reviewed proposal:
the complete applied spec must equal the baseline spec with only its proposed
bucket policy substituted. Tests also bind bucket identities, resource versions
and readback timestamps, and reject missing snapshots, changed baseline rules,
extra or broadened writer rules, and unrelated bucket-setting changes. The local
audit path is supplemental; these policy claims do not depend on that uncommitted
file. After revocation, the reader downloaded and hash-checked all
**25 candidate objects / 343,345 bytes**, including the matching `SUCCESS` and
frozen candidate `e04f50ff0748a0077c0602c397ed7c9c3087757fe0892f1a2d284e91b2383b7c`.
This is the isolated **synthetic** candidate, not the production model. Exact
MysteryBox version selectors and the access-ID digest match across staging and
readback. The production final-read key remains inactive; production-object
HEAD was explicitly denied, and no production object body was downloaded.

The synthetic input prefix is still empty. The full source staging gate,
native-storage proof and remote MLflow proof therefore remain open. Preserve
the complete candidate release and resume conditionally; do not overwrite it or
regenerate the retained fixture package. Before another writer window, review a
bounded transport that avoids per-object emulated CLI startup overhead, then
obtain fresh approval and current resource-version-guarded policy readbacks.

### Synthetic source staging closed (2026-09-15)

Following merged PR #187, the operator approved one input-only writer window.
The [completed session](evidence/g8-input-staging-session-20260915.json) records
325 conditional input PUTs, zero candidate PUTs, and verified policy restoration
within 397.215 seconds (input bucket **6 → 7 → 8**). A fresh container independently
downloaded and verified all 350 source objects after revocation, checked 30 replay
domains and confirmed production-object HEAD denial. Full GET snapshots and
publication/readback receipts are checksum-bound in the session record.
The frozen package and both source `SUCCESS` identities are preserved.

Source staging and operator-side authenticated downloads are complete. The next
gate is the reviewed native/remote package and fresh billing reconciliation before
the previously approved two-Job/$2 rehearsal. Future synthetic rehearsals and
pre-production model/runtime tests run on Nebius Serverless, per the operator's
2026-09-15 instruction. No native or remote-MLflow proof is claimed yet; G8 remains
open and G9 blocked. Historical staging grants must not be rerun.
