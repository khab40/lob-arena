# Changelog

This changelog lists significant commits in reverse chronological order.
Update this file with each significant commit before pushing.

- Added the governed LightGBM Phase 2 binary trainer with deterministic CPU
  settings, training-only class and base-session weighting, native missing
  values, bounded float32 fold materialization, validation early stopping,
  approved identity-preserving optional scalers, explicit feature-release/model
  digest bindings, atomic `lightgbm_text_v1`/`lightgbm_training_run_v1`
  artifacts, and non-trivial repeated-run byte/prediction determinism tests.

- Bounded the authoritative Java arena's canonical in-memory event history,
  added stream-scoped segmented JSONL persistence with archive-backed cursor
  replay and incremental deterministic summaries, closed embedded DuckDB
  resources at EOF, paged aligned Parquet replay to bound JDBC native memory,
  configured DuckDB memory/disk spill limits, and added explicit Java
  heap/direct-memory and Compose container budgets.

- Added LOBSTER message/book, lifecycle, visible-volume, session, crossed-book,
  normalized hash, and provenance validation; repeat-run determinism and
  before/during/after causal-neighbourhood equivalence; synthetic
  cancellation/execution audits; future-data leakage coverage; and an
  Ed25519-signed public validation bundle. Java now rejects modified,
  incomplete, or unsynchronized normalized Parquet before replay;
  quote-stuffing impact is validated through per-tick event flow; and the
  Ed25519 signature binds the full evidence inventory. Fixed stable-ID agent
  order moves that could leave ghost liquidity at an old price.

- Added bounded detector-tournament lifecycle, duration, throughput, in-flight,
  and artifact-collection Prometheus metrics at the FastAPI orchestration
  boundary, plus the provisioned `LOB Arena Detector Tournaments` Grafana
  dashboard.

- Hardened local-mode secret handling: serverless-disabled environments must not retain an endpoint token, serverless-enabled environments require one, and maintainer diagnostics must never print `.env`.

- Consolidated local and Nebius runtime configuration into one conditional Docker Compose file, added explicit serverless isolation, independent Prometheus/full-Grafana profiles, combination Make targets, and removed the Nebius override file.

- Added the opt-in local Prometheus/Grafana monitoring profile with provisioned dashboards for end-to-end flow, Java kernel, component health, and bottleneck triage; FastAPI and agent-runner now expose focused Prometheus text metrics.

- Cut over the stateful live arena, scenario programs, deterministic detectors/incidents, JSONL journals, REST controls, browser WebSocket delivery, and agent-runner orchestration to Java 25/Spring. FastAPI now retains AI/ML, Nebius, experiments, evidence, and serverless responsibilities behind a thin Java arena client; same-origin Nginx routes arena traffic directly to Java.

- Completed the Java deterministic-kernel cut-over: Spring Boot now owns the public Protobuf run/status API, Python runtime kernel code/dependencies and fallback/shadow routing were removed, frontend Nginx proxies `/api/kernel/` to Java, and CI replays the immutable golden corpus directly against Java. Python remains for ML/AI and capabilities without Java replacements.

- Fixed Linux/macOS Python-to-Java parity at a liquidity-thinning boundary by making Python use Java-equivalent exact binary-value summation and scale-three half-even conversion.
- Restored the minimized backend image's Protobuf/gRPC runtime imports and added backend/Java container smoke checks to CI.

- Hardened Java CI with production-JAR parity replay, explicit process cleanup and timeouts, retained failure diagnostics, Java test reports, and per-image Docker cache scopes.

- Made Java the default versioned kernel authority with a non-root Java 25 Compose image, sampled runtime Python replay, fallback/rollback, Java image CI, and permanent full-corpus Python-to-Java gRPC replay.

- Added controlled Python/shadow/Java kernel authority routing with deterministic percentage cohorts, sampled Python replay, mismatch/error fallback, fail-closed behavior, Protobuf HTTP execution/status endpoints, persisted decisions, and rollback configuration.

- Added failure-isolated Java gRPC metrics and OpenTelemetry spans, Prometheus actuator exposure, bounded Python shadow metrics, and Prometheus/Grafana provisioning templates without adding runtime containers.

- Added JMH simulation and matching benchmarks, GC allocation profiling, and portable CI regression gates for Java kernel latency, throughput, allocation, and measured-run correctness.

- Added offline and live Java-kernel shadow execution with a runnable gRPC server, deadline-bound Python client, bounded background comparison, failure isolation, corpus replay CLI, and real six-scenario cross-language verification.

- Added the differential parity harness with immutable dual-runner inputs, structured first-divergence reporting, and explicit event, execution, snapshot, final-book, hash, metric, and termination comparisons.

- Added the shared Python/Java gRPC kernel boundary with generated stubs, reference and candidate service adapters, deterministic error mapping, and exact golden-result integration tests.

- Added the executable Java simulation kernel with logical tick phases, normal agents, all active scenarios, baseline repair, snapshots, deterministic metrics, resource validation, and exact golden output tests.

- Added the Java integer tick/lot order book and matching engine with FIFO execution, exact modify/cancel semantics, deterministic Protobuf events/snapshots, tests, and architecture documentation.

