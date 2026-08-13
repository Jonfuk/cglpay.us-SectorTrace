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
