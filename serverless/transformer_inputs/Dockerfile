FROM python:3.11-slim

ENV PYTHONPATH=/opt/verifier/backend \
    PYTHONUNBUFFERED=1 \
    AWS_EC2_METADATA_DISABLED=true \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1
WORKDIR /opt/verifier
COPY serverless/transformer_inputs/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app backend/app
COPY docs/evidence/transformer-development-input-inventory-20260928.jsonl inventory.jsonl
ARG SOURCE_COMMIT
RUN python -c 'import re,sys; assert re.fullmatch("[0-9a-f]{40}", sys.argv[1]); open("source-commit","w").write(sys.argv[1])' "${SOURCE_COMMIT}"
RUN python -c 'from pathlib import Path; from app.ml.transformer.verification_spec import INVENTORY_SHA, load_inventory; from app.ml.transformer.verification_runner import execute; assert len(load_inventory(Path("inventory.jsonl"), INVENTORY_SHA)) == 185'
CMD ["python", "-m", "app.ml.transformer.verification_runner", "/opt/verifier/request.json", "/opt/verifier/inventory.jsonl", "/job/verification"]
