# L40S Endpoint Migration

## Scope

The LOB Arena Serverless AI Endpoint is right-sized from `gpu-h100-sxm` to the
Nebius `gpu-l40s-d` platform and from `Qwen/Qwen2.5-1.5B-Instruct` to
`Qwen/Qwen2.5-14B-Instruct`. The existing `1gpu-16vcpu-96gb` resource preset,
image, networking, subnet, public/token authentication, port, routes, health
checks, autoscaling behavior, logging, monitoring, and CI/CD structure remain
unchanged.

Nebius CLI calls `gpu-l40s-d` a platform; `1gpu-16vcpu-96gb` remains the
platform-specific preset passed through `NEBIUS_ENDPOINT_PRESET`.

## vLLM configuration

| Setting | Value |
| --- | --- |
| Model | `Qwen/Qwen2.5-14B-Instruct` |
| dtype | `auto` (BF16 for this checkpoint) |
| GPU memory utilization | `0.90` |
| Maximum model length | `16384` |
| Prefix caching | enabled |
| Maximum sequences | `16` |
| Trust remote code | enabled |

The OpenAI-compatible vLLM API remains on `127.0.0.1:8001/v1`; LOB Arena's public
FastAPI routes and authentication contract are unchanged.

## Memory-fit verification

The [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct) reports
14.7B parameters, BF16 tensors, 48 layers, 40 query heads, and 8 KV heads.
[NVIDIA specifies](https://www.nvidia.com/en-us/data-center/l40s/) 48 GB of
memory for one L40S. The planning calculation is:

- BF16 weights: `14.7B × 2 bytes`, approximately 29.4 GB or 27.4 GiB.
- vLLM GPU budget: `48 GiB × 0.90`, approximately 43.2 GiB.
- BF16 KV cache: `2 × 48 layers × 8 KV heads × 128 head dimension × 2 bytes`,
  approximately 192 KiB per cached token.
- One fully occupied 16,384-token sequence: approximately 3 GiB of KV cache.

This leaves roughly 15.8 GiB inside the vLLM budget after weights for KV cache,
CUDA graphs, activations, and framework overhead. One full-length request fits
comfortably; typical shorter LOB Arena requests can use the configured 16-sequence
scheduler cap. Do not interpret `max-num-seqs=16` as capacity for sixteen
simultaneous 16K contexts: approximately three full-length sequences are the
conservative operational target after overhead. vLLM profiles the available KV
cache at startup and fails early if the configuration cannot fit.

## Planning benchmark

These are sizing estimates, not measured production results. Both GPU and model
change, so they must be replaced with measurements from the deployed endpoint.
The ranges assume typical LOB Arena requests near 512–2,048 input tokens and
128–512 output tokens.

| Measure | Previous H100 / Qwen2.5-1.5B | L40S / Qwen2.5-14B | Expectation |
| --- | --- | --- | --- |
| Weight memory | about 3 GiB BF16 | about 27.4 GiB BF16 | 14B model remains within 48 GB |
| vLLM memory budget | 85% of H100 memory | about 43.2 GiB | lower absolute reservation |
| Single-request decode | roughly 120–250 tokens/s | roughly 30–50 tokens/s | larger model is slower |
| Time to first token | roughly 0.05–0.20 s | roughly 0.20–0.80 s | depends strongly on prompt length |
| Aggregate throughput at useful batching | roughly 800–2,000 tokens/s | roughly 250–600 tokens/s | validate with LOB Arena payloads |
| Scheduler concurrency | previous vLLM default, not pinned | 16 requests | 8–16 short/medium requests; about 3 at 16K |

The L40S has 864 GB/s memory bandwidth, so decode-heavy latency is expected to
be materially higher than H100. Prefix caching should improve repeated LOB Arena
system prompts. Use vLLM's serving benchmark against the real Endpoint and
record TTFT, inter-token latency, request throughput, token throughput, peak GPU
memory, and error rate at concurrency 1, 4, 8, and 16. Keep the existing
12-second application timeout initially; change it only if measured LOB Arena
responses exceed it.

## Migration

1. Build and push the unchanged endpoint image name/tag with the updated image
   contents.
2. Create a parallel replacement Endpoint so the H100 remains available for
   rollback:

   ```bash
   export NEBIUS_ENDPOINT_NAME=lob-arena-ai-endpoint-l40s
   ./scripts/create-nebius-ai-endpoint.sh
   ```

3. Confirm `/health` reports `local_vllm` and
   `Qwen/Qwen2.5-14B-Instruct`.
4. Run `scripts/validate-local-vllm-endpoint.sh validate` against all existing
   LOB Arena routes.
5. Benchmark concurrency 1, 4, 8, and 16 and inspect GPU memory in Nebius logs
   and monitoring.
6. Switch the existing backend base URL only after validation. Authentication,
   route paths, and backend environment names do not change.
7. Retain the H100 Endpoint until the L40S smoke and benchmark pass; rollback is
   the existing backend URL switch.

No Terraform module exists for this Endpoint in the repository. The maintained
IaC surfaces are `serverless/endpoint/endpoint_config.yaml`, its example, the
deployment mode env files, and the Nebius CLI creation script; this migration
preserves that structure rather than introducing a second provisioning system.

## Changed-file inventory

| File | Change |
| --- | --- |
| `.env.example` | Documents the right-sized endpoint defaults without changing local mock mode. |
| `README.md` | Updates the primary deployment example and links this sizing analysis. |
| `backend/tests/test_incidents.py` | Aligns mocked health metadata with the current model. |
| `backend/tests/test_nebius_env_config.py` | Verifies the platform, preset, flags, and single-L40S memory bound. |
| `deployments/modes/production-nebius.env` | Selects `local_vllm`, L40S, the 14B model, and tuned vLLM settings. |
| `deployments/modes/nebius-cloud-demo.env` | Applies the same endpoint runtime defaults to the cloud demo profile. |
| `docs/challenge-submission.md` | Preserves H100 as historical evidence while identifying the current L40S configuration. |
| `docs/nebius-deployment.md` | Updates deployment, validation, and environment-reference instructions. |
| `docs/l40s-migration.md` | Adds fit analysis, estimates, migration, rollback, and this inventory. |
| `scripts/create-nebius-ai-endpoint.sh` | Passes the new platform, model, and vLLM environment variables to the unchanged CLI flow. |
| `scripts/deploy-nebius-partial.sh` | Changes only the default Endpoint platform used by the existing pipeline. |
| `scripts/validate-local-vllm-endpoint.sh` | Expects the 14B model in deployed health evidence. |
| `serverless/README.md` | Updates the serverless deployment example. |
| `serverless/deployment.env.example` | Updates the copyable Endpoint environment contract. |
| `serverless/endpoint/Dockerfile` | Changes only default model and vLLM tuning environment values. |
| `serverless/endpoint/README.md` | Documents L40S deployment and validation commands. |
| `serverless/endpoint/app.py` | Changes the reported/default local-vLLM model name. |
| `serverless/endpoint/endpoint_config.yaml` | Right-sizes the checked-in deployment manifest. |
| `serverless/endpoint/endpoint_config.example.yaml` | Keeps the public manifest example aligned. |
| `serverless/endpoint/start.sh` | Converts the six tuning environment values into supported vLLM CLI flags. |
| `serverless/endpoint/test_endpoint_contract.py` | Updates the default-model API contract assertion. |