- Added bit-exact Java deterministic primitives and canonical SHA-256 hashing with complete parity against the frozen Python/JSON vectors.

- Added the Java 25 multi-module Gradle scaffold with shared Protobuf generation, a framework-free kernel boundary, separate Spring Boot control plane, repository wrapper/toolchain policy, smoke tests, and CI job.

- Added the immutable version 1 golden parity corpus with deterministic Protobuf requests/results, all-scenario and all-event coverage, checksums, canonical hashes, regeneration checks, and versioning policy.

## Unreleased

### Current - feat: add governed corpus and benchmark protocol

- Hardened the LightGBM Phase 1 boundary after review: added the externally
  SHA-256-anchored governed feature-release contract, exact replay-unit
  bindings, locally revalidated adjudications and evidence, row-level label
  reconstruction from governed ground truth, and mutation tests covering each
  fail-closed boundary.
- Added the LightGBM Phase 1 governed data boundary with locked optional
  LightGBM, scikit-learn, and MLflow client dependencies; exact local
  protocol/corpus/split/feature verification; complete fold inventory checks;
  supervised-label provenance enforcement; bounded Parquet batch iteration;
  and separate development versus final-test access.
- Fixed the post-MLflow CI regressions by aligning the frontend branding
  contract with the historical/hybrid product positioning and recording the
  exact Gitleaks fingerprint of a committed non-secret example placeholder.
- Upgraded the locked frontend to React/React DOM 19.2.8, React Router 8.3.0
  and PostCSS 8.5.23, migrated declarative router imports from the removed
  `react-router-dom` compatibility package, and closed the associated
  Dependabot advisories.
- Added an opt-in, pinned shared MLflow 3.13 Docker deployment with PostgreSQL
  metadata, private MinIO artifacts, basic authentication, generated local
  secrets, health-gated startup, persistent volumes, and hardened containers.
- Review hardening replaced MLflow's use of MinIO root credentials with a
  dedicated non-root artifact-service identity, added a safe in-place
  credential upgrade, and extended contract coverage for private storage,
  bootstrap secrecy, and policy attachment.
- Added roadmap experiment/model bootstrap and an end-to-end verification run
  covering authentication, registry metadata, artifact upload, and artifact
  download without replacing checksum-verified governed release manifests.
- Consolidated the main README, architecture overview, runtime model, use
  cases, functional overview, quick start, and ARD-0001/0022-0027 around one
  high-level design for historical ingestion, deterministic hybrid replay,
  governed corpus/features, MLflow tracking, learned detectors, and signed
  client evidence.
- Added the LightGBM Phase 0 release boundary: strict training-run, calibration,
  model-bundle, and prediction manifests bind stable model/run IDs to exact
  protocol, corpus, chronological assignment, feature, Git, and artifact
  hashes before any trainer is introduced.
- Added fail-closed validation for training-only preprocessing/class weights,
  validation-only early stopping/calibration/threshold selection, the three
  frozen operating modes, checksummed release contents, and cross-manifest
  compatibility.
- Review hardening made every manifest and nested value immutable, replaced
  untyped parameters and metrics with finite binary-LightGBM contracts, bound
  train/validation/test inputs to their declared folds and feature schema,
  verified balanced class weights, and added byte-level artifact, canonical
  manifest, safe-path, and checksum-inventory verification.
- Made required attack-family coverage derive from the implemented scenario
  catalog and added liquidity evaporation to the governed production protocol.
- Added versioned corpus, independent clean-window adjudication, canonical Java
  replay, frozen split, benchmark result, and signed release contracts.
- Added coverage gates across complete sessions, instruments, dates, attack
  families, and seeds; historical data stays unlabeled unless two independent
  blinded reviews or adjudication establish a clean window.
- Added chronological base-session grouping, boundary embargo, purge metadata,
  duplicate-source leakage rejection, and a frozen assignment hash.
- Added one-pass bounded-memory feature output, deterministic quality samples,
  Parquet row groups, logical row hashes, and throughput/RSS benchmarking.
- Added false alerts per million events, attack-level recall,
  detection-before-benefit, duplicate-alert load, session-cluster confidence
  intervals, paired comparisons, train-fitted regime matrices, worst-decile
  results, and a fully signed Ed25519 benchmark release.
- Added focused and end-to-end tests proving canonical artifact binding,
  tamper rejection, scientific split/label gates, and signed release
  verification. No learned model was added.
- Added the versioned explicit negative-label contract and governed feature
  export path. Independently verified clean windows now become bounded label
  zero rows only after local corpus/evidence verification; unreviewed history
  remains null, hybrid transfer requires equivalence evidence, and each run
  records label/adjudication provenance hashes.
- Hardened the governed release after review: corpus coverage and chronological
  splits are recomputed, canonical Java stream hashes are independently
  derived, replay/campaign inventories fail on omissions or duplicates,
  ground-truth records must parse into exactly one registered attack, clean
  transfers require exact causal-neighbourhood equivalence, event-ID checks use
  disk-backed bounded state, and streaming evidence is bound to the exact
  historical-control replay and reproduced across two row-group sizes.

### Current - feat: add versioned causal market-abuse features

