#!/usr/bin/env bash
# Register and analyse every provenance-complete legacy document source. The
# worker wrapper removes the host-only git/uv setup lines before running this
# script in its immutable container image.
set -euo pipefail

git pull origin master
uv sync --extra postgres --extra storage --extra documents
uv run pipeline migrate

batch_size="${DOCUMENT_BATCH_SIZE:-25}"
parser="${DOCUMENT_PARSER:-pymupdf}"
sources=(committee_papers cdp_documents annual_reports)

batch=0
total_registered=0
total_success=0
total_unchanged=0
total_failed=0
started_at=$SECONDS

elapsed() {
  printf '%02d:%02d:%02d' \
    $((SECONDS / 3600)) \
    $(((SECONDS / 60) % 60)) \
    $((SECONDS % 60))
}

process_documents() {
  local description="$1"
  shift
  local output processed success unchanged failed skipped

  printf '[%s] %s\n' "$(elapsed)" "$description"
  if ! output="$(uv run pipeline documents process --parser "$parser" --limit "$batch_size" "$@")"; then
    echo "Processing failed during $description:" >&2
    printf '%s\n' "$output" >&2
    exit 1
  fi

  read -r processed success unchanged failed skipped < <(
    printf '%s' "$output" | uv run python -c '
import json, sys
rows = json.load(sys.stdin)
statuses = [row.get("status") for row in rows]
known = {"SUCCESS", "UNCHANGED", "FAILED", "OCR_FAILED"}
print(len(rows), statuses.count("SUCCESS"), statuses.count("UNCHANGED"),
      statuses.count("FAILED") + statuses.count("OCR_FAILED"),
      sum(status not in known for status in statuses))
'
  )

  total_success=$((total_success + success))
  total_unchanged=$((total_unchanged + unchanged))
  total_failed=$((total_failed + failed))
  printf '[%s] %s: %d processed — %d new success, %d unchanged, %d failed, %d skipped\n' \
    "$(elapsed)" "$description" "$processed" "$success" "$unchanged" "$failed" "$skipped"
  printf '          Run total: %d registered, %d new success, %d unchanged, %d failed\n' \
    "$total_registered" "$total_success" "$total_unchanged" "$total_failed"

  [[ "$processed" -gt 0 ]]
}

echo "Draining any already registered documents before registering more."
while process_documents "Outstanding work"; do :; done

for source in "${sources[@]}"; do
  echo
  echo "=== Source: $source ==="
  while :; do
    batch=$((batch + 1))
    registration="$(uv run pipeline documents register-existing --source "$source" --limit "$batch_size")"

    read -r candidates registered missing_raw source_systems < <(
      printf '%s' "$registration" | uv run python -c '
import json, sys
data = json.load(sys.stdin)
print(data["candidates"], data["registered"], data["missing_raw"],
      ",".join(data["source_systems"]) or "-")
'
    )

    printf '[%s] %s batch %d: %d candidate(s), %d registered, %d missing raw; source system(s): %s\n' \
      "$(elapsed)" "$source" "$batch" "$candidates" "$registered" "$missing_raw" "$source_systems"

    if [[ "$registered" -eq 0 ]]; then
      if [[ "$candidates" -eq 0 ]]; then
        echo "$source is complete."
      else
        echo "$source cannot progress until its missing raw archive objects are recovered." >&2
      fi
      break
    fi

    total_registered=$((total_registered + registered))
    IFS=',' read -r -a systems <<< "$source_systems"
    for source_system in "${systems[@]}"; do
      [[ "$source_system" != "-" ]] || { echo "Registration returned no source system." >&2; exit 1; }
      process_documents "$source batch $batch ($source_system)" --source-system "$source_system" || true
    done
  done
done

printf '\nCompleted in %s.\n' "$(elapsed)"
uv run pipeline documents stats
uv run pipeline documents status
uv run pipeline documents validate
