# syntax=docker/dockerfile:1
FROM python:3.11-slim AS runtime
ENV PYTHONPATH=/opt/role-audit/backend \
    PYTHONUNBUFFERED=1 \
    AWS_EC2_METADATA_DISABLED=true \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1
WORKDIR /opt/role-audit
COPY serverless/transformer_inputs/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app backend/app
COPY docs/evidence/transformer-development-input-inventory-20260928.jsonl inventory.jsonl
COPY docs/evidence/transformer-source-separation-receipt-20261002.json source-separation.json
ARG SOURCE_COMMIT
RUN python -c 'import re,sys; assert re.fullmatch("[0-9a-f]{40}",sys.argv[1]); open("source-commit","w").write(sys.argv[1])' "${SOURCE_COMMIT}"
RUN python -c 'from pathlib import Path; from app.ml.transformer.role_execution_spec import INVENTORY_SHA, SOURCE_RECEIPT_SHA, load_inventory, digest; from app.ml.transformer.role_execution_runner import execute; assert len(load_inventory(Path("inventory.jsonl"), INVENTORY_SHA)) == 185; assert digest(Path("source-separation.json").read_bytes()) == SOURCE_RECEIPT_SHA'
CMD ["python", "-m", "app.ml.transformer.role_execution_runner", "/opt/role-audit/request.json", "/opt/role-audit/inventory.jsonl", "/opt/role-audit/bundle.json", "/opt/role-audit/source-separation.json", "/job/role-audit"]

# The release image includes the authenticated restricted bundle. CI builds runtime;
# a sealed release requires this exact retained file supplied through BuildKit.
FROM runtime AS sealed
RUN --mount=type=secret,id=role_bundle,required=true python -c 'from pathlib import Path; from app.ml.transformer.role_audit_bundle import verify; from app.ml.transformer.role_execution_spec import BUNDLE_SHA, digest; raw=Path("/run/secrets/role_bundle").read_bytes(); assert digest(raw)==BUNDLE_SHA; verify(raw); Path("bundle.json").write_bytes(raw)'
