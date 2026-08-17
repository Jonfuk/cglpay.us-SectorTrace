FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Keep the dependency layer cacheable. Railway supplies DATABASE_URL at run
# time; PostgreSQL is therefore a deployment dependency even though SQLite is
# still the default for a local checkout.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra postgres --extra storage

COPY pipeline ./pipeline
COPY deploy ./deploy
COPY railway.toml ./railway.toml

RUN uv sync --frozen --no-dev --extra postgres --extra storage

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x deploy/railway-start.sh

CMD ["/app/deploy/railway-start.sh"]
