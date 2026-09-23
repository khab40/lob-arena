# G8 final results and G9 handoff — 2026-09-23

Tracking: [story #23](https://github.com/khab40/lob-arena/issues/23),
[PR #223](https://github.com/khab40/lob-arena/pull/223),
[Project #3](https://github.com/users/khab40/projects/3).

**G8 execution, independent verification and cloud cleanup are complete.**
The [execution receipt](../../evidence/g8-final-execution-20260923.json) records
the separately approved replacement Job `aijob-e00kd6g7vaqtngwv9r`, completed
at 09:41:25 UTC after 8,749.50 seconds, within its 10,800-second limit.
Exactly one replacement Job and one scoring invocation ran. Candidate, features,
model, calibration and balanced threshold `0.5769230769230769` remained frozen.
The signed runtime source is `14a4d1a6b0931c822995224d2a5e8d657538e1e6`;
later PR commits record evidence and guidance, without changing the executed bytes.

## Measured quality

The held-out C4 result covers 15,160 retained observations across AAPL/MSFT/NVDA
on 2019-12-30, including 27 observed attack campaigns. Positive labels come from
synthetic scenarios; negative labels are research-control assumptions.

| Retained-observation metric | Frozen LightGBM | Original Rules |
| --- | ---: | ---: |
| True positives | 89 | 135 |
| False positives | 15 | 14,985 |
| False negatives | 46 | 0 |
| True negatives | 15,010 | 40 |
| Precision | 85.58% | 0.89% |
| Recall | 65.93% | 100% |
| F1 | 74.48% | 1.77% |
| Observed-campaign recall | 100% | 100% |

LightGBM reduces false-positive observations by 99.90%, while missing 46 of 135
positive observations. Campaign recall means at least one detection in each
observed campaign; it does not imply complete detection of its positive rows.
Family recall is 62.22% for layering-like, 61.11% for quote stuffing and 77.78%
for spoofing-like walls. Frozen isotonic calibration improves Brier score from
0.013852 to 0.004401 and ECE from 0.058173 to 0.004506 on this held-out sample.

These measurements do not establish seven-date benchmark compliance, production
acceptance or client surveillance performance. Precision and recall are below
90%; retain that limitation without changing thresholds after observing test
results. No confidence interval or wider-date generalization claim is established.

## Independent verification and cleanup

The [independent receipt](../../evidence/g8-final-verification-20260923.json) binds:

- All 176 published S3 objects (24,463,251 bytes), exact hashes and sizes,
  `SUCCESS`/checksum inventories, and equality of scored and published artifacts.
- Final MLflow run `e4e5d9ff757a4587bcd6d01bcd33df06`: FINISHED, four artifact
  hashes, 30 full dataset identities, and 24 metrics each recorded once at step 0.
- Candidate, request, Job, evaluation profile and exact feature-release ID/hash.
  The selected development run's seven artifacts remain covered by
  [PR #219's lineage verification](../../ml/lightgbm-lineage-verification.md).
- Independent aggregate arithmetic, family recall and reliability-bin ECE checks.
  Readback performed no scoring, retraining or cloud writes.
- Final key INACTIVE, temporary SSH rule absent, Job worker released and MLflow
  VM STOPPED. Native evidence and the existing 32 GiB filesystem remain retained.

The first scoring/comparison stage took 4,085.12 seconds wall and 4,011.82
CPU-seconds, with 354,996,224 bytes peak RSS. Its measured 3.711 observations/sec
includes comparison work and is not pure inference latency or whole-Job throughput.
Whole-Job duration was 2h25m49.50s on 4 vCPU / 16 GiB RAM / 100 GiB disk.
Whole-Job peak memory and billed cost are not established by the stage measurement.
The provider mount warning remains unexplained; actual mount checks, durable
native output and complete independent publication readback passed.

## Remaining G9 decision

1. Review this research baseline's quality, coverage and resource limitations.
2. Record the operator-provided cost disposition under the
   [execution policy](../../ml/model-validation-execution-policy.md); no billing
   API query or fresh budget gate is required by this evidence update.
3. Obtain the signed Wave 1 exit disposition. Wave 2 remains gated until that
   decision permits it; G8 completion does not itself qualify production use.

This is an unsigned G9 handoff, not an operator exit decision. Any future model
improvement uses permitted development data and fresh untouched held-out data;
the completed final evaluation is not a tuning dataset or retry opportunity.