- Added one source-agnostic `lob_features_v1` rolling pipeline over Java
  canonical events for LOBSTER, synthetic, and hybrid runs, with stable
  float64 columns, explicit source/session metadata, external nullable labels,
  configuration hashing, and tick/lot/book validation.
- Added Zstandard Parquet, JSON run metadata, feature-quality reports, a
  canonical JSONL/Java endpoint CLI, Make target, and a generated hybrid sample.
- Added prefix-invariance, label-leakage, source-parity, order-lifecycle,
  session-split, invalid-semantics, typed-artifact, and hybrid causal-convergence
  tests plus ARD-0024 and trainer-consumption documentation.
- Review hardening now uses only Java combined-book checkpoints as prediction
  rows, groups duplicate imports of one session together, rejects gapped or
  duplicate canonical streams and ambiguous labels, counts only terminal
  lifetimes and large adds, and validates artifact/run/config consistency.

### Current - feat: add deterministic LOBSTER hybrid replay

- Reused the authoritative Java integer exchange to replay normalized LOBSTER
  history and inject existing UI-launched spoofing-like or layering-like
  scenarios against the reconstructed current book.
- Preserved immutable historical source snapshots, historical-first equal-time
  ordering, disjoint `HIST:`/`SYN:` identities, domain-separated attack seeds,
  separate synthetic ground truth, and label-free detector input.
- Added historical-only and hybrid comparison artifacts with source/event
  counts, historical/synthetic hashes, TP/FN/FP/TN, precision, recall, F1,
  realism deltas, manifests, and checksums.
- Added a public LOBSTER-compatible fixture, replay configs, end-to-end
  determinism/provenance/label-leakage tests, ARD-0023, and updated ARD-0022,
  architecture, use-case, quick-start, backend, and root README documentation.

### Current - docs: freeze Python-to-Java kernel migration boundary

- Added ARD-0019 and the Java kernel migration tracker with the Python reference, Java candidate, authority modes, parity gates, rollback rules, and component ownership boundary.
- Kept REST, WebSocket, persistence, orchestration, detectors, and frontend authority outside the initial Java hot-loop scope.
- Recorded repository-owned Java 25 toolchain, Gradle wrapper, and Protobuf generation requirements because global build tools are not assumed.
- Added the versioned `lob.exchange.v1` Protobuf request/event/result contract, checked-in Python bindings, locked generation tooling, and stale-binding/round-trip tests.
- Added the executable determinism contract with fixed-point units, total event ordering, SplitMix64/named stream vectors, half-even metrics, midpoint, identifier, and exchange rules.
- Added domain-separated canonical event/book encoding, SHA-256 event/book digests, a rolling stream hash chain, and golden vectors for Java/Python parity.
- Added the authoritative Python Protobuf reference runner with complete event/book conversion, canonical hashes, quantized metrics, deterministic repeat tests, and resource validation.

### Current - feat: define canonical exchange event schema

- Added versioned canonical `add`, `modify`, `cancel`, `execute`, and `snapshot` event models for simulation and future historical feeds.
- Separated canonical replay sequence from upstream feed sequence and retained venue, symbol, tick, nanosecond timestamps, and scenario lineage.
- Added schema validation, serialization coverage, implementation documentation, and ARD-0018.
- Added a typed append-only event log with canonical sequence assignment, duplicate/gap protection, cursor replay, and validated JSONL round trips.
- Added explicit modify-order behavior with stable same-price queue priority and cancel/reinsert semantics for price changes.
- Migrated matching output to typed, sequenced canonical events with deterministic IDs and complete execution remainders.
- Added configurable-depth typed L2 snapshot checkpoints to the canonical matching stream.
- Integrated agent, scenario, and baseline simulation mutations into one canonical stream with one post-mutation snapshot per tick.
- Exposed a bounded canonical event tail in arena/WebSocket state and added cursor-based HTTP event replay.
- Added discriminated frontend event types and an Exchange Event Tape for backend and local mock streams.
- Added a common event-source reader with live simulation, canonical JSONL, and future historical record-normalizer adapters.
- Persisted stream-scoped canonical and snapshot-only JSONL history with validated replay and end-to-end five-event coverage.

### Current - chore: harden automated grading and repository packaging

- Renamed the local default branch to `main` and updated CI, README, and submission references from `master`.
- Added `make grader-smoke`, a credential-free fixed-seed Local Mock check for backend, frontend, scenario submission, detector/results/event output, and artifacts.
- Replaced broad Docker ignore rules with context-specific allow-lists and excluded reproducible downloads and accidental local object-store materializations.
- Added local Markdown link/anchor validation and repaired active submission links.
- Preserved compact sanitized Nebius execution evidence while removing reproducible generated binaries from the tracked project tree.

### Current - chore: archive inactive product modules

- Moved the experimental 3D LOB UI, Google Auth, disabled advanced controls, and orphan modules under `archived/` outside active build roots.
- Removed their active routes, imports, configuration, styles, dependencies, and stale architecture claims.
- Kept Local Mock as the credential-free default and added backend, Compose, frontend contract, lint, and build coverage.
- Deleted the archived source tree after confirming active code no longer imported it; this also removed its obsolete Google Auth persona test from test discovery.

