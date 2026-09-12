"""The files an export produced: listing them, and handing one back.

The whole of the security thinking here is one sentence: **a file is served
only if it appears in a listing this server just computed for itself.**

Nothing takes a caller's path and sanitises it. There is no `..` check, no
prefix comparison, no `os.path.normpath` dance to get right -- those are all
ways of asking "is this path acceptable?", which is the question that keeps
being answered wrongly. Instead the directory is walked, the answer is a set of
real resolved paths, and a request either matches one of them or gets a 404.
Traversal is not defended against; it is unrepresentable.

The listing follows symlinks to their targets before comparing, so a link
planted inside exports/output pointing at the warehouse cannot smuggle it out
either -- it resolves to a path that is not under the export root, and is
dropped from the listing entirely.
"""
from __future__ import annotations

from pathlib import Path

# Exports can be large -- treatment_numbers.geojson is 23 MB -- so a download
# is streamed rather than read into memory and handed to the socket whole.
CHUNK_BYTES = 64 * 1024

# What a browser should do with each kind of artefact. Everything is sent as an
# attachment regardless; this only decides how it is labelled.
CONTENT_TYPES = {
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


def export_root(settings) -> Path:
    """Where `pipeline export` writes, and the only place a download may come
    from. A configured setting rather than a path derived from the warehouse's
    location, which would be a guess that is right for one layout."""
    return Path(settings.export_output_dir)


def listing(settings) -> dict:
    """Every export file on disk, newest first.

    Provenance companions are attached to the file they describe rather than
    listed beside it: `contracts.geojson` and
    `contracts.geojson.provenance.json` are one artefact and two files, and a
    list that interleaves them doubles in length and halves in use.
    """
    root = export_root(settings)
    if not root.is_dir():
        return {"root": str(root), "exists": False, "files": [], "bytes": 0}

    resolved_root = root.resolve()
    found: dict[str, dict] = {}
    companions: dict[str, dict] = {}

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        real = path.resolve()
        # A symlink out of the export tree is not an export.
        if not real.is_relative_to(resolved_root):
            continue

        relative = path.relative_to(root).as_posix()
        stat = real.stat()
        entry = {
            "path": relative,
            "name": path.name,
            "group": relative.split("/")[0] if "/" in relative else "",
            "bytes": stat.st_size,
            "modified": _iso(stat.st_mtime),
        }
        if relative.endswith(".provenance.json"):
            companions[relative[: -len(".provenance.json")]] = entry
        else:
            found[relative] = entry

    for relative, entry in found.items():
        companion = companions.pop(relative, None)
        entry["provenance"] = companion["path"] if companion else None

    # A provenance file whose subject has gone is still a file someone may want
    # to look at, and hiding it would misreport what is on disk.
    files = list(found.values()) + list(companions.values())
    files.sort(key=lambda entry: entry["modified"], reverse=True)

    return {
        "root": str(root),
        "exists": True,
        "files": files,
        "bytes": sum(entry["bytes"] for entry in files),
    }


# --- staleness -----------------------------------------------------------------
#
# W-20: the listing carried file mtimes and nothing else, so an export written
# before a warehouse-changing run looked exactly like one written after it. A
# figure taken from stale sheets looks current, which is the shape D-02 existed
# to kill -- for artefacts instead of runs.
#
# The question is "could the evidence behind these files have changed since
# they were written", and the signal has to be the *pipeline's* own activity
# rather than the warehouse's.
#
# The first version of this compared the export files against the mtime of
# `warehouse.db` and its WAL, on the reasoning that every write touches the
# file and the check could then only err towards stale. That reasoning is
# sound and the result was useless, which the browser showed in one look: the
# server writes to the warehouse as it starts -- applying migrations, marking
# a job left running as interrupted -- so every directory read "stale" a
# second after the page was opened. A warning that is always on is not a
# warning, and it would have trained its reader to skip the line.
#
# So the verdict comes from three records of the pipeline having *done*
# something, each of which is a single indexed-or-tiny read:
#
#   * `http_cache.updated_at` -- written on every conditional request by the
#     shared client, so it moves whenever any module spoke to any source. This
#     is the one that catches a command-line run, which leaves no job row.
#   * `module_cursors.updated_at` -- where a module resumes from.
#   * `job_runs.finished_at` -- runs started from the browser. Used to *name*
#     what happened, since it is the only one of the three that knows.
#
# None of them moves because somebody opened the operator UI, which is the
# whole point. What they can miss is a module that wrote rows without fetching
# anything at all; the note travelling with the answer says so rather than
# leaving the reader to assume a completeness this does not have.

ACTIVITY_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("http_cache", "SELECT MAX(updated_at) AS stamp FROM http_cache",
      "a source was last fetched"),
    ("module_cursors", "SELECT MAX(updated_at) AS stamp FROM module_cursors",
      "a module last recorded its position"),
    ("job_runs", "SELECT MAX(finished_at) AS stamp FROM job_runs",
      "a run started from this UI last finished"),
)


