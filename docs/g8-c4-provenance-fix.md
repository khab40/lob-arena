# PR #171 C4 provenance finding — fix verification

Outcome: fixed in the shared MLflow report intake; no live G8 execution.

## Boundary and strategy

The bundle CLI forwarded user-supplied `--benchmark-results` JSON to
`log_governed_evaluation_run`. A copied prediction identity and self-asserted
`same_observations_verified` flag were enough to publish fabricated C4 metrics
and candidate/profile identities. Repeated reads also allowed the uploaded file
to differ from the validated content.

The invariant is now enforced at the shared logger, not only one CLI: C4 reports
require evidence locations and an independent `evaluate_c4_release` invocation.
The entire report must match the recomputed canonical JSON SHA-256. The existing
evaluator binds candidate/model, frozen root, projection and original comparison
evidence. Postprocessing source identities additionally require a verified
complete scored source result with the exact prediction manifest. No new
caller-controlled verification flag, unsigned receipt or hash-only bypass exists.

Schema downgrades/wrappers carrying C4 claims and duplicate JSON keys are rejected.
Metrics, tags and uploads use a single private byte snapshot; the exact uploaded
report hash is logged. Legacy metric documents, no-report cloud logging, null
metrics, dataset lineage and the postprocessing report's source fields remain
supported. The CLI adds `--c4-evaluation-inputs`; paths resolve relative to that
manifest. See [the contract](g8-c4-evaluation-contract.md) for required fields.

Changed implementation: `backend/app/ml/lightgbm/tracking.py`,
`backend/app/ml/lightgbm/c4_evaluation.py`, `scripts/lightgbm_v1.py`.
Regression tests: `backend/tests/test_c4_tracking.py`.

## Ordered verification

1. **Syntax and integration:** focused `ruff check` for all four changed Python
   files and `git diff --check` passed; `lightgbm_v1.py bundle --help` exposes the
   evidence argument. The shared dependency import remains lazy to avoid a cycle.
2. **Security trigger:** before patching,
   `uv run --extra ml pytest -q tests/test_c4_tracking.py::test_self_asserted_report_is_rejected_before_mlflow`
   failed because the forged report reached MLflow. After patching,
   `uv run --extra ml pytest -q tests/test_c4_tracking.py` passed all 15 cases:
   the original trigger, missing/legacy schema, wrapped claims, duplicate keys,
   changed metrics, forged candidate/profile hashes, modified profile evidence,
   forged source identity and file-swap handling, plus legitimate controls.
3. **Compatibility:** `make lightgbm-wave1-g8-check` passed 118 tests, Ruff and CLI
   checks. The supporting command
   `uv run --extra ml pytest -q tests/test_lightgbm_v1.py tests/test_canonical_evaluation_bundle.py tests/test_mlflow_dataset_lineage.py`
   passed 18 tests. An independent read-only reviewer found no concrete bypass or
   regression and independently passed the 15 tracking and 6 LightGBM v1 tests.

Shell invocations use the repository-required `rtk proxy` prefix; Python commands
run from `backend`, and Make runs from the repository root. The pre-patch failure
is retained as reproduction evidence, not represented as a passing test.

The pinned `linux/amd64` image also passed the existing synthetic no-report
rehearsal with networking disabled and the four C4 modules mounted read-only.
It produced one FINISHED local MLflow run, verified artifact/metric read-backs,
36 synthetic scored rows and 33 simulated publication objects. Exact image,
overlay hashes and receipt are [recorded here](evidence/g8-c4-provenance-fix-20260914.json).

## Limits

The positive C4 tracking test invokes the real evaluator and verifies its
candidate/model/root/projection path, but substitutes the canonical checkpoint
join with a synthetic silent-rules fixture. Original checkpoint and replay joins
have separate tests. This proves the report intake repair, not full production
canonical comparison or remote MLflow/S3 readiness. The frozen rehearsal verifies
no-report compatibility, not a complete C4 comparison. No production test data
was read, no cloud job submitted, and no temporary credentials activated.