### Current - chore: rename project to LOB Arena

- Renamed user-facing product, package, service, image, documentation, and repository references to LOB Arena.
- Added the surveillance-benchmarking tagline, canonical one-line description, and a frontend branding contract test.
- Preserved legacy `AIMADA_*`, session-header, schema-version, and deployed artifact identifiers for compatibility.

### Current - chore: compact command center and remove stale docs

- Folded standalone demo/report/detection/experiment page modules into the current Command Center and Arena surfaces.
- Removed stale planning and one-pager docs that were not referenced by the active documentation index.
- Compact runtime controls and Command Center workflow cards for the current three-primary-tab UI.

### Current - test: expand exchange and detector coverage

- Added backend coverage tooling with `pytest-cov` and documented the coverage command.
- Added matching-engine and order-book tests for add/cancel/market flows, price-time priority, partial fills, modify-like quote updates, and L2 snapshots.
- Added detector tests for normal market-making false positives, spoofing-like alerts, layering-like alerts, and quote-stuffing noise limits.
- Added deterministic replay and scenario-linked incident regression coverage.
- Fixed fractional partial-fill accounting in the matching engine.
- Updated README, ARD index, ARD-0001, ARD-0003, ARD-0011, and phase docs for the new validation coverage.

### Current - feat: add multiuser platform foundation

- Added a frontend platform identity model for users, workspaces, roles, case ownership, report attribution, and audit trail entries.
- Kept demo mode unblocked with `Demo Analyst` in `Aimada Surveillance Desk` when Google Auth is not configured.
- Updated Investigation to show assigned analyst, reviewer, case status, last-updated user, and audit trail records.
- Updated compliance report metadata with generated-by, reviewed-by, timestamp, assigned analyst, and case status.
- Kept one global workspace/user menu and no duplicate Google Auth widgets.
- Added ARD-0014 and refreshed architecture docs for identity, workspace, case ownership, and audit boundaries.

### Current - feat: add product demo orchestration

- Added `/demo` as a top-level product demo page with Real Nebius AI Run, Two-Model Pipeline, and Streaming Explanation cards.
- Wired demo cards to deterministic Arena modes through `/arena?demo=real`, `/arena?demo=two-model`, and `/arena?demo=streaming`.
- Added selected demo-mode context, simulated fallback labeling, and AI cost/latency metrics to Arena AI Investigator output.
- Updated README, Quick Start, architecture overview, ARD index, ARD-0001, and phase docs for seven-destination navigation and four-area diagrams.

### Current - feat: consolidate product navigation and detection workflow

- Reduced the core workflow navigation to Arena, Scenario Generator, Detection, Experiments, Nebius AI, and About before adding the dedicated Demo destination.
- Renamed Investigation/Blue Team surfaces to Detection and folded Reports into Detection outputs instead of treating Reports as an independent destination.
- Reworked Arena into three primary sections: Scenario / Attack Configuration, Market, and Detection, with Standard and Battlefield visualization modes.
- Consolidated related UI components: detector confidence panel, incident live/replay details, and agent timeline/feed surfaces.
- Reduced default analyst workload to a smaller set of primary widgets, with secondary evidence, timeline, reports, replay, and artifacts available through tabs/drawers.
- Standardized visible AI vocabulary around AI Investigator, Nebius AI, LLM, Smart Detection, and Managed Experiment.
- Refocused Nebius AI around model selection, inference, batch execution, GPU utilization, datasets, and Managed Experiments.
- Expanded About with architecture, pipeline, research papers, benchmark summary, and a JPG architecture diagram showing Front, Back, Agent Runners Workspace, and Nebius Serverless Cloud.

### Current - feat: add real Nebius deployment controls

- Added a `/nebius` Real Nebius Deployment panel that shows endpoint base URL, endpoint health, endpoint mode, model, job image, rendered job config path, submit-template readiness, latest cloud job status, and cloud artifact collection status.
- Added frontend actions for endpoint health, Smart Detection, AI Investigator report, rendered job config, real Nebius submit, job refresh, and cloud artifact collection while preserving the existing Managed Experiment and smart-batch/local flow.
- Exposed Nebius model, job image, endpoint base URL, and job submit-template readiness through `/api/nebius/status`.
- Added `POST /api/experiments/{id}/render-nebius-job-config` so the UI can render the existing serverless job config without submitting a cloud job.
- Kept missing real Nebius command templates visible as pending/not configured rather than showing fake real-cloud success.

### Current - chore: add deployment smoke workflow

- Added `scripts/serverless-smoke.sh` to verify endpoint health, endpoint alert/report routes, jobs image 3-run execution, backend experiment creation, local batch execution, optional Nebius submit, optional artifact collection, and `outputs/serverless-smoke/summary.json`.
- Kept real Nebius job submission optional; missing submit/artifact configuration is recorded as pending rather than failing the smoke.
- Documented exact local and deployed smoke commands in `serverless/README.md`.

### Current - chore: improve serverless image build and smoke targets

