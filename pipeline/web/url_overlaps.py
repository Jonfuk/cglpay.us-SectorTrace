"""Candidate URL overlap signals (BETA-057).

When one conservatively canonicalised URL appears in more than one source
table (or workflow role), that is worth a reviewer's eye — it can mean the
same document was discovered twice, or that two evidence rows are about the
same page. It is **not** proof that anything should be merged, discarded or
reprioritised, and this view says so.

Read-only. It scans a fixed list of `(table, url column, role)` and groups by
`url_canon.canonical`.
"""
from __future__ import annotations

from pipeline import catalog, url_canon

# (table, url column, human role). The `source_url` columns are the
# provenance cursor for most tables, so the document's own address column is
# listed first where there is one.
_URL_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("contracts", "notice_web_url", "contract notice page"),
    ("pfd_reports", "report_url", "PFD report"),
    ("cdp_documents", "document_url", "CDP document"),
    ("committee_papers", "document_url", "committee paper"),
    ("foi_requests", "request_url", "FOI request"),
    ("tribunal_cases", "source_url", "tribunal case"),
    ("sar_documents", "document_url", "SAR document"),
    ("charity_accounts_documents", "document_url", "charity accounts"),
    ("provider_pay_pages", "page_url", "provider pay page"),
    ("data_gov_uk_resources", "resource_url", "data.gov.uk resource"),
    ("review_queue", "raw_value", "review item"),
)

_SCAN_CAP = 200_000


def overlaps(conn, *, limit: int = 200) -> dict:
    limit = max(1, min(int(limit), 2000))
    seen: dict[str, list[dict]] = {}
    scanned = 0

    for table, column, role in _URL_SOURCES:
        if catalog.object_type(conn, table) is None:
            continue
        if column not in {c["name"] for c in catalog.columns_of(conn, table)}:
            continue
        rows = conn.execute(
            f"SELECT {column} AS u, COUNT(*) AS n FROM {table} "
            f"WHERE {column} IS NOT NULL GROUP BY {column} LIMIT ?",
            (_SCAN_CAP,)).fetchall()
        for row in rows:
            value = str(row["u"])
            if not value.lower().startswith(("http://", "https://")):
                continue
            scanned += 1
            key = url_canon.canonical(value)
            seen.setdefault(key, []).append(
                {"table": table, "role": role, "raw_url": value,
                 "row_count": row["n"]})

    groups = []
    for canonical, occ in seen.items():
        sources = {(o["table"], o["role"]) for o in occ}
        if len(sources) > 1:
            groups.append({
                "canonical_url": canonical,
                "distinct_sources": len(sources),
                "occurrences": sorted(occ, key=lambda o: (o["table"], o["raw_url"])),
            })
    groups.sort(key=lambda g: (-g["distinct_sources"], g["canonical_url"]))

    return {
        "overlaps": groups[:limit],
        "total": len(groups),
        "scanned": scanned,
        "caveat": (
            "An overlap means one canonicalised URL was found in more than "
            "one source table. It is a lead — the same document discovered "
            "twice, or two rows about the same page — not proof that any "
            "record should be merged, discarded or reprioritised. The "
            "canonicaliser is deliberately conservative: it drops only the "
            "fragment and known tracking parameters and never follows a "
            "redirect."),
    }
