"""Downloadable versions of the portal's data, with provenance attached.

The provenance goes *in* the file rather than beside it. A CSV that leaves
this server gets separated from any accompanying note almost immediately —
pasted into a spreadsheet, mailed on, quoted in a document — and a figure
whose origin cannot be reconstructed from the file itself is a figure that
will eventually be quoted without one. So a CSV carries commented header
lines, and a JSON export carries a `_provenance` key.

This mirrors what `pipeline/exports/provenance.py` does for the pipeline's own
export files. It is not shared with it because that module writes a companion
`.provenance.json` on disk, which is the right answer for a file in a
directory and the wrong one for a browser download.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

# Which part of each endpoint's payload is "the data" for export purposes, and
# what to call it in the filename. An endpoint returning several tables
# exports its principal one — the charts have the rest, and a CSV with five
# unrelated shapes stacked in it is not usable by anyone.
EXPORTABLE = {
    "summary": ("sources", "summary"),
    "providers": ("providers", "providers"),
    "authorities": ("authorities", "authorities"),
    "contracts": ("notices", "contracts"),
    "pay": ("charity_wage_series", "pay"),
    "geography": ("features", "geography"),
    "fingertips": ("series", "fingertips"),
    # The estimates, not `other_rows`. The latter is context and suppression
    # markers — rows with no number in them, which is not what somebody
    # downloading this is after.
    "ndtms": ("estimates", "ndtms"),
}

NOTE = (
    "All figures are from public-domain sources and carry their own source URL "
    "and retrieval timestamp. Read docs/CAVEATS.md before quoting any of them: "
    "it leads with the things that must not be computed from this data."
)


class ExportError(Exception):
    pass


def rows_for(endpoint: str, payload: dict) -> tuple[list[dict], str]:
    """(rows, label) for an endpoint's payload."""
    endpoint = endpoint.split("?")[0].strip("/")
    if endpoint not in EXPORTABLE:
        raise ExportError(
            f"{endpoint!r} cannot be exported. One of: {', '.join(sorted(EXPORTABLE))}.")

    key, label = EXPORTABLE[endpoint]
    rows = payload.get(key)
    if endpoint == "summary":
        rows = (payload.get("pipeline") or {}).get("sources", [])
    if not isinstance(rows, list):
        rows = []
    return rows, label


def provenance(endpoint: str, filters: dict[str, Any]) -> dict:
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_endpoint": f"/api/v1/{endpoint.strip('/')}",
        "filters_applied": {k: v for k, v in filters.items() if v not in (None, "")},
        "pipeline_corpus": "SectorTrace",
        "note": NOTE,
    }


def to_csv(rows: list[dict], prov: dict) -> str:
    """CSV with the provenance as leading comment lines.

    `#` comments are not part of RFC 4180 and every spreadsheet handles them
    differently, which is exactly why they are here rather than as a first data
    row: a tool that ignores them loses nothing, and a person opening the file
    in a text editor sees where it came from before they see a single number.
    """
    buffer = io.StringIO()
    buffer.write(f"# SectorTrace export — {prov['source_endpoint']}\n")
    buffer.write(f"# exported_at: {prov['exported_at']}\n")
    if prov["filters_applied"]:
        applied = "; ".join(f"{k}={v}" for k, v in prov["filters_applied"].items())
        buffer.write(f"# filters_applied: {applied}\n")
    else:
        buffer.write("# filters_applied: none (full dataset)\n")
    buffer.write(f"# note: {prov['note']}\n")

    if not rows:
        buffer.write("# no rows matched\n")
        return buffer.getvalue()

    # Union of keys, first-seen order: rows from a view can legitimately differ
    # in shape, and dropping a column because row one lacked it would silently
    # truncate the export.
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fieldnames})
    return buffer.getvalue()
