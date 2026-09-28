# Transformer development inputs verified — 2026-09-28

[Story #24](https://github.com/khab40/lob-arena/issues/24) /
[Bug #238](https://github.com/khab40/lob-arena/issues/238), Feature #16 → Epic #15,
[Project #3](https://github.com/users/khab40/projects/3).

**The approved r2 CPU verification passed and its S3 package was independently
read back.** The [acceptance receipt](../evidence/transformer-development-acceptance-r2-20260928.json)
binds the approved proposal, source/image, actual Job, feature release, artifact
versions/checksums, row identities, measurements and released resources.

## Verified behavior

- Exactly 185 approved object versions / 30,034,660 bytes downloaded in 185 GETs.
- All 33,450 training and 9,210 validation target rows consumed per pass.
- Causal windows, padding/attention masks, missingness, exact source-feature
  equality and ordered baseline-row identities passed the governed input checks.
- Normalization fitted 33,450 unique training targets. Its fitting-row digest
  matches the measured training-row digest; validation did not enter fitting.
- Batch sizes 16, 64 and 256 produced identical normalization and input-contract
  bytes, per-fold row digests and logical-output hashes.
- All six result artifacts passed version-specific S3 readback and checksum/
  lineage verification in a separate inspection process. SUCCESS is bound to the
  checksum in the provider Job log, independently of the S3 checksum inventory.

The normalizer, input contract, configuration, measurements, inventory reference
and lineage total 50,671 bytes. Their immutable version IDs and hashes are in the
receipt. Exact feature-release ID/hash and the retained MLflow dataset-lineage
receipt are bound; this run creates no MLflow run or registered model.

## Measured resource use

Job `aijob-e00avfmh58qjzav9tr` ran on 4 vCPU / 16 GiB with a 100 GiB ephemeral
disk. Container duration was **496.63 seconds (8 minutes 17 seconds)**.

| Batch size | Full check (seconds) | Batching + digest (windows/second) | Peak process RSS (MiB) |
| --- | ---: | ---: | ---: |
| 16 | 152.35 | 763.29 | 122.12 |
| 64 | 150.88 | 760.40 | 131.90 |
| 256 | 151.48 | 764.24 | 176.89 |

Full checks include preflight, normalization fit and batching/digest work. These
are three separate fresh-process observations, not repeated statistical estimates
or model/GPU throughput. Peak RSS covers each measurement process, not host-wide
memory. Per-phase times and runtime versions remain in the receipt.

Provider state is COMPLETED. Subsequent Compute API reads return ResourceNotFound
for both worker and ephemeral disk. Monetary cost remains unknown under the
approved operator-managed policy; no billing query or persistent resource was added.

## Repair acceptance and remaining scope

The publisher was armed before create. Matching INTENT appeared at 12:33:41 UTC;
signed context arrived at 12:33:43, a two-second handoff. Its signature and actual
Job binding independently verify. This satisfies #238's runtime acceptance;
the failed r1 evidence remains preserved and no automatic rerun occurred.

The development input/preprocessing chunk is complete. Wider #24 remains open:
next propose the smallest GPU Transformer classifier, bounded training/checkpoint
selection, validation/calibration and MLflow artifact/config logging. No Transformer
has been trained, and no model quality or production qualification is claimed.
Synthetic-positive/research-control label limitations remain. G8/G9 stay closed;
the previously inspected final fold is not a new untouched evaluation set.
