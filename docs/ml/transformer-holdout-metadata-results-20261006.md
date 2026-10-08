# Transformer December metadata results — 6 October 2026

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[settings #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3).
This records the completed [admission audit](transformer-holdout-admission.md).
Behavioral change: none. Candidate, calibration and operating points remain fixed.
Verification: retained manifest hashes, exact receipt equality and separate-agent
review; no model execution or holdout payload inspection.

The approved single attempt made **3 GETs + 62 HEADs**. Frozen JSON metadata
contains 30 December replay identities and **15,160 aligned supervised rows**,
64-step sequences, matching row identities and declared causal ordering. All 65
objects have version `1`; sizes match manifests or archived original G8 receipts.
The three JSON bodies total 53,466 bytes. All other checks read zero payload bytes.

The [machine result](../evidence/transformer-holdout-metadata-result-20261006.json)
binds source/proposal/evidence hashes. The [exact object inventory](../evidence/transformer-holdout-object-inventory-20261006.json)
preserves all 65 receipts, including key/version/size/hash and GET/HEAD method.
Its parsed contents equal the original retained receipts. These are metadata
pins for packaging, not an execution request or authorization.
HEAD hashes are expected manifest/archive hashes; they do not prove fresh payload
integrity. A separately authorized consumer must verify fetched bytes before use.

After the operator's explicit `run` delegation, approved CLI policy updates were
independently read back through Nebius MCP. Both grants were removed; original
policies match exactly at final bucket version **10** / 2 rules and results
version **11** / 9 rules. The access window was 2,195.985139 seconds, conservatively
recorded as 2,195.986 seconds, below one hour. The approved $0.01 additional cap
excluding VAT remains reserved until actual cost reconciliation.

Durable evidence lives in project-root
`outputs/transformer-holdout-admission-20261006/`: `live-audit/`, approval and
attempt receipts, active/cleanup readbacks and independent review receipts.
The source is PR #328 head `a2a0cd41596cda3d56d4b0d50905c1a31d638d7b`, merged as
`23ceb7c8209b52d057c497b126fc68393073bdc9`; all 25 checks passed. Two separate
reviews found no actionable P0/P1/P2 in retained evidence and its publication.

Next: publish/pin the saved development reference, resolve remaining access and
credential pins, seal the request, publish the immutable image and perform the
exact Nebius dry-run. Then obtain fresh final-access/run/spend authorization.
Proposed execution remains one L40S, one hour and $6.25 additional excluding VAT.
CUDA parity must pass before December payload reads. No GPU Job is authorized
by this audit; no G8 rerun, fitting or candidate reselection is included.
