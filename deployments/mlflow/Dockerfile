FROM ghcr.io/mlflow/mlflow:v3.13.0

RUN python -m pip install --no-cache-dir \
    "mlflow[auth]==3.13.0" \
    "boto3==1.40.61" \
    "psycopg2-binary==2.9.11"

COPY \
    entrypoint.py \
    bootstrap_resources.py \
    exporter.py \
    exporter_bootstrap.py \
    smoke_test.py \
    /opt/lob-arena/mlflow/

USER 10001:10001

ENTRYPOINT ["python", "/opt/lob-arena/mlflow/entrypoint.py"]
