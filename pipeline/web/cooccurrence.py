"""Entity co-occurrence explorer (BETA-095).

Documents and records in which two or more selected tracked entities are
named together — and the exact passage or structured field for each.

The whole point of the caveat: **co-occurrence is location, not a
relationship.** Two names in one passage may be a list, a comparison, or
unrelated. This finds source material; it never asserts a connection — that
is what BETA-093's pathfinder is for, and it only follows reviewed edges.

v1 restrictions (from the objective):
  * verified entity aliases only — each key's name variants come from
    `supplier_aliases` (the explicit review step), never fuzzy matching, and
    every structured mention used here already carries a confirmed
    `provider_key`;
  * same-record co-occurrence only — both entities in one document element,
    one coroner's report, one tribunal case, or one procurement notice.

Documents are gated by the same `DOCUMENT_SEARCH_SOURCES` allowlist as
`document_search`.
"""
from __future__ import annotations

from pipeline import catalog
from pipeline.web.public_queries import (
    DOCUMENT_SEARCH_SOURCES,
    _one,
    _public,
    _rows,
)
from pipeline.web.queries import QueryError, escape_like

_MAX_KEYS = 5
_MAX_RESULTS = 200
_TEXT_TRIM = 400

_NOTE = (
    "Every row is one record that names all the selected entities. "
    "Co-occurrence is location, not a relationship: two names in one passage "
    "may be a list, a comparison, or unrelated. Use the relationship "
    "pathfinder for a verified connection."
)


def _variants(conn, key: str) -> list[str]:
    rows = _rows(conn,
                 "SELECT DISTINCT alias_raw FROM supplier_aliases "
                 "WHERE supplier_key = ? ORDER BY alias_raw", (key,))
    return [r["alias_raw"] for r in rows if r["alias_raw"]]


def _entity_name(conn, key: str) -> str:
    row = (_one(conn, "SELECT canonical_name AS n FROM providers WHERE provider_key = ?", (key,))
           or _one(conn, "SELECT canonical_name AS n FROM supplier_aliases WHERE supplier_key = ? LIMIT 1", (key,)))
    return (row or {}).get("n") or key


