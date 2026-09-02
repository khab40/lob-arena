FROM python:3.11-slim

WORKDIR /app

ARG INSTALL_NEBIUS_CLI=false

# Real Nebius mode opts in with NEBIUS_SERVERLESS_ENABLED in Docker Compose.
# Local mock builds do not carry cloud CLIs or their installer dependencies.
RUN if [ "${INSTALL_NEBIUS_CLI}" = "true" ]; then \
      apt-get update; \
      apt-get install -y --no-install-recommends ca-certificates curl; \
      curl -fsSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash; \
      apt-get purge -y --auto-remove curl; \
      rm -rf /var/lib/apt/lists/*; \
    elif [ "${INSTALL_NEBIUS_CLI}" != "false" ]; then \
      echo "INSTALL_NEBIUS_CLI must be true or false" >&2; \
      exit 2; \
    fi

# Add the Nebius binary directory directly to the system PATH
ENV PATH="/root/.nebius/bin:${PATH}"

# Install dependencies with pip cache and timeout settings to avoid network issues
RUN pip install --no-cache-dir --retries 5 \
  "fastapi>=0.141.1" \
  "pydantic>=2.13.5" \
  "pydantic-settings>=2.14.2" \
  "starlette>=1.6.0" \
  "pyyaml>=6.0.3" \
  "pyarrow==25.0.0" \
  "uvicorn>=0.52.4" \
  uvloop \
  httptools \
  && if [ "${INSTALL_NEBIUS_CLI}" = "true" ]; then pip install --no-cache-dir --retries 5 awscli; fi

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/compose-entrypoint.sh ./compose-entrypoint.sh
COPY serverless/jobs ./serverless/jobs

RUN chmod +x ./compose-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/compose-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
