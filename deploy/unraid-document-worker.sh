#!/usr/bin/env bash
# Manage the Unraid OCR worker without repeating image, environment, and mount
# configuration. This script is run from the checkout or by absolute path.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"
image="${SECTORTRACE_DOCUMENT_IMAGE:-sectortrace-document-worker:latest}"
env_file="${SECTORTRACE_DOCUMENT_ENV_FILE:-/mnt/user/appdata/sectortrace/document-worker.env}"
data_dir="${SECTORTRACE_DOCUMENT_DATA_DIR:-$repo_dir/data}"
worker_user="${SECTORTRACE_DOCUMENT_USER:-99:100}"

usage() {
  cat <<'EOF'
Usage: deploy/unraid-document-worker.sh <command> [arguments]

Commands:
  build                 Build the local OCR worker image.
  verify                Print the installed OCR tool versions.
  status                Show document processing status.
  validate              Run canonical document integrity checks.
  shell                 Open an interactive shell in the worker.
  command <pipeline…>   Run any pipeline command, e.g. `documents stats`.
  batch <script>        Run a container-safe batch script mounted read-only.

Environment overrides:
  SECTORTRACE_DOCUMENT_IMAGE
  SECTORTRACE_DOCUMENT_ENV_FILE
  SECTORTRACE_DOCUMENT_DATA_DIR
  SECTORTRACE_DOCUMENT_USER
EOF
}

require_env_file() {
  if [[ ! -f "$env_file" ]]; then
    echo "Missing worker environment file: $env_file" >&2
    echo "Copy .env there, or set SECTORTRACE_DOCUMENT_ENV_FILE." >&2
    exit 2
  fi
}

worker_args() {
  require_env_file
  printf '%s\n' --rm --user "$worker_user" --env-file "$env_file" -e UV_CACHE_DIR=/tmp/uv-cache
  if [[ -d "$data_dir" ]]; then
    printf '%s\n' -v "$data_dir:/app/data"
  fi
}

run_pipeline() {
  local args=()
  require_env_file
  mapfile -t args < <(worker_args)
  docker run "${args[@]}" "$image" "$@"
}

case "${1:-}" in
  build)
    docker build -f "$repo_dir/deploy/Dockerfile.documents" -t "$image" "$repo_dir"
    ;;
  verify)
    docker run --rm --entrypoint /bin/sh "$image" \
      -c 'tesseract --version && gs --version && ocrmypdf --version'
    ;;
  status)
    run_pipeline documents status
    ;;
  validate)
    run_pipeline documents validate
    ;;
  shell)
    require_env_file
    args=()
    mapfile -t args < <(worker_args)
    docker run --rm -it "${args[@]}" --entrypoint /bin/bash "$image"
    ;;
  command)
    shift
    [[ $# -gt 0 ]] || { usage >&2; exit 2; }
    run_pipeline "$@"
    ;;
  batch)
    shift
    [[ $# -eq 1 ]] || { usage >&2; exit 2; }
    batch_script="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    [[ -f "$batch_script" ]] || { echo "Batch script not found: $1" >&2; exit 2; }
    require_env_file
    args=()
    mapfile -t args < <(worker_args)
    docker run --rm --name sectortrace-document-batch "${args[@]}" \
      -v "$batch_script:/work/batch.sh:ro" \
      --entrypoint /bin/bash "$image" -c '
        # The host script may begin with `git pull` and `uv sync`. The image
        # is rebuilt to update code/dependencies, so those host-only setup
        # commands are removed in a temporary copy rather than run here.
        sed -E \
          -e "/^[[:space:]]*git[[:space:]]+pull([[:space:]]|$)/d" \
          -e "/^[[:space:]]*uv[[:space:]]+sync([[:space:]]|$)/d" \
          -e "s/uv[[:space:]]+run[[:space:]]+pipeline([[:space:]]|$)/pipeline\\1/g" \
          -e "s/uv[[:space:]]+run[[:space:]]+python([[:space:]]|$)/python\\1/g" \
          /work/batch.sh > /tmp/sectortrace-batch.sh
        exec /bin/bash /tmp/sectortrace-batch.sh
      '
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
