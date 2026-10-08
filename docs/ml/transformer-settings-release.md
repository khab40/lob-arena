# Selected Transformer settings release

Date: 2026-10-05. [Story #314](https://github.com/khab40/lob-arena/issues/314),
under [Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).
Dependency: [Story #24](https://github.com/khab40/lob-arena/issues/24).

As a detector developer,
I want to save and reload the selected Transformer's model and feature settings,
So that later inference reproduces the verified candidate without manual configuration.

Actor: detector developer. Goal: one immutable, complete research settings release.
Value: prevent drift between research and later inference.
Out of scope: training, final payload reads, Jobs, live serving, promotion and online MLflow.
Verification: metadata-only persistence/adversarial tests; GPU inference parity later.
Operator approved chunk 1 of the unseen-validation plan on 5 October.

## Retained candidate and trust boundary

The [canonical manifest](../../configs/releases/transformer/selected-settings-20261005.json)
has SHA-256 `2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab`.
It preserves width 128, rate 0.0003, seed 42, epoch 4, the original checkpoint
version, 60 features plus missingness, causal 64-step windows and training-only
normalization. Calibration is `0.9984971167248549`; all three O thresholds are
`0.996423148187864`. Balanced is the predeclared primary mode.

[Export evidence](../evidence/transformer-settings-release-20261005.json) binds
the original training verification, comparison reconciliation and normalized
operator continuation record. The receipt retains C-role calibration; no
calibrator is fitted during export. Checkpoint bytes are hashed, never deserialized.
The seven referenced blobs and their local map are preserved in root
`outputs/transformer-settings-release-20261005/`. Weights and private execution
receipts remain outside Git; public settings contain references and metadata only.

[`build_release` / `load_release`](../../backend/app/ml/transformer/settings_release.py)
require external trusted selection, comparison and decision hashes. Obtain these
from reviewed evidence; taking them from an untrusted manifest defeats the trust
boundary. The exporter validates receipt lineage and exact artifact versions/bytes;
it consumes prior independent ML verification rather than redoing ML verification.
The reader receives a bounded reference and returns `ArtifactRead(bytes, version_id)`.
It must request the exact version, cap streaming at `size_bytes + 1`, and report
the observed version. The provided CLI reads only retained local files.

Always consume the result of `load_release`, then call `require_research_inference`
before loading weights. Direct Pydantic construction is schema validation only.
Research eligibility is not run/final-access authority. `require_serving` rejects
production use even when development gates pass. Real-time feature equivalence,
GPU inference parity, online MLflow and production qualification remain open.

`save_release` writes and fsyncs a temporary file, then atomically links it to a
new destination. Existing files/symlinks are retained. Incomplete temporary writes
are removed on handled failure; a process kill may leave an unreferenced temporary
file, never a partially published manifest. This is local publication, not S3 upload.
Canonical JSON is intentionally stored on one line to preserve its checksum.

## Acceptance scenarios and tests

```gherkin
Feature: Reusable selected Transformer settings
  Scenario: Preserve a verified selected candidate
    Given trusted selection, comparison and operator decision receipts
    When settings are exported and loaded with their expected checksum
    Then all settings, ordered features and artifact identities are preserved
    And no training, calibration fitting or model execution occurs

  Scenario: Reject feature or artifact drift
    Given an immutable research settings release
    When a feature order, artifact version, checksum or training binding differs
    Then the consumer rejects the release before loading weights

  Scenario: Block incomplete or negative candidates
    Given incomplete calibration, failed gates or a negative research decision
    When research inference eligibility is requested
    Then it is rejected
    And research settings and limitations remain available for archival

  Scenario: Protect immutable publication
    Given an existing release or an interrupted temporary write
    When publication is attempted
    Then no existing release is overwritten
    And no partial manifest is published

  Scenario: Reject unsupported configuration
    Given an unknown schema, unexpected setting or nonfinite value
    When settings are loaded
    Then compatibility validation fails before artifact reads
```

The three `test_transformer_settings_*` files exercise these scenarios without
NumPy, PyTorch, cloud reads or synthetic training. The CLI is
[`export_transformer_settings.py`](../../scripts/export_transformer_settings.py):
set `PYTHONPATH=backend`, supply `--artifact-map`, `--output` and the three trusted
`--verification-sha256`, `--selection-sha256`, `--decision-sha256` pins.

Next: [the locked holdout protocol](transformer-holdout-protocol-20261005.md),
a separate final-input adapter/request/worker/readback package, followed by exact
data/run/spend authorization. Story #314 stays open until authorized inference
consumer parity passes; it does not authorize real-time serving.
