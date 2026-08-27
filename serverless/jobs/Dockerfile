FROM python:3.11-slim

WORKDIR /job

ENV PYTHONPATH=/job/backend \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet

COPY serverless/jobs/requirements.txt /job/serverless/jobs/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 openssl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r /job/serverless/jobs/requirements.txt

COPY backend/app /job/backend/app
COPY serverless/jobs /job/serverless/jobs

RUN python -c "import lightgbm, mlflow, pyarrow; from app.ml.lightgbm.cloud_transport import execute_wave1_s3" \
    && python /job/serverless/jobs/run_lightgbm_wave1.py run-s3 --help >/dev/null \
    && aws --version

WORKDIR /job/serverless/jobs

CMD ["python", "run_batch_experiments.py", "--runs", "1000", "--batch-size", "100", "--output", "/job/outputs/serverless-batch"]
