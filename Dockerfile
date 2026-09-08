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
# The extra list is deliberate and closed for the ordinary image: `nlp`,
# `docs`, `ocr`, `sheets` and `open-jobs`
# are NOT installed here. `otel` (performance.md's Phase 5 pipeline
# observability) is always installed alongside `storage`/`graph` rather than
# gated behind a build arg: unlike the excluded extras above it carries no
# native build step, GPU/ML weight, or runtime process of its own -- the SDK
# is inert until `OTEL_ENABLED=true` (pipeline/telemetry.py degrades to a
# documented no-op otherwise), so there is no image-size or attack-surface
# reason to make an operator rebuild the image just to turn tracing on.
# `assistant` (BETA-107) is the local-analysis-host
# operator layer — it pulls `openai` and expects an Ollama runtime and model
# weights that this image neither has nor should — so it too is off by
# default and stays off on Railway, which builds this file with no build
# args (railway.toml: builder = DOCKERFILE). A self-hosted box that
# provisions the assistant runtime builds with --build-arg
# INSTALL_ASSISTANT=true; the Ansible roles pass it, keyed on
# assistant_runtime_enabled. Beta collection hosts additionally pass
# INSTALL_SCRAPY=true so their image carries Scrapy, scrapy-playwright and
# Chromium; ordinary publication images remain browser-free.
ARG INSTALL_ASSISTANT=false
ARG INSTALL_SCRAPY=false
ARG INSTALL_OPEN_JOBS=false

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra storage --extra graph --extra otel \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant") \
    $([ "$INSTALL_SCRAPY" = "true" ] && echo "--extra scrapy") \
    $([ "$INSTALL_OPEN_JOBS" = "true" ] && echo "--extra open-jobs")

COPY pipeline ./pipeline
COPY deploy ./deploy
COPY railway.toml ./railway.toml

# The two built Nuxt outputs, into the location nuxt_assets.DEFAULT_DIST_DIR
# resolves to. Node itself is left behind in the frontend stage — only these
# static files cross into the runtime image. Inert until SERVE_NUXT=true.
COPY --from=frontend /frontend/public/.output/public ./pipeline/web/static_nuxt/public
COPY --from=frontend /frontend/admin/.output/public ./pipeline/web/static_nuxt/admin

RUN uv sync --frozen --no-dev --extra storage --extra graph --extra otel \
    $([ "$INSTALL_ASSISTANT" = "true" ] && echo "--extra assistant") \
    $([ "$INSTALL_SCRAPY" = "true" ] && echo "--extra scrapy") \
    $([ "$INSTALL_OPEN_JOBS" = "true" ] && echo "--extra open-jobs")

# The Python extra deliberately does not download a browser on ordinary
# images. Beta collection hosts opt in at build time so Power BI interception
# has a reproducible Chromium binary instead of depending on a hand-edited
# container.
RUN if [ "$INSTALL_SCRAPY" = "true" ]; then uv run playwright install --with-deps chromium; fi

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x deploy/railway-start.sh

CMD ["/app/deploy/railway-start.sh"]
