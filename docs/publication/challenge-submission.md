# Challenge Submission

## Submission links

- **Repository:** [github.com/khab40/lob-arena](https://github.com/khab40/lob-arena)
- **Technical article:** [Technical article draft](linkedin-technical-blog-post.md) — publication URL not yet available.
- **Video:** [LOB Arena — real Nebius cloud E2E demo](https://youtu.be/PZOrEwa4lqg).
- **Challenge category:** Nebius Serverless AI Builders Challenge.
- **Hashtag:** `#NebiusServerlessChallenge`

## One-minute summary

LOB Arena is a synthetic market-surveillance arena that makes order-book abuse-like behavior visible, measurable, and explainable without using real trading data. A FastAPI/React application runs deterministic Spoofing-like Wall, Layering-like Pattern, Quote Stuffing Burst, and Liquidity Evaporation scenarios; rule-based detectors generate evidence; and Nebius AI turns that evidence into investigation reports. Interactive inference is assigned to a Serverless Endpoint, while repeatable detector tournaments are assigned to Serverless Jobs. The result is an inspectable workflow from labeled scenario through alert, explanation, metrics, leaderboard, report, and charts. LOB Arena is an educational benchmark and research scaffold, not a production compliance or trading system.

## Nebius Serverless usage

- **Endpoint:** The archived representative challenge run used a Nebius H100 Serverless Endpoint (`gpu-h100`, `1gpu-16vcpu-200gb`) with `Qwen/Qwen2.5-1.5B-Instruct`. The current right-sized deployment configuration uses one L40S (`gpu-l40s-d`) with `Qwen/Qwen2.5-14B-Instruct`; see [deployment configuration](nebius-deployment.md#nebius-ai-endpoints) and [migration notes](l40s-migration.md).
- **Job:** Nebius Serverless Job using the repository jobs image and the CPU `cpu-d3`, `4vcpu-16gb` preset for parallel simulations, detector evaluation, aggregation, and artifact generation. See [job configuration](../serverless/jobs/job_config.example.yaml).
- **Why each execution model was selected:** Endpoint requests are short, interactive, and latency-sensitive. Tournament runs are finite, parallel, reproducible batch workloads that should terminate after persisting metrics and reports.

## Reproduction

- **Automated grader path:** The repository default branch is `main`. From a fresh checkout, run exactly `make grader-smoke`. This deterministic Local Mock check needs no credentials, Docker, GPU, or Nebius access; it validates backend and frontend startup, submits one fixed-seed scenario, verifies detector/results/event output and all expected artifacts, and prints `GRADER_OK` only on success.
- **Interactive local path:** Follow [Quick start](../README.md#quick-start), then open `http://localhost:5173` and run the Serverless E2E demo. Generated evidence is written under `outputs/serverless-smoke/`.
- **Real Nebius path:** Build and push both images, deploy the endpoint, create the job, and run the smoke workflow using [Nebius deployment instructions](nebius-deployment.md). Cloud completion must be confirmed by job status and collected artifacts; submission alone is not treated as success.
- **Runtime and usage:** Six corrected 200-workload Jobs completed with hash-derived, non-overlapping run seeds and synchronized Object Storage artifacts. The earlier default-seed repetitions are retained only as audit history. Pricing rates were not configured, so no dollar estimate is fabricated.

| Workflow | Measured production evidence | Infrastructure | Runtime / latency | Output |
| --- | --- | --- | --- | --- |
| Local mock demo | Local deterministic path | Laptop, Docker Compose | 3–5 min including stack startup | Demo artifacts under `outputs/serverless-smoke/` |
| Corrected multi-seed Job set | Six completed Jobs; 1,200 unique run seeds with zero overlap | Nebius Serverless Job, `cpu-d3`, `4vcpu-16gb` | 1,200 workloads and 148,958 events in 1,308.436 s aggregate lifecycle | 6 distinct event digests, 6 distinct metric digests, and 42 Job outputs synchronized from Object Storage |
| Production vLLM Endpoint set | 25 completed real calls: 17 investigations, 4 reports, 4 scenario generations | Nebius Serverless Endpoint, `gpu-l40s-d`, `1gpu-16vcpu-96gb`, `Qwen/Qwen2.5-14B-Instruct`, vLLM | 38,429 tokens; mean 24.038 s; P50 27.141 s; zero fallbacks | 17 validated structured assessments and 25 S3-uploaded evidence records |
| Manual Control Panel run | One completed 100-workload Job plus 12 real Endpoint calls | Nebius Serverless Job + L40S/vLLM Endpoint | 12,414 events in 159.800 s Job lifecycle; 16,279 Endpoint tokens | TP 60, FN 20, FP 0, TN 20; F1 0.857; 7 investigation reports; S3-synchronized artifacts |

The detector result is intentionally not perfect: aggregate precision is 1.000, recall is 0.740, and F1 is 0.850. All 240 Liquidity Evaporation positives were missed and 10 Layering-like positives were missed. See the [sanitized production evidence](../evidence/production-e2e-2026-07-15/README.md).

## Results

- **Number of runs:** More than ten production Serverless AI Job runs validated the batch workflow. The committed `EXP-390EFAC2` evidence requested and retained 100 workload labels: 80 labeled attack rows plus 20 `normal_market` control rows.
- **Best detector in the committed example:** The built-in deterministic detector suite reached precision/recall/F1 of 1.0 for the synthetic `layering_like`, `quote_stuffing`, and `spoofing_like_wall` scenarios; the benign `normal_market` control is excluded from attack recall.
- **Endpoint investigations:** The production window contains 25 completed real vLLM calls with no fallback; all 25 evidence records were uploaded to S3, and all 17 Investigation Team responses preserved the validated structured assessment.
- **Manual UI verification:** `EXP-84D07DB1` completed from the Control Panel with 100 unique derived seeds, 12,414 events, and seven collected Job-output artifacts. The same session produced 12 real Endpoint responses with zero fallback and two validated structured assessments. See the [manual UI evidence](../evidence/manual-ui-2026-07-15/README.md).
- **Main finding:** Production runs validated container execution, scenario generation, detector evaluation, aggregation, reporting, logs, and artifact persistence. These synthetic metrics validate integration and reproducibility only; they do not support a real-world surveillance-accuracy claim.

### Workload-count reconciliation

The `EXP-390EFAC2` run did not drop 20 workloads. The checked-in `labels.jsonl` contains 100 rows: 20 `normal_market` controls with `has_attack:false`, plus 20 rows each for `spoofing_like_wall`, `layering_like`, `quote_stuffing`, and `liquidity_evaporation`. The aggregate report's "80 attacks" denominator excludes the benign control rows by design.

## Proof of execution

- **Job ID/status screenshot:** More than ten production jobs completed successfully and are visible in Nebius production logs; sanitized UI screenshots are listed in the [screenshot checklist](../assets/screenshots/README.md).
- **Endpoint screenshot:** A vLLM-backed endpoint executed scenario generation, incident analysis, investigation reporting, and structured market-event explanation routes; see the [runtime status screenshot](../assets/screenshots/Screenshot%202026-07-14%20at%2019.06.53.png) and [investigation screenshot](../assets/screenshots/Screenshot%202026-07-14%20at%2017.41.43.png).
- **Logs:** The sanitized [Nebius evidence index](../evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/nebius_evidence_index.json) records completed Job operations whose evidence bundles were uploaded to S3. Raw logs remain excluded because they can contain environment-specific values.
- **Output artifacts:** The frozen [benchmark evidence bundle](../evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md) includes job records, aggregate metrics, a detector/model leaderboard, Endpoint request/response examples, the benchmark report, a manifest, and SHA-256 checksums.
- **CI and secret scanning:** [GitHub Actions](../.github/workflows/ci.yml) runs backend, frontend, deterministic-evaluation, agent-workspace, Compose, image, and Gitleaks checks without building the long-running Nebius deployment images.

## Limitations

- Production execution is validated, compact redacted evidence bundles are committed, and the runtime/cost statement above records the measured cloud run used for publication. Private console screenshots are intentionally not required to reproduce the public evidence chain.
- The manual Polished E2E workflow completed its local pipeline and evidence upload, but its cloud child lookup returned `NotFound`; it is not counted as a completed cloud Job. The separate managed experiment is the completed manual cloud run.
- The published article URL remains missing; the rendered demo video is linked above.
- The committed 100-workload evidence contains 80 labeled attack rows and 20 normal-market control rows; this is a denominator distinction, not an unexplained data loss.
- Results cover five synthetic scenario labels with one deterministic detector suite/model dimension; broader seeds and learned-detector comparisons are required before comparative claims are credible.
- The system is an educational research scaffold and must not be used for compliance decisions, trading signals, or allegations of market manipulation.
