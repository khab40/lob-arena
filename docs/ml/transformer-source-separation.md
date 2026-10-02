# Transformer source-domain separation — 2026-10-02

Story [#24](https://github.com/khab40/lob-arena/issues/24),
Feature [#16](https://github.com/khab40/lob-arena/issues/16),
Epic [#15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).
Continues the approved [campaign plan](transformer-gpu-campaign-plan.md) after
merged [PR #271](https://github.com/khab40/lob-arena/pull/271).

As a validation engineer,
I want source observations and label windows bound to complete development roles,
So that selection, calibration and operating-point selection cannot reuse them.

Actor: validation engineer. Goal: verify the frozen C4 instrument-local source and
label contract. Value: resolve this readiness gate using authenticated retained
evidence. Acceptance scenarios are in [the feature specification](transformer-source-separation.feature).
Out of scope: payload enumeration, class-support measurement, statistical
independence, new source groups, cloud access and model execution. Verification:
reviewed producer source, inert mutation tests, offline authentication of the
frozen anchor and all 115 retained metadata objects, and independent readback.

## Result and exact scope

The [verification receipt](../evidence/transformer-source-separation-20261002.json)
records source-observation and label-horizon separation under the reviewed
producer contract. It binds the producer commit/image, frozen anchor, metadata
receipts, role manifest and feature-release ID/hash. All 30 validation runs retain
their predeclared roles; the verifier does not regroup after inspecting labels.

| Role | Instrument | Runs | Supervised rows | Synthetic label windows |
| --- | --- | ---: | ---: | ---: |
| Selection | NVDA | 10 | 1,250 | 9 |
| Calibration | MSFT | 10 | 5,490 | 9 |
| Operating-point selection | AAPL | 10 | 2,470 | 9 |
| Total | Three instruments | 30 | 9,210 | 27 |

Each group includes its control replay and all nine family/seed variants.
Source-observation identity uses the source-file hash and global source sequence.
The reviewed parser routes each observation to one instrument and maintains
separate books. The separation domain conservatively includes that instrument's
**entire source-file ancestry**, including book state accumulated before the
requested 10:00–10:30 interval. Different windows, parser hashes, replay hashes or
run identifiers cannot divide the same instrument domain between roles.

Labels are pointwise `attack_active` labels in producer tick coordinates. Each
hybrid has one inclusive tick window; controls have no synthetic window. A label
inherits its replay's entire instrument domain. This proof does not infer exact
label timestamps or multiply ticks by the manifest's `tick_interval_ns` field:
historical replay advances by source-record batches, not a fixed wall-clock step.

The public verifier reauthenticates retained bytes before interpreting them and
rejects changed producer identities, source filters, unsupported label semantics,
missing/duplicate runs and divided domains. It rejects an existing output path
and publishes no success receipt after a failed proof. This increment makes
**zero cloud reads, payload reads or model runs**; it does not enumerate the
payload's individual source-observation IDs again.

Initial verification passed 232 focused inert tests, including 97 new contract cases.
Independent review found no P1/P2 issues and reproduced the 4,663-byte receipt
exactly in 0.062 seconds. Source, label and orchestration boundary cases are in
`test_transformer_source_contract.py`, `test_transformer_label_domain.py` and
`test_transformer_source_separation.py`. The lineage-result checksum hashes
canonical JSON; the evidence also retains the earlier pretty-printed file's checksum.

[Bug #273](https://github.com/khab40/lob-arena/issues/273) repairs the initial CI
collection failure: the metadata helper imported NumPy through the row adapter.
Its constants now come from the standard-library-only specification. A Python
`-S` regression proves import without site packages; the existing ML CI step
explicitly runs all three new suites. Source roles and receipt bytes are unchanged.

The [review correction](../evidence/transformer-source-review-20261002.json) for
[Bug #274](https://github.com/khab40/lob-arena/issues/274) fixes a reproduced partial
receipt after a failed write. Publication now stages complete bytes, checks the
write length, flushes, synchronizes and closes before exclusively linking the
final filename. Existing or concurrently created evidence cannot be replaced.
Only this invocation's temporary file is cleaned; if cleanup fails after successful
publication, the command reports the temporary alias and preserves the complete
receipt. Atomic visibility is verified; power-loss directory durability is not claimed.
Fifteen new fault/CLI cases and all 247 focused tests pass. Independent CLI readback
reproduces the original receipt unchanged. The P1 size finding counted the whole
PR: at reviewed head `3354f59`, its nine commits each changed at most 166 lines.

## Producer semantics reviewed

The metadata binds producer commit
`cf426c0db0940a985133fc7c8482623186acd5a4` and its immutable image digest.
The local Git object at that commit supplies the reviewed source:

- [ITCH normalization and symbol-local warm-up](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/backend/app/data_ingestion/itch.py#L485)
  routes records to one symbol and updates its book before applying the output window.
- [Replay export](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/backend/app/market_data/replay_export.py#L140)
  binds ground truth to run/campaign and emits one dataset/instrument/session manifest.
- [Historical replay advancement](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/java/control-plane/src/main/java/ai/lobarena/controlplane/LiveArenaService.java#L794)
  advances batch ticks using source timestamps; its
  [ground-truth producer](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/java/control-plane/src/main/java/ai/lobarena/controlplane/LiveArenaService.java#L1465)
  records run-local attack windows.
- [Label construction](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/backend/app/features/io.py#L166)
  consumes tick bounds; [label assignment](https://github.com/khab40/lob-arena/blob/cf426c0db0940a985133fc7c8482623186acd5a4/backend/app/features/models.py#L179)
  tests the prediction's own tick without adding a future horizon.

## Limitations and next steps

All roles share October 30, 2019 market time. Temporal separation is false and
statistical independence is unproven. There is one instrument per role, shared
synthetic templates and seeds, and prior development exposure. Repeated scenario
identifiers are scoped by replay/campaign; they do not imply independent attacks.
Negative labels remain `research_control_assumption`, with
`independently_verified_clean=false`. Row counts do not measure independent
observations or per-role positive/negative class support.

1. Complete the signed CPU role-audit package, obtain exact execution approval,
   then independently verify class support and exact row alignment. The existing
   campaign guard requires at least 20 positives and 20 negatives in each role.
2. Complete MLflow and platform readiness under
   [#19](https://github.com/khab40/lob-arena/issues/19)–[#21](https://github.com/khab40/lob-arena/issues/21),
   including application permissions, artifact round trips and recovery evidence.
3. Present the immutable bounded GPU package for separate execution authorization
   only after the required readiness gates pass.

Story #24 remains in progress. Class support, GPU readiness and execution
authorization remain false. G8/G9 remain closed.