- Updated `scripts/build-serverless-images.sh` to use `IMAGE_NAMESPACE`, `ENDPOINT_IMAGE`, `JOBS_IMAGE`, `TAG`, `PUSH`, and `PLATFORM` options while keeping old owner/tag aliases compatible.
- Added `SMOKE=true` mode with an endpoint `/health` container check and a jobs-container 3-run batch smoke.
- Added `make serverless-build`, `make serverless-push`, and `make serverless-smoke` targets.
- Updated serverless build documentation with exact build, push, and smoke commands.

### Current - feat: collect Nebius job artifacts into experiment layout

- Added `POST /api/experiments/{id}/collect-nebius-artifacts` to collect existing Nebius job output files from mounted output or the configured artifacts command.
- Reused the Phase 4.5 artifact normalizer to copy/index only the expected job outputs into `events.jsonl`, `trades.jsonl`, `labels.jsonl`, `alerts.jsonl`, `detector_metrics.csv`, `benchmark_report.md`, `batch_manifest.json`, and `artifact_index.json`.
- Added `cloud_artifacts_pending` experiment status for cases where cloud artifacts are not yet available instead of inventing placeholder outputs.
- Added tests with fake mounted Nebius output directories and pending collection behavior.

### Current - feat: add real Nebius job submit adapter

- Added command-template based real Nebius Serverless Job submission in `backend/app/experiments/nebius_orchestrator.py` using the existing rendered experiment job config.
- Supported `NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE`, `NEBIUS_JOB_STATUS_COMMAND_TEMPLATE`, `NEBIUS_JOB_LOGS_COMMAND_TEMPLATE`, and `NEBIUS_JOB_ARTIFACTS_COMMAND_TEMPLATE` with `{config_path}`, `{experiment_id}`, `{job_id}`, `{image}`, `{output_dir}`, `{subnet_id_arg}`, `{parent_id_arg}`, and `{volume_arg}` placeholders.
- Parsed submitted job ids from JSON or text stdout, persisted queued/failed job records to `jobs.jsonl`, and redacted command output before storing messages/artifacts.
- Kept missing-template behavior as `real_nebius_pending` and prevented jobs from being marked completed until status plus artifact collection confirms completion.
- Added tests for missing templates, mocked successful submit, failed submit redaction, job id parsing, and completion gating.

### Current - feat: render experiment Nebius job configs

- Added `serverless/jobs/render_job_config.py` to render experiment-specific Nebius Serverless Job configs from the existing `serverless/jobs/nebius_job_config.yaml` template.
- Supported overrides for runs, batch size, scenarios, job output directory, and job image repository/tag without adding parallel Dockerfiles or job templates.
- Updated experiment `submit-nebius` to persist `outputs/experiments/<id>/nebius_job_config.rendered.yaml` and include it in job and experiment artifact paths while keeping real cloud execution marked pending.
- Added tests for direct config rendering and experiment submission artifact generation.

### Current - feat: wire backend to deployed serverless endpoint

- Extended backend `NebiusClient` to derive `/orderbook-alert`, `/investigation-report`, `/explain-event`, and `/generate-scenario` from `NEBIUS_ENDPOINT_BASE_URL`.
- Added explicit `NEBIUS_ORDERBOOK_ALERT_URL` and `NEBIUS_INVESTIGATION_REPORT_URL` route overrides alongside the existing incident and scenario overrides.
- Kept Bearer-token forwarding with `ENDPOINT_TOKEN`, timeout handling, and mock fallback behavior for unavailable deployed endpoints.
- Added endpoint `/health` probing plus endpoint base/order-book/investigation/mode metadata to `/api/nebius/status` and `/api/nebius/observatory`.
- Added mocked HTTP tests for route derivation, explicit overrides, Bearer auth, deployed order-book/investigation calls, and fallback on endpoint failure.

### Current - fix: harden serverless Nebius endpoint fallback behavior

- Added `/ready` to the existing serverless endpoint app and expanded `/health` with endpoint mode, active model mode, model name, and sanitized credential readiness metadata.
- Added `model`, `model_mode`, and `latency_ms` metadata to endpoint responses where possible.
- Hardened Nebius model JSON parsing and route-specific schema validation so malformed or wrong-shaped AI output falls back deterministically.
- Preserved no-fail deterministic fallback behavior for mock mode, HTTP/model failures, and invalid model JSON without exposing endpoint tokens.
- Added endpoint contract tests for mock mode, mocked local-vLLM responses, and invalid JSON fallback.

### Current - fix: normalize Nebius endpoint environment names

- Removed endpoint-side external AI gateway configuration in favor of local vLLM or deterministic mock mode.
- Updated serverless env/config examples, Docker Compose, endpoint creation script, and Nebius deployment docs.
- Stopped the Nebius endpoint creation script from printing endpoint auth tokens.
- Added tests for local-vLLM endpoint routing and deterministic fallback.

### Current - fix: restore backend Docker startup

- Fixed a Python 3.11 import-time annotation crash in `ExperimentManager` where the `list()` method shadowed the builtin `list` for later `list[...]` return annotations.
- Verified the rebuilt backend Docker image can import `app.main` successfully.

### Current - feat: add phase-4.5 experiment manager

