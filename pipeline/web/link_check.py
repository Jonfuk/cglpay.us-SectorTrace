"""Source-link resilience checker (BETA-100).

Whether an original source URL was live, redirected or gone the last time
this pipeline fetched it, and whether a checksum-verified archive copy is
held. A citation stays inspectable when a publisher moves or removes a file
— but the archive is what this pipeline fetched on a past date, and this
never presents it as the current publisher page.

**No live fetch.** Every link state is derived from collection-time metadata
already in the warehouse: the `http_status` recorded at the last fetch, the
`payload_sha256`, and whether the archived bytes are still on disk. Nothing
here opens a socket.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from pipeline import catalog
from pipeline.web.public_queries import _one, _public, _rows
from pipeline.web.queries import QueryError

_ARCHIVE_HASH_MAX = 64 * 1024 * 1024  # don't re-hash a file larger than this

_STATE_NOTE = {
    "live_at_last_check": "The publisher returned the file (HTTP 200) at the "
                          "last collection. It may have changed or moved since.",
    "redirected_at_last_check": "The publisher redirected this URL (HTTP 3xx) "
                                "at the last collection.",
    "gone_at_last_check": "The publisher returned not-found or gone (HTTP "
                          "404/410) at the last collection.",
    "error_at_last_check": "The publisher returned an error at the last "
                           "collection.",
    "not_recorded": "No HTTP status was recorded for this URL — its state at "
                    "last collection is unknown.",
    "unknown_url": "This warehouse holds no row citing that exact URL.",
}


def _state_for(http_status: int | None) -> str:
    if http_status is None:
        return "not_recorded"
    if http_status == 200:
        return "live_at_last_check"
    if 300 <= http_status < 400:
        return "redirected_at_last_check"
    if http_status in (404, 410):
        return "gone_at_last_check"
    return "error_at_last_check"


def _url_tables(conn: sqlite3.Connection) -> list[str]:
    """Every table carrying source_url + http_status + retrieved_at — found
    from the live schema, not a hand-list (BETA-102 discipline)."""
    out = []
    for obj in catalog.list_objects(conn):
        if obj["type"] != "table":
            continue
        cols = {c["name"] for c in catalog.columns_of(conn, obj["name"])}
        if {"source_url", "http_status", "retrieved_at"} <= cols:
            out.append(obj["name"])
    return sorted(out)


def check(conn: sqlite3.Connection, settings, url: str) -> dict:
    if not url or not url.lower().startswith(("http://", "https://")):
        raise QueryError("give an http(s) source_url to check")
    _public(["evidence_records"])

    best: dict | None = None
    for table in _url_tables(conn):
        row = _one(conn,
                   f"SELECT http_status, retrieved_at, payload_sha256 "
                   f"FROM {table} WHERE source_url = ? "
                   f"ORDER BY retrieved_at DESC LIMIT 1", (url,))
        if not row:
            continue
        if best is None or (row.get("retrieved_at") or "") > (best.get("retrieved_at") or ""):
            best = {**row, "table": table}

    ev = _one(conn,
              "SELECT retrieved_at, http_status, payload_sha256, raw_object_path "
              "FROM evidence_records WHERE source_url = ? "
              "ORDER BY retrieved_at DESC LIMIT 1", (url,))
    if ev and (best is None or (ev.get("retrieved_at") or "") >= (best.get("retrieved_at") or "")):
        best = {**ev, "table": "evidence_records"}

    if best is None:
        return {
            "url": url, "state": "unknown_url",
            "state_label": _STATE_NOTE["unknown_url"],
            "last_http_status": None, "last_checked": None,
            "archive": {"held": False},
            "note": "Nothing to check — no row in this warehouse cites that "
                    "exact URL.",
            "caveat": _CAVEAT,
        }

    state = _state_for(best.get("http_status"))
    archive = _archive_status(settings, ev, best.get("payload_sha256"))

    return {
        "url": url,
        "state": state,
        "state_label": _STATE_NOTE[state],
        "last_http_status": best.get("http_status"),
        "last_checked": best.get("retrieved_at"),
        "observed_in": best.get("table"),
        "archive": archive,
        "note": "Derived only from collection-time metadata — no request was "
                "made to the source. The state is as of the last fetch date.",
        "caveat": _CAVEAT,
    }


_CAVEAT = (
    "An archive copy is the bytes this pipeline fetched on the date shown, "
    "kept with its SHA-256. It is provenance, not a mirror: it is never "
    "presented as the live publisher page, and the publisher may have changed "
    "or withdrawn the original since."
)


def _archive_status(settings, ev: dict | None, sha256: str | None) -> dict:
    if not ev or not ev.get("raw_object_path"):
        return {"held": False, "sha256": sha256}
    rel = str(ev["raw_object_path"]).removeprefix("data/raw/")
    path = Path(getattr(settings, "raw_archive_dir", "data/raw")) / rel
    if not path.is_file():
        return {"held": False, "sha256": ev.get("payload_sha256"),
                "recorded_path": ev["raw_object_path"],
                "note": "A path is recorded but the archived file is not on disk."}
    out = {"held": True, "sha256": ev.get("payload_sha256"),
           "recorded_path": ev["raw_object_path"],
           "bytes": path.stat().st_size}
    if ev.get("payload_sha256") and path.stat().st_size <= _ARCHIVE_HASH_MAX:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out["verified"] = digest == ev["payload_sha256"]
        out["computed_sha256"] = digest
    else:
        out["verified"] = None  # too large to re-hash on a request
    return out


def overview(conn: sqlite3.Connection) -> dict:
    """Warehouse-wide: how many cited rows sit at each link state. Grouped
    counts only — no per-URL scan."""
    _public(["evidence_records"])
    by_state: dict[str, int] = {}
    tables = _url_tables(conn)
    for table in (*tables, "evidence_records"):
        for row in _rows(conn,
                         f"SELECT http_status, COUNT(*) AS n FROM {table} "
                         f"WHERE source_url IS NOT NULL GROUP BY http_status"):
            state = _state_for(row["http_status"])
            by_state[state] = by_state.get(state, 0) + row["n"]

    return {
        "by_state": by_state,
        "states": list(_STATE_NOTE),
        "tables_checked": len(tables) + 1,
        "note": "One count per cited row (not per distinct URL), by the HTTP "
                "status recorded at its last fetch. Nothing here was "
                "re-fetched.",
        "caveat": _CAVEAT,
    }
