# --- Frontend build stage (Phase 6) -------------------------------------------
#
# Node is a BUILD-TIME dependency only. This stage compiles the two Nuxt
# applications to static, client-rendered output; the final runtime image below
# copies just those files and never contains Node, npm, or node_modules. Each
# app has its own pinned lockfile, so `npm ci` is reproducible. The build is
# hermetic — remote font providers are disabled in the Nuxt configs — so it
# needs no network beyond the npm registry.
#
# The generated assets are inert in the runtime image until SERVE_NUXT is set:
# the server serves the legacy portals by default and the Nuxt apps only when
# the cutover flag flips. So this stage makes the image cutover-ready without
# changing what it serves.
FROM node:22-bookworm-slim AS frontend

WORKDIR /frontend

# Install each app's dependencies from its committed lockfile first, so the
# dependency layer caches independently of source changes.
COPY frontend/public/package.json frontend/public/package-lock.json frontend/public/.npmrc ./public/
COPY frontend/admin/package.json frontend/admin/package-lock.json frontend/admin/.npmrc ./admin/
RUN npm --prefix public ci --no-audit --no-fund \
 && npm --prefix admin ci --no-audit --no-fund

# Build both static outputs (nuxt generate + explicit 200.html/404.html).
COPY frontend/public ./public
COPY frontend/admin ./admin
RUN npm --prefix public run build \
 && npm --prefix admin run build

# --- Runtime image ------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Keep the dependency layer cacheable. Railway supplies DATABASE_URL at run
# time; PostgreSQL is a core deployment dependency because it is the only
# application database.
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
RUN uv sync --frozen --no-dev --no-install-project --extra storage --extra graph \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant")

COPY pipeline ./pipeline
COPY deploy ./deploy
COPY railway.toml ./railway.toml

# The two built Nuxt outputs, into the location nuxt_assets.DEFAULT_DIST_DIR
# resolves to. Node itself is left behind in the frontend stage — only these
# static files cross into the runtime image. Inert until SERVE_NUXT=true.
COPY --from=frontend /frontend/public/.output/public ./pipeline/web/static_nuxt/public
COPY --from=frontend /frontend/admin/.output/public ./pipeline/web/static_nuxt/admin

RUN uv sync --frozen --no-dev --extra storage --extra graph \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant")

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x deploy/railway-start.sh

CMD ["/app/deploy/railway-start.sh"]
