FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    TRAQ_ENABLE_DISCOVERY=false \
    TRAQ_AUTO_CREATE_SCHEMA=false \
    TRAQ_ENABLE_FILE_LOGGING=false \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md admin_cli.py alembic.ini ./
COPY app ./app
COPY alembic ./alembic

RUN uv sync --frozen

RUN mkdir -p /app/local_data

EXPOSE 8000

CMD ["sh", "-c", "/app/.venv/bin/traq-server --host 0.0.0.0 --port ${PORT:-8000}"]