- Added a managed experiment manifest layer under `/api/experiments` with create/list/get/delete routes.
- Persisted experiment manifests at `outputs/experiments/<experiment_id>/experiment.json`.
- Added deterministic attack manifest generation with `POST /api/experiments/{id}/generate-manifest`, writing `outputs/experiments/<experiment_id>/attacks.jsonl`.
- Added `POST /api/experiments/{id}/run-local-batch`, reusing the existing smart-batch runner to write `outputs/experiments/<experiment_id>/local-batch/` and `jobs.jsonl`.
- Added `POST /api/experiments/{id}/normalize-artifacts` to copy local-batch outputs into canonical experiment-root artifacts and write `artifact_index.json` without deleting originals.
- Added batch alert investigation with `POST /api/experiments/{id}/run-investigations` and `GET /api/experiments/{id}/investigations`, reusing the existing Nebius investigation-report client against top persisted alerts only.
- Added experiment aggregation with `POST /api/experiments/{id}/aggregate`, `GET /summary`, `GET /leaderboard`, and `GET /report`, reusing existing `detector_metrics.csv` values for scenario precision/recall/F1.
- Added a real Nebius orchestration boundary with `POST /api/experiments/{id}/submit-nebius`, `GET /api/experiments/{id}/jobs`, and `POST /api/experiments/{id}/refresh-jobs`; without real Nebius job configuration it records `real_nebius_pending` instead of faking cloud execution.
- Added experiment job summaries to `/api/nebius/observatory`.
- Upgraded `/nebius` with a Managed Experiment Lab that creates experiments, generates manifests, runs local batches, submits pending Nebius jobs, aggregates, runs AI Investigator reports, and shows status, jobs, artifacts, and leaderboard data through FastAPI only.
- Integrated Phase 4.5 experiment outputs into Detection with an experiment list, selected experiment summary, leaderboard, `benchmark_report.md` viewer, AI Investigator report list, `artifact_index.json` links, and original `local-batch` artifact workbenches.
- Reused smart-batch-compatible artifact path conventions and Reports history indexing without changing `/api/nebius/smart-batches`.
- Added backend tests for managed experiment create, list, get, report visibility, delete behavior, deterministic attack manifests, attack counts, expected labels, a 3-run local batch, fake local-batch artifact normalization, mocked Nebius investigations, sample-CSV aggregation, and missing real Nebius config.
- Verified a local 10-row mixed-scenario experiment end-to-end in mock mode through HTTP APIs, producing normalized experiment artifacts, original local-batch artifacts, aggregation outputs, and seven mock investigation reports.
- Superseded status: production Serverless Job execution, logs, S3 artifacts, and Endpoint evidence were subsequently validated and archived under `outputs/benchmark/`.

### Current - fix: sync arena tick widgets

- Aligned Liquidity Map, Market Timeline, and Incidents on the same tick window and labels.
- Changed Liquidity Map frame labels from local sequence numbers to real arena ticks.
- Added a persistent Incidents widget label with current/live tick context.
- Fixed detector Confidence graph attack-marker labels so they render as an overlay without shrinking the graph.

### Current - feat: polish AI-MADA branding and UI shell

- Switched the README/GitHub banner to `assets/img/ai-mada.jpg`.
- Added persisted day/night/system theme behavior for the shared UI shell and migrated widgets, charts, status chips, order-book levels, and the Liquidity Map canvas to theme-aware tokens.
- Made the Google/auth widget collapsible and retained a compact authenticated account control.
- Tightened the vertical navigation collapse/expand control and removed the stale product subtitle from the UI shell.
- Stopped the Liquidity Map from appending or shifting frames while the arena tick is not advancing.
- Added ARD-0013 and refreshed README, architecture, design ideas, phase status, and use-case docs for the current UI/auth/runtime state.

### Current - feat: add Google authentication persistence

- Added Google ID token verification with `google-auth` and optional authorization-code exchange using configured Google OAuth credentials.
- Added SQLite-backed Google user persistence with `id`, `email`, `name`, `avatar_url`, `google_id`, `auth_provider`, `created_at`, and `updated_at`.
- Added app-issued JWT sessions so Google tokens are only verification input, not long-lived app sessions.
- Wired the frontend Google button to Google Identity Services authorization-code flow when Google auth is configured.
- Fixed the GIS popup code exchange path to pass the browser origin consistently and return Google token-exchange details in 401 responses.
- Added ARD-0012 and tests for verified Google login, DB storage, JWT lookup, and configured-mode validation.

### Current - fix: preserve baseline exchange liquidity

- Added a baseline liquidity guard that restores a configured minimum bid/ask ladder after each simulation tick.
- Added per-agent level updates so runtime agents quoting the same price add independent synthetic orders instead of overwriting the whole price level.
- Added `ARENA_BASELINE_LIQUIDITY_*` and `ARENA_MAX_AGENT_QUOTE_SIZE` backend configuration plus regression tests for empty-side reseeding, shared-price agent liquidity, quote clamping, and long-run bounded depth.

### Current - feat: add phase-3 LangGraph remote agents

