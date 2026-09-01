FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir \
  "fastapi>=0.111.0" \
  pydantic \
  "starlette>=1.3.1" \
  langgraph \
  uvicorn \
  uvloop \
  httptools

COPY backend/app ./app
COPY agent-runner/app.py ./agent_runner_app.py
COPY agent-runner/langgraph_agents.py ./langgraph_agents.py

EXPOSE 9100
CMD ["uvicorn", "agent_runner_app:app", "--host", "0.0.0.0", "--port", "9100"]