def find(conn, keys: list[str]) -> dict:
    _public(["providers", "supplier_aliases", "document_elements",
              "document_versions", "document_records", "evidence_records",
              "pfd_provider_mentions", "pfd_reports", "tribunal_cases",
              "contracts"])
    keys = [k for k in dict.fromkeys(keys) if k]
    if len(keys) < 2:
        raise QueryError("select at least two entities")
    if len(keys) > _MAX_KEYS:
        raise QueryError(f"at most {_MAX_KEYS} entities")

    entities = []
    variants: dict[str, list[str]] = {}
    for key in keys:
        variants[key] = _variants(conn, key)
        entities.append({"key": key, "name": _entity_name(conn, key),
                          "variant_count": len(variants[key])})

    results: list[dict] = []

    # --- documents: one element that contains a variant of every key -------
    have_docs = all(variants[k] for k in keys)
    if have_docs:
        present = {o["name"] for o in catalog.list_objects(conn)}
        if {"document_elements", "document_versions", "document_records",
                "evidence_records"} <= present:
            placeholders = ",".join("?" * len(DOCUMENT_SEARCH_SOURCES))
            per_key_clause = " AND ".join(
                "(" + " OR ".join("de.text LIKE ? ESCAPE '\\'" for _ in variants[k]) + ")"
                for k in keys)
            like_params = [f"%{escape_like(v)}%" for k in keys for v in variants[k]]
            rows = _rows(conn, f"""
                SELECT de.document_element_id, de.text, d.document_id, d.title,
                       e.source_system
                FROM document_elements de
                JOIN document_versions v ON v.document_version_id = de.document_version_id
                                         AND v.is_active = 1
                JOIN document_records d ON d.document_id = v.document_id
                JOIN evidence_records e ON e.evidence_id = d.evidence_id
                WHERE e.source_system IN ({placeholders})
                  AND {per_key_clause}
                LIMIT {_MAX_RESULTS}""",
                (*DOCUMENT_SEARCH_SOURCES, *like_params))
            for row in rows:
                text = row["text"] or ""
                results.append({
                    "record_type": "document",
                    "record_id": row["document_id"],
                    "element_id": row["document_element_id"],
                    "title": row["title"] or row["document_id"],
                    "source_system": row["source_system"],
                    "text": text[:_TEXT_TRIM] + ("…" if len(text) > _TEXT_TRIM else ""),
                    "link": (f"#/documents?doc={row['document_id']}"
                             f"&el={row['document_element_id']}"),
                })

    kset = set(keys)

    # --- coroner reports: mentions of >=2 selected keys on one report -----
    for row in _rows(conn, """
        SELECT report_ref FROM pfd_provider_mentions
        GROUP BY report_ref
        HAVING COUNT(DISTINCT provider_key) >= 2"""):
        mentions = _rows(conn,
            "SELECT provider_key, mention_type, matched_name "
            "FROM pfd_provider_mentions WHERE report_ref = ?", (row["report_ref"],))
        hit = {m["provider_key"] for m in mentions} & kset
        if len(hit) < 2:
            continue
        report = _one(conn, "SELECT report_date, coroner_area, report_url "
                            "FROM pfd_reports WHERE report_ref = ?", (row["report_ref"],))
        results.append({
            "record_type": "coroner_report",
            "record_id": row["report_ref"],
            "title": f"PFD {row['report_ref']} — {(report or {}).get('coroner_area') or ''}".strip(" —"),
            "date": (report or {}).get("report_date"),
            "matched": {m["provider_key"]: m["matched_name"] or m["mention_type"]
                        for m in mentions if m["provider_key"] in hit},
            "link": "#/pfd",
        })

    # --- tribunal cases: >=2 selected keys as respondent on one case -----
    for row in _rows(conn, """
        SELECT case_number FROM tribunal_cases
        WHERE provider_key IS NOT NULL
        GROUP BY case_number
        HAVING COUNT(DISTINCT provider_key) >= 2"""):
        parties = _rows(conn,
            "SELECT provider_key, decision_date FROM tribunal_cases "
            "WHERE case_number = ?", (row["case_number"],))
        hit = {p["provider_key"] for p in parties} & kset
        if len(hit) < 2:
            continue
        results.append({
            "record_type": "tribunal_case",
            "record_id": row["case_number"],
            "title": f"Tribunal {row['case_number']}",
            "date": parties[0]["decision_date"] if parties else None,
            "matched": {k: k for k in hit},
            "link": "#/pfd",
        })

    # --- procurement notices: >=2 selected keys as supplier on one notice -
    for row in _rows(conn, """
        SELECT c.notice_id
        FROM contracts c JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
        GROUP BY c.notice_id
        HAVING COUNT(DISTINCT sa.supplier_key) >= 2"""):
        sups = _rows(conn, """
            SELECT sa.supplier_key, c.title, c.date_published, c.source_url
            FROM contracts c JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw
            WHERE c.notice_id = ?""", (row["notice_id"],))
        hit = {s["supplier_key"] for s in sups} & kset
        if len(hit) < 2:
            continue
        results.append({
            "record_type": "procurement_notice",
            "record_id": row["notice_id"],
            "title": sups[0]["title"] or row["notice_id"],
            "date": sups[0]["date_published"],
            "matched": {k: k for k in hit},
            "link": f"#/contracts?ocid=&notice={row['notice_id']}",
        })

    results = results[:_MAX_RESULTS]
    by_type: dict[str, int] = {}
    for r in results:
        by_type[r["record_type"]] = by_type.get(r["record_type"], 0) + 1

    return {
        "entities": entities,
        "results": results,
        "counts": {"by_record_type": by_type},
        "record_types": ["document", "coroner_report", "tribunal_case",
                          "procurement_notice"],
        "note": _NOTE,
        "caveat": "Documents are searched over committee papers and community "
                  "drug-partnership documents only, using verified name "
                  "variants. A missing entity variant list means nothing was "
                  "confirmed for that key — its document hits will be empty.",
    }
