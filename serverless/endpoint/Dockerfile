# vLLM-only endpoint image for Nebius Serverless AI Endpoint on GPU.
# Runs local vLLM on 127.0.0.1:8001 and exposes LOB Arena FastAPI on 0.0.0.0:9000.

FROM vllm/vllm-openai:v0.28.0

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NEBIUS_ENDPOINT_MODE=local_vllm \
    LOCAL_VLLM_HOST=127.0.0.1 \
    LOCAL_VLLM_PORT=8001 \
    LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct \
    LOCAL_VLLM_DTYPE=auto \
    LOCAL_VLLM_GPU_MEMORY_UTILIZATION=0.90 \
    LOCAL_VLLM_MAX_MODEL_LEN=16384 \
    LOCAL_VLLM_ENABLE_PREFIX_CACHING=true \
    LOCAL_VLLM_MAX_NUM_SEQS=16 \
    LOCAL_VLLM_TRUST_REMOTE_CODE=true

WORKDIR /endpoint

COPY requirements.txt /endpoint/requirements.txt

RUN python3 -m pip install --no-cache-dir -r /endpoint/requirements.txt && \
    python3 -m pip uninstall -y torchaudio torchvision || true
COPY . /endpoint

RUN chmod +x /endpoint/start.sh

RUN NEBIUS_ENDPOINT_MODE=mock python3 - <<'PY'
import app
health = app.health()
assert health["status"] == "ok"
assert health["endpoint_mode"] == "mock"
print("LOB Arena endpoint smoke test passed")
PY

EXPOSE 9000

ENTRYPOINT ["/endpoint/start.sh"]
CMD []
