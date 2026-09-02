FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
  "fastapi>=0.141.1" \
  "pydantic>=2.13.5" \
  "starlette>=1.6.0" \
  langgraph \
  "uvicorn>=0.52.4" \
  uvloop \
  httptools

COPY backend/app ./app
COPY agent-runner/app.py ./agent_runner_app.py
COPY agent-runner/langgraph_agents.py ./langgraph_agents.py

EXPOSE 9100
CMD ["uvicorn", "agent_runner_app:app", "--host", "0.0.0.0", "--port", "9100"]
