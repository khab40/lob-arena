# Transformer seed 7 — startup failure, 4 October 2026

**No training result.** The approved Job failed while waiting for signed
execution context. It never reached governed input download or model training;
there are no epochs, loss curves, checkpoints or metrics to report.

[Bug #306](https://github.com/khab40/lob-arena/issues/306), under
[Story #24](https://github.com/khab40/lob-arena/issues/24) in
[Project #3](https://github.com/users/khab40/projects/3).
[Machine-readable evidence](../../../evidence/transformer-confirmation-failure-20261004.json).

| Item | Observed value |
| --- | --- |
| Requested configuration | Width 128, learning rate 0.0003, seed 7 |
| Nebius Job | `aijob-e00k6zkjr3hqc15dhb` |
| Resource | 1 L40S, 8 vCPU, 32 GiB RAM, 100 GiB disk |
| Created / started / finished (UTC) | 06:38:38 / 06:42:23 / 06:47:25 |
| Provider runtime | 301.78 seconds |
| Terminal state | FAILED, ContainerFailed |
| Worker error | TimeoutError at context delivery |
| Local attester error | AttributeError; original stage/frame not retained |
| Output keys | INTENT and FAILED only |

The operator approved proposal `8aa272fe9c16fc5cd50fa16e3b29ebc448f93ff1a7196b319a934dc8031a7871`
and a $25 additional cap excluding VAT. The exact request and fresh read-only
availability/rate checks passed; one create was submitted. The helper exited
without publishing context and the worker stopped after its five-minute wait.
Seed 2027 was not submitted. Neither Job creation nor publication was retried.

The saved provider specification validates offline; the retained INTENT exactly
matches the approved request. A bounded diagnostic read confirms the context
object is absent and returns ordinary NoSuchKey. Malformed transient provider
or exception shapes can reproduce AttributeError in inert probes, but none is
proven to have caused this incident. The original failing line remains unknown.

The terminal Job no longer bills compute. Created-to-terminal compute/disk time
estimates approximately $0.23, excluding other charges; actual billing is not
reconciled. Keep the full $12.50 reservation committed. This failure gives no
evidence about Transformer quality and does not invalidate the verified grid.

Next: repair safe stage/frame diagnostics and test startup transitions; review
and pass CI; prepare a fresh replacement identity and exact authorization.
Do not restart this consumed slot, launch seed 2027, loosen context validation,
or claim the underlying AttributeError cause is resolved by diagnostic changes.

The repair emits `attester_ready` after SDK/authentication and custody checks,
then flushed progress and safe failure stage/type/code-frame records. A future
execution handoff must retain stdout as JSONL, require readiness plus a live
helper, use an explicitly reviewed asynchronous create command, and monitor
both helper and provider until context delivery completes. Helper exit blocks
creation or stops the sequence; cancellation of an already-created Job needs
the exact proposal's bounds-enforcement authority. These steps are not a new
execution authorization and have not been exercised on another cloud Job.
