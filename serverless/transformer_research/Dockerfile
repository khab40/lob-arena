# syntax=docker/dockerfile:1
FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b AS runtime
ENV PYTHONPATH=/opt/research/backend PYTHONUNBUFFERED=1 AWS_EC2_METADATA_DISABLED=true \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=8 CUBLAS_WORKSPACE_CONFIG=:4096:8
WORKDIR /opt/research
COPY serverless/transformer_research/requirements.txt requirements.txt
RUN pip install --no-cache-dir --require-hashes --extra-index-url https://download.pytorch.org/whl/cu126 -r requirements.txt
COPY backend/app backend/app
COPY configs/experiments/transformer configs/experiments/transformer
COPY docs/evidence/transformer-development-input-inventory-20260928.jsonl inventory.jsonl
COPY docs/evidence/transformer-source-separation-receipt-20261002.json source-separation.json
ARG SOURCE_COMMIT
RUN python -c 'import re,sys; assert re.fullmatch("[0-9a-f]{40}",sys.argv[1]); open("source-commit","w").write(sys.argv[1])' "${SOURCE_COMMIT}"
RUN python -m pip check
CMD ["python", "-m", "app.ml.transformer.research_worker", "/opt/research/request.json", "/job/research"]

FROM runtime AS sealed
RUN --mount=type=secret,id=role_bundle,required=true \
    --mount=type=secret,id=baseline_predictions,required=true \
    --mount=type=secret,id=baseline_calibration,required=true \
    python -c 'from pathlib import Path; import gzip; from app.ml.transformer.role_source import authenticate; from app.ml.transformer.research_baseline import load; b=Path("/run/secrets/role_bundle").read_bytes(); p=gzip.decompress(Path("/run/secrets/baseline_predictions").read_bytes()); c=Path("/run/secrets/baseline_calibration").read_bytes(); metadata,*_=authenticate(b,Path("source-separation.json").read_bytes()); load(p,c,metadata); Path("bundle.json").write_bytes(b); Path("baseline.parquet").write_bytes(p); Path("baseline-calibration.json").write_bytes(c)'
