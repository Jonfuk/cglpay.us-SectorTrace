"""Contract diary and milestone calendar (BETA-098).

Procurement lifecycle records read as dated events rather than disconnected
notice rows: a notice published, an award, a contract period starting, a
contract period ending. Every date is **transcribed from the notice**. A
period-end date is the contract period as published — it is not a prediction
of renewal, re-tender, or completion, and nothing here forecasts a milestone
the notice did not state.

Only the OCDS fields the warehouse actually holds are used
(`date_published`, `date_start`, `date_end`, and the notice type for the
award marker). Amendments, milestones and performance events are not
collected and are not invented.
"""
from __future__ import annotations

import sqlite3

from pipeline.web.public_queries import _public, _rows
from pipeline.web.queries import QueryError

_MAX_EVENTS = 1000

_KIND_LABEL = {
    "published": "Notice published",
    "award": "Award notice",
    "period_start": "Contract period starts (as published)",
    "period_end": "Contract period ends (as published)",
}

_NOTE = (
    "Each event is a date the notice itself carries. An “ends” event "
    "is the contract period as published, not a forecast: this diary never "
    "predicts a renewal, a re-tender, or a completion, and it shows no "
    "milestone or performance event because the warehouse does not collect "
    "them."
)


def diary(conn: sqlite3.Connection, *, provider_key: str | None = None,
          buyer_ons_code: str | None = None, year: str | None = None,
          ocid: str | None = None) -> dict:
    _public(["contracts", "supplier_aliases"])

    where = ["1=1"]
    params: list = []
    scope = None
    if provider_key:
        where.append(
            "c.supplier_name_raw IN (SELECT alias_raw FROM supplier_aliases "
            "WHERE supplier_key = %s)")
        params.append(provider_key)
        scope = {"kind": "provider", "id": provider_key}
    if buyer_ons_code:
        where.append("c.buyer_ons_code = %s")
        params.append(buyer_ons_code)
        scope = scope or {"kind": "authority", "id": buyer_ons_code}
    if ocid:
        where.append("c.ocid = %s")
        params.append(ocid)
        scope = scope or {"kind": "ocid", "id": ocid}
    if not (provider_key or buyer_ons_code or ocid):
        raise QueryError("give a provider_key, a buyer_ons_code or an ocid")

    rows = _rows(conn, f"""
        SELECT c.notice_id, c.ocid, c.notice_type, c.title, c.buyer_name,
               c.buyer_ons_code, c.supplier_name_raw, c.value_core, c.currency,
               c.date_published, c.date_start, c.date_end, c.source_url
        FROM contracts c
        WHERE {' AND '.join(where)}
        ORDER BY c.date_published, c.notice_id""", tuple(params))

    events: list[dict] = []

    def add(date, kind, row):
        if not date:
            return
        d = str(date)[:10]
        if year and not d.startswith(str(year)):
            return
        events.append({
            "date": d, "kind": kind, "kind_label": _KIND_LABEL[kind],
            "notice_id": row["notice_id"], "ocid": row["ocid"],
            "title": row["title"] or row["notice_id"],
            "buyer_name": row["buyer_name"],
            "supplier": row["supplier_name_raw"],
            "value_core": row["value_core"], "currency": row["currency"],
            "source_url": row["source_url"],
        })

    for row in rows:
        types = (row["notice_type"] or "").lower()
        add(row["date_published"],
            "award" if "award" in types or "contract" in types else "published",
            row)
        add(row["date_start"], "period_start", row)
        add(row["date_end"], "period_end", row)

    events.sort(key=lambda e: (e["date"], e["kind"], e["notice_id"]))
    truncated = len(events) > _MAX_EVENTS
    events = events[:_MAX_EVENTS]

    by_kind: dict[str, int] = {}
    by_month: dict[str, int] = {}
    for e in events:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        by_month[e["date"][:7]] = by_month.get(e["date"][:7], 0) + 1

    dates = [e["date"] for e in events]
    return {
        "scope": scope,
        "events": events,
        "months": [{"month": m, "count": by_month[m]} for m in sorted(by_month)],
        "span": {"min": dates[0], "max": dates[-1]} if dates else None,
        "counts": {"by_kind": by_kind},
        "kinds": list(_KIND_LABEL),
        "truncated": truncated,
        "note": _NOTE,
        "caveat": "Coverage is whichever notices matched this scope by exact "
                  "supplier-name or buyer ONS code; a missing event means a "
                  "missing or unmatched notice, not that nothing happened.",
    }
