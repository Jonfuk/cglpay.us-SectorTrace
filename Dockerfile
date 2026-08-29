FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Keep the dependency layer cacheable. Railway supplies DATABASE_URL at run
# time; PostgreSQL is therefore a deployment dependency even though SQLite is
# still the default for a local checkout.
#
# The extra list is deliberate and closed: `nlp`, `docs`, `ocr` and `sheets`
# are NOT installed here. `assistant` (BETA-107) is the local-analysis-host
# operator layer — it pulls `openai` and expects an Ollama runtime and model
# weights that this image neither has nor should — so it too is off by
# default and stays off on Railway, which builds this file with no build
# args (railway.toml: builder = DOCKERFILE). A self-hosted box that
# provisions the assistant runtime builds with --build-arg
# INSTALL_ASSISTANT=true; the Ansible roles pass it, keyed on
# assistant_runtime_enabled. Nothing else about the image changes.
ARG INSTALL_ASSISTANT=false

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra postgres --extra storage --extra graph \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant")

COPY pipeline ./pipeline
COPY deploy ./deploy
COPY railway.toml ./railway.toml

RUN uv sync --frozen --no-dev --extra postgres --extra storage --extra graph \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant")

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x deploy/railway-start.sh

CMD ["/app/deploy/railway-start.sh"]
