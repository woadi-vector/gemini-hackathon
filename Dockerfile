FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y --no-install-recommends nodejs && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
COPY agent/ ./agent/
RUN uv sync --frozen --no-dev || uv sync --no-dev
COPY server.py ./
RUN uv pip install --no-cache fastapi uvicorn
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/agent
ENV PHOENIX_PROJECT_NAME=apex-approve
ENV GOOGLE_GENAI_USE_VERTEXAI=1
EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
