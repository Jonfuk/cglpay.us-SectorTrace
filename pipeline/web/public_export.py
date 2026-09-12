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
from typing import Any, Iterable, Iterator

from pipeline import licences

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
    # `recent`, not the year/area/term aggregates on the same page — those
    # are already-computed summaries, not a corpus a reader downloads rows
    # from. See WINDOWED below: `recent` itself is capped at 50, so this key
    # only names *which* part of the payload the complete export replaces.
    "pfd": ("recent", "pfd"),
}

# Endpoints whose /api/v1 payload is a *window* onto something larger, because
# it is answering a page that draws charts beside the table. Their export does
# not go through `to_csv` at all: it streams every row from its own query, and
# `to_csv` refuses them outright.
#
# The refusal is the point. `/api/v1/contracts` capped at 500 rows of 98,636
# and the download passed no limit at all, so the export shipped 0.5% of the
# corpus with nothing in the file saying so — a CSV that looks complete is
# worse than one that is visibly partial, because nobody checks. Making the
# easy path raise means that cannot be reintroduced by a caller who reaches for
# it without knowing this happened. `pfd` joined this set for the same reason:
# its `recent` key is `LIMIT 50` against a 1,500+ row corpus — see
# `public_queries.all_pfd_reports`.
WINDOWED = {"contracts", "pfd"}

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


def provenance(endpoint: str, filters: dict[str, Any],
                row_count: int | None = None) -> dict:
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_endpoint": f"/api/v1/{endpoint.strip('/')}",
        "filters_applied": {k: v for k, v in filters.items() if v not in (None, "")},
        # The same number the `# rows:` line carries, for anything reading the
        # response rather than the file. Every export this server sends is
        # complete for its filters, so this is the corpus behind it and not a
        # page size.
        "row_count": row_count,
        "pipeline_corpus": "SectorTrace",
        # Reuse starts with the licence, so it travels with the figures rather
        # than living on a page the file gets separated from. Every licence
        # this endpoint's rows can be under, from pipeline/licences.py.
        "licence": [
            {"name": lic.name, "url": lic.url, "attribution": lic.attribution,
              "caution": lic.caution or None}
            for lic in licences.for_endpoint(endpoint)
        ],
        "note": NOTE,
    }


def header(prov: dict, row_count: int) -> str:
    """The `#` lines every CSV this module produces begins with.

    `#` comments are not part of RFC 4180 and every spreadsheet handles them
    differently, which is exactly why they are here rather than as a first data
    row: a tool that ignores them loses nothing, and a person opening the file
    in a text editor sees where it came from before they see a single number.

    The row count is one of those lines rather than a figure beside the
    download, for the same reason the rest of the provenance is: the file
    travels and the page does not. A reader who opens this in six months can
    see whether the number of rows in front of them is the number of rows there
    were.
    """
    buffer = io.StringIO()
    buffer.write(f"# SectorTrace export — {prov['source_endpoint']}\n")
    buffer.write(f"# exported_at: {prov['exported_at']}\n")
    if prov["filters_applied"]:
        applied = "; ".join(f"{k}={v}" for k, v in prov["filters_applied"].items())
        buffer.write(f"# filters_applied: {applied}\n")
    else:
        buffer.write("# filters_applied: none (full dataset)\n")
    buffer.write(f"# rows: {row_count:,} — every row matching these filters\n")
    # One line per licence the rows can be under, never a single flattened
    # one: two of this pipeline's sources are not OGL, and they are among the
    # most quotable it holds.
    for lic in prov.get("licence") or []:
        terms = " ".join(part for part in (
            lic["name"],
            f"<{lic['url']}>" if lic.get("url") else "",
            lic["attribution"],
            lic.get("caution") or "",
        ) if part)
        buffer.write(f"# licence: {terms}\n")
    if not prov.get("licence"):
        buffer.write("# licence: not recorded for this endpoint — see docs/SOURCES.md\n")
    buffer.write(f"# note: {prov['note']}\n")
    return buffer.getvalue()


def to_csv(rows: list[dict], prov: dict) -> str:
    """A whole dataset, in memory, with its provenance as leading comments.

    Refuses a windowed endpoint: see WINDOWED. Everything else this serves is
    the complete table — a few hundred rows of authorities, providers or
    series — and holding it in memory to send it is not worth streaming.
    """
    endpoint = prov["source_endpoint"].rsplit("/", 1)[-1]
    if endpoint in WINDOWED:
        raise ExportError(
            f"{endpoint!r} is a windowed endpoint and must be streamed with "
            "stream_csv, which reads every row rather than the page's slice.")

    buffer = io.StringIO()
    buffer.write(header(prov, len(rows)))
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


def stream_csv(rows: Iterable[dict], prov: dict, row_count: int,
                batch: int = 500) -> Iterator[bytes]:
    """The same file, produced a batch of rows at a time.

    98,636 contract notices is around 40 MB of CSV. Building that string and
    then handing it to the socket costs the memory twice over on a server whose
    whole point is that it is a stdlib one; producing it in batches costs a
    500-row buffer.

    `row_count` was counted before the cursor was opened, because it has to be
    in the header line above rows that have not been read yet. The count that
    is actually streamed is checked against it at the end and the difference
    raised, because a file whose header says 98,636 and whose body holds 500 is
    the failure this function exists to fix, wearing a disguise.
    """
    yield header(prov, row_count).encode("utf-8")

    buffer = io.StringIO()
    writer: csv.DictWriter | None = None
    written = 0
    for row in rows:
        if writer is None:
            # Column order from the first row, not the union of every row: a
            # streamed export comes from one SELECT, so every row has the
            # cursor's shape and there is nothing to union. `to_csv` above
            # unions because its rows can come from a view.
            writer = csv.DictWriter(buffer, fieldnames=list(row),
                                     extrasaction="ignore")
            writer.writeheader()
        writer.writerow(row)
        written += 1
        if written % batch == 0:
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

    if writer is None:
        buffer.write("# no rows matched\n")
    tail = buffer.getvalue()
    if tail:
        yield tail.encode("utf-8")

    if written != row_count:
        raise ExportError(
            f"Export claimed {row_count} rows and wrote {written}. The header "
            "of this file would have been wrong, so it was not finished.")