- Added generic LangGraph remote agents in `agent-runner` using `StateGraph` observe/decide nodes.
- Added heavy-agent worker-pool execution inside `agent-runner` so expensive decisions stay out of the backend/exchange process.
- Added `AGENT_RUNNER_HEAVY_AGENT_*` and `AGENT_RUNNER_LANGGRAPH_*` configuration in Docker Compose.
- Added ARD-0010 and updated architecture/runtime docs for local, remote, heavy, and LangGraph-compatible agent execution.

### Current - feat: add phase-2 remote agent runners

- Added HTTP remote-agent runner support through `RemoteAgentClient` and `ARENA_REMOTE_AGENT_URLS`.
- Added a separate `agent-runner` service with `/health`, `/agents`, and `/decide` endpoints.
- Updated Docker Compose so normal agents can run outside the backend/exchange container by default.
- Added tests for remote runner intent parsing and local/remote agent manager composition.

### Current - feat: add phase-1 in-process agent scheduler

- Added an in-process `AgentManager` that registers scalable normal agents, gathers per-tick intents with a deadline, sorts intents deterministically, and keeps order-book mutation single-writer.
- Added generated normal-agent support through `ARENA_AGENT_COUNT` and `ARENA_AGENT_DECISION_TIMEOUT_SECONDS`; Docker Compose defaults the backend to 200 normal agents.
- Added focused tests for hundreds of registered agents, deterministic intent ordering, deadline drops, and high-agent-count engine ticks.
- Updated runtime and phase docs to describe the agent scheduler boundary and future out-of-process agent-runner path.

### Current - rename product and mark implementation status

- Renamed the product identity from the old Nebius-branded project name to AI Market Abuse Detection Arena across UI labels, package/service names, docs, scripts, manifests, and demo assets.
- Updated the README with a current implementation snapshot and open gaps.
- Added implementation status sections to ARD-0001 through ARD-0009 and summarized done/partial work in the ARD index.
- Updated design ideas and phase tracking to mark implemented, partial, and missing pieces, including Judge Mode, screenshots, demo video, and sample benchmark artifacts.

### Current - fix: align cloud lab UI, replay reports, and education flow

- Split the high-level UI into clearer newcomer workflows: Arena, Scenario Generator, Detection, Experiments, Nebius AI, and About.
- Moved concrete attack-plan creation out of Nebius AI so the Scenario Generator owns attack scenario generation, variants, injection, Nebius batch submission, and scenario templates.
- Added Detection views for live detector scores, suspicious agents, evidence, incident replay, Smart Detection, and AI Investigator reports.
- Added replay/report cleanup with a typed confirmation dialog and backend clear endpoint for local persisted evidence.
- Added backend-backed artifact workbench actions for preview, keyboard navigation, export to Markdown/PDF, benchmark comparison, incident replay, screenshot attachment, and evidence promotion.
- Added red/blue geometric team marks and route-level branding without cartoon imagery.
- Updated About copy for a newcomer-friendly educational story, ML mental model, market-abuse consequences, guardrails, and runtime flow.
- Updated architecture, use-case, ARD, and phase documentation to match the current cloud-native AI laboratory workflow.

## 2026-06-09

### `4553a5e` - Add Nebius control panel and serverless workflows

- Added a Nebius Control Panel UI for cloud runtime status, AI analyst actions, serverless batch experiments, scenario grids, artifacts, usage/cost, and deployment health.
- Added backend Nebius observatory and smart batch APIs with typed mock adapters that can later be replaced by real Nebius SDK/API calls.
- Added reproducible scripts for scenario generation, local evaluation, Nebius job submission, endpoint calls, and endpoint/job creation.
- Added serverless endpoint and job Docker/config artifacts under the consolidated `serverless/` tree.
- Added report/artifact UI actions for benchmark outputs, Nebius logs/metrics evidence, export, comparison, replay, and promoted challenge bundles.
- Updated README, quickstart, deployment docs, ARDs, and phase tracking for Nebius Serverless AI Jobs and Endpoints.

## 2026-06-08

### `ee25dd5` - fix: documentation updates

- Added editor recommendations and a one-slide market-abuse arena visual asset.
- Added an AI Market Abuse Detection Arena one-pager and updated the overall architecture ARD.
- Refined Arena/Lab UI copy and scenario-launch styling.
- Updated Nebius endpoint creation script details and included the modeling document artifact.

## 2026-06-04

### `2ad792d` - docs: add 3D market battlefield concept artifacts

- Documented the 3D Market Battlefield simulator idea in `docs/DESIGN-IDEAS.md`.
- Added the detailed 3D LOB terrain concept under `docs/3d-concept-lob.md`.
- Added detached frontend prototype artifacts under `frontend/src/tabs/MarketBattlefield3D/`.
- Added game-scenario visual concept artifacts under `assets/game-scenario/`.
- Kept the 3D tab detached from the main UI navigation while preserving the prototype code for future iteration.

## 2026-06-03

### `6709f20` - feat: wire Nebius jobs and polish arena operations