def _parse(stamp: str | None):
    from datetime import datetime

    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def pipeline_last_active(conn) -> dict:
    """When the pipeline last did something, and which record says so."""
    newest: tuple = ()
    for source, sql, phrase in ACTIVITY_SOURCES:
        try:
            stamp = conn.execute(sql).fetchone()["stamp"]
        except Exception:  # pragma: no cover - a warehouse without the table
            continue
        parsed = _parse(stamp)
        if parsed is None:
            continue
        if not newest or parsed > newest[0]:
            newest = (parsed, stamp, source, phrase)
    if not newest:
        return {"at": None, "source": None, "what": None}
    return {"at": newest[1], "source": newest[2], "what": newest[3]}


def staleness(settings, conn, files: list[dict]) -> dict:
    """Per export directory: does anything on disk predate the last collection?

    `files` is the listing's own output, so the two cannot disagree about what
    is on disk.
    """
    active = pipeline_last_active(conn)
    changed = _parse(active["at"])

    groups: dict[str, list[dict]] = {}
    for entry in files:
        groups.setdefault(entry["group"] or "(root)", []).append(entry)

    out = []
    for group, entries in sorted(groups.items()):
        # The *oldest* file in the directory, not the newest: a target writes
        # nine files in one pass, and the question is whether any of them
        # predates the change, not whether the last one did.
        oldest = min(entry["modified"] for entry in entries)
        newest = max(entry["modified"] for entry in entries)
        written = _parse(oldest)
        stale = bool(changed and written and changed > written)
        out.append({
            "group": group,
            "files": len(entries),
            "oldest_file": oldest,
            "newest_file": newest,
            "stale": stale,
            "since": _runs_since(conn, oldest) if stale else [],
        })

    return {
        "pipeline_last_active": active,
        "groups": out,
        # Stated rather than left for a reader to infer from an empty `since`.
        "record_note": (
            "Staleness compares these files against the pipeline's own record "
            "of activity — the conditional-request cache, the module cursors "
            "and the job history. Runs started from the command line leave no "
            "job row, so a stale directory may not be able to name what "
            "changed."
        ),
    }


def _runs_since(conn, when: str) -> list[dict]:
    """Jobs that finished after these files were written, oldest first."""
    cutoff = _parse(when)
    if cutoff is None:
        return []
    try:
        rows = conn.execute(
            "SELECT label, state, finished_at FROM job_runs "
            "WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 50"
        ).fetchall()
    except Exception:  # pragma: no cover - a warehouse without the table
        return []

    since = []
    for row in rows:
        finished = _parse(row["finished_at"])
        if finished is None or finished <= cutoff:
            continue
        since.append({"label": row["label"], "state": row["state"],
                       "finished_at": row["finished_at"]})
    return list(reversed(since))


def resolve_for_download(settings, wanted: str) -> Path | None:
    """The real path for a requested export, or None.

    `wanted` is compared against the listing rather than interpreted. Anything
    that is not one of the paths this server just enumerated -- including any
    spelling of a traversal -- simply is not found.
    """
    if not wanted:
        return None
    root = export_root(settings)
    allowed = {entry["path"] for entry in listing(settings)["files"]}
    if wanted not in allowed:
        return None

    candidate = (root / wanted).resolve()
    # Re-checked after resolution, because the listing was taken a moment ago
    # and the filesystem is not ours alone.
    if not candidate.is_file() or not candidate.is_relative_to(root.resolve()):
        return None
    return candidate


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _iso(timestamp: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
        timespec="seconds")
