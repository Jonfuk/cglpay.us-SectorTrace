"""Listing census figures for a person to check, next to the page they came from.

The read half of `pipeline/census_verify.py`, the way `candidates.py` is the
read half of `promote.py`, and out of `queries.py` for the same reason: this is
two specific tables with a specific shape rather than the generic browser.

The shape follows the check it supports. Verifying a census figure means
reading a number off a page of a PDF, so the page has to be here — not a link
to the PDF, the page. m06 stored the full extracted text of every page it read
in `workforce_census_page_text`, for exactly this, and nothing had ever read it.
That is what makes this screen a replacement for the generated markdown
worklist rather than a second copy of it: the worklist could show the line the
value was parsed from, and only the page can show whether that line meant what
the parser took it to mean.

Everything here is read-only. Deciding goes through `census_verify`, which is
where the audit trail lives.
"""
from __future__ import annotations

import sqlite3

from pipeline.census_verify import KEY_COLUMNS, VerificationError, metric_key

# One census round is a few dozen metrics, so the natural page is a year. The
# cap exists so a future round cannot make one response unbounded.
PAGE = 200

STATUSES = ("unchecked", "verified", "rejected", "all")


def counts(conn: sqlite3.Connection) -> dict:
    """How many figures are checked, per census year and overall.

    The number this exists to move is `unchecked`. It was 68 out of 68 from the
    day m06 first ran until the mechanism this file serves existed.
    """
    years = []
    for row in conn.execute(
            "SELECT m.census_year AS census_year, COUNT(*) AS total, "
            "       SUM(CASE WHEN m.verified = 1 THEN 1 ELSE 0 END) AS verified, "
            "       SUM(CASE WHEN m.rejected = 1 THEN 1 ELSE 0 END) AS rejected, "
            "       r.document_url AS document_url, r.page_count AS page_count "
            "FROM workforce_census_metrics m "
            "LEFT JOIN workforce_census_reports r USING (census_year) "
            "GROUP BY m.census_year, r.document_url, r.page_count "
            "ORDER BY m.census_year DESC"):
        record = dict(row)
        record["unchecked"] = (record["total"] - (record["verified"] or 0)
                                - (record["rejected"] or 0))
        years.append(record)

    return {
        "years": years,
        "total": sum(year["total"] for year in years),
        "verified": sum(year["verified"] or 0 for year in years),
        "rejected": sum(year["rejected"] or 0 for year in years),
        "unchecked": sum(year["unchecked"] for year in years),
    }


def listing(conn: sqlite3.Connection, year: int | None = None,
             status: str = "unchecked", offset: int = 0,
             limit: int = PAGE) -> dict:
    """One page of census metrics, with each figure's own decision history.

    Ordered by source page, because that is the order a person checking them
    against the PDF will want: one page open, every figure read off it, then
    the next page.
    """
    if status not in STATUSES:
        raise VerificationError(
            f"unknown status {status!r}; expected "
            f"{', '.join(STATUSES[:-1])} or all.")

    where = []
    params: list = []
    if status == "unchecked":
        where.append("verified = 0 AND rejected = 0")
    elif status == "verified":
        where.append("verified = 1")
    elif status == "rejected":
        where.append("rejected = 1")
    if year:
        where.append("census_year = ?")
        params.append(int(year))

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM workforce_census_metrics {clause}",
        params).fetchone()[0]

    limit = max(1, min(int(limit), PAGE))
    rows = conn.execute(
        f"SELECT * FROM workforce_census_metrics {clause} "
        "ORDER BY census_year DESC, source_page, metric, workforce_segment "
        "LIMIT ? OFFSET ?", [*params, limit, max(0, int(offset))])

    decisions = _decisions_by_key(conn)
    items = []
    for row in rows:
        record = dict(row)
        key = metric_key(record)
        items.append({
            "key": key,
            "census_year": record["census_year"],
            "metric": record["metric"],
            "workforce_segment": record["workforce_segment"],
            "value": record["value"],
            "unit": record["unit"],
            "source_page": record["source_page"],
            # The verbatim line the number was parsed from. The whole check is
            # this string against the page, so it is never truncated here --
            # the markdown worklist cut it at 240 characters, which is where a
            # parse that had swallowed a neighbouring sentence stopped being
            # visible.
            "raw_text": record["raw_text"],
            "verified": record["verified"],
            "rejected": record["rejected"],
            "verified_at": record["verified_at"],
            # Provenance of the report m06 read, which is what a verification
            # is taken against. Not a fetch of this screen's own.
            "source": {
                "source_url": record["source_url"],
                "retrieved_at": record["retrieved_at"],
                "payload_sha256": record["payload_sha256"],
            },
            "decisions": decisions.get(key, []),
        })

    return {"status": status, "year": year, "total": total, "offset": offset,
             "limit": limit, "items": items}


def _decisions_by_key(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Every recorded decision, grouped by the key of the metric it is about.

    Grouped here rather than joined per row so that a page of the worklist is
    two queries instead of one per figure. The whole table is a few dozen rows
    per census round.
    """
    out: dict[str, list[dict]] = {}
    for row in conn.execute(
            "SELECT census_year, metric, workforce_segment, raw_text, decision, "
            "       decided_by, decided_at, note, checked_value, checked_unit "
            "FROM census_verifications ORDER BY id DESC"):
        record = dict(row)
        key = metric_key(record)
        out.setdefault(key, []).append(
            {name: value for name, value in record.items()
              if name not in KEY_COLUMNS})
    return out


def page_text(conn: sqlite3.Connection, year: int, page: int) -> dict:
    """The archived text of one page of one census report.

    This is what a verification is taken *against*. Served from
    `workforce_census_page_text` rather than by re-reading the PDF, because the
    bytes m06 hashed are the bytes the judgement should be about — and because
    re-extracting on demand would make the text a property of whichever
    pdfplumber version is installed today.
    """
    row = conn.execute(
        "SELECT census_year, page_number, page_text, source_url, retrieved_at, "
        "       payload_sha256 "
        "FROM workforce_census_page_text "
        "WHERE census_year = ? AND page_number = ?",
        (int(year), int(page))).fetchone()
    if row is None:
        raise VerificationError(
            f"no archived text for page {page} of the {year} census. Either "
            "the page held no extractable text, or m06 has not read that "
            "report — check with ./start.sh run m06_workforce_census.")

    metrics = [dict(m) for m in conn.execute(
        "SELECT metric, workforce_segment, value, unit, verified, rejected "
        "FROM workforce_census_metrics "
        "WHERE census_year = ? AND source_page = ? "
        "ORDER BY metric, workforce_segment", (int(year), int(page)))]

    return {**dict(row), "metrics_on_page": metrics}