- Wired the Lab "Run on Nebius Serverless Job" action through FastAPI to execute `serverless/jobs/detector_tournament.py` and parse produced benchmark artifacts.
- Updated backend Docker packaging so the FastAPI container includes `serverless/jobs` and can run the detector tournament path in Docker.
- Added persistent incident explanation records under `incidents/explanations.jsonl` and exposed them in Reports as Nebius analysis history.
- Polished the Arena cockpit toward a denser FinTech terminal UI with better viewport usage, responsive heatmap sizing, tighter panels, and clearer market-data styling.
- Made Arena Start/Pause/Reset controls state-dependent to avoid duplicate starts and invalid resets.
- Added a browser/site icon and web manifest for the AI Market Abuse Detection Arena UI.
- Added a concise one-pager under `assets/` describing AI Market Abuse Detection Arena as an early-stage product demo and future near-real-time detection direction.
- Updated `docs/PHASES.md` with status markers and aligned Phase 4 artifacts with the current serverless job outputs.

### `0c1f58b` - fix: preserve labeled legacy scenario runtime

- Kept the legacy scenario-agent and `LiveArenaRuntime` path because committed tests and older scenario-controller code still reference it.
- Added scenario metadata propagation to Spoofing-like Wall, Layering-like Pattern, and Quote Stuffing Burst agents.
- Added scenario launch support to `LiveArenaRuntime` and covered it with tests.
- Extended the matching engine to preserve scenario identifiers on cancel, limit-order, and market-order events.

### `2811d05` - docs: add architecture, use cases, and deployment docs

- Expanded the root README with quick start, API examples, environment mapping, documentation index, and screenshot links.
- Added architecture and use-case documentation, including Mermaid diagrams and ARD index updates.
- Added ARD-0002 through ARD-0009 for WebSocket schema, detector evidence, benchmark artifacts, Nebius endpoint/jobs, scenario labeling, and judge mode.
- Moved project phases from root `PHASES.md` to `docs/PHASES.md`.
- Added documentation guide, quickstart guide, design ideas, use cases, and SVG screenshot placeholders.
- Updated `docker-compose.yml` and `Makefile` documentation/deployment helpers.

### `3ccbece` - feat: add Nebius serverless endpoint and jobs

- Added Nebius Serverless AI Endpoint implementation with deterministic mock mode; the current GPU endpoint path uses local vLLM.
- Added endpoint routes for health, incident explanation, simulation explanation, report generation, and scenario generation.
- Added detector tournament and synthetic dataset factory serverless job scripts.
- Added serverless Dockerfiles, example job configs, endpoint config, deployment env example, and serverless README.
- Added `scripts/build-serverless-images.sh` for linux/amd64 GHCR image builds and optional pushes.
- Added endpoint contract tests and smoke-tested benchmark/dataset scripts.

### `bb79d04` - feat: build arena cockpit and lab UI

- Reworked the frontend into a routed React/Vite app with Arena, Lab, Reports, and About pages.
- Added market cockpit widgets: order book ladder, liquidity heatmap, market timeline, detector confidence panel, attack tracker, evidence panel, agent event tape, and Incident Details.
- Added Nebius AI Investigator panel with mock/real backend integration through the API client.
- Added Experiment Lab with attack builder, benchmark table, Recharts charting, and report summary UI.
- Added Tailwind/PostCSS/ESLint config, React Router, Recharts, and frontend build/lint scripts.
- Removed the old duplicate benchmark page.

### `754b779` - feat: wire FastAPI arena routes and persistence

- Replaced the early runtime wiring with FastAPI arena, simulation, scenario, incident, Nebius, red-team, experiment, and WebSocket routes.
- Added backend `NebiusClient` with typed fallback responses for incident explanations and red-team scenario generation.
- Added local JSONL persistence for experiments, benchmark runs, attacks, incidents, labels, and significant events.
- Added `/api/status`, `/metrics`, `/api/arena/state`, `/api/incidents`, `/api/red-team/generate-scenario`, and `/ws/arena` runtime surfaces.
- Updated backend config/env mapping for Nebius endpoint URLs, tenant metadata, API key, output dirs, and dotenv loading.
- Added backend tests for incident creation/explanation, experiment persistence, and red-team generation.

### `bb27454` - feat: implement accepted arena ARD slice

- Implemented the synthetic L2 order book, arena state models, simulation engine, detector aggregation, and scenario controller.
- Added deterministic scenario state machines for spoofing-like, layering-like, quote-stuffing, and liquidity-evaporation patterns.
- Added detector feature extraction and detector modules for spoofing-like, layering-like, quote-stuffing, and liquidity shock.
- Added structured arena Pydantic schemas and frontend TypeScript arena models.
- Added versioned WebSocket arena state envelope and frontend arena source hook supporting mock and WebSocket modes.
- Added reproducible scenario labels and focused backend/frontend verification coverage.

### `0e6bf98` - chore: ignore local worktrees

- Added `.worktrees/` and related local-development artifacts to `.gitignore`.
- Prevented isolated implementation worktrees from being committed accidentally.

### `c942b59` - feat: initial simple setup

- Added the initial project scaffold for backend, frontend, serverless, docs, assets, data, and outputs.
- Added the first README, license, Makefile, Docker Compose file, environment example, and gitignore.
- Added initial FastAPI backend, Vite frontend, serverless scaffolds, sample data, and documentation structure.
