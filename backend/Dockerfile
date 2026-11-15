# ASTRA backend (FastAPI). Build context: backend/
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    CACHE_DIR=/app/cache \
    DB_PATH=/app/data/astra.sqlite3

WORKDIR /app

# Dependencies first (cached layer unless pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY scripts/ ./scripts/

# Non-root runtime user; cache/ and data/ must be writable
RUN useradd --create-home --uid 1000 astra \
    && mkdir -p /app/cache /app/data \
    && chown -R astra:astra /app/cache /app/data
USER astra

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["sh", "-c", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + '${PORT:-8000}' + '/api/health', timeout=4)\""]

# Shell form so ${PORT} (set by Render) expands
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
