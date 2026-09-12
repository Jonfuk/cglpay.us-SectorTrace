"""Validation-rule explorer (BETA-104).

A read-only catalogue of the warehouse's validation rules, derived on each
request from three enumerable sources and given stable ids:

  schema rules   `trigger:<name>`     promotion / decision gates
                 `check:<table>:<col>` fixed-value CHECK constraints
                 `provenance:<table>`  the constraint-1 NOT NULL columns
  observed rules `parse:<module>:<field>`   constraint 6, from parse_failures
                 `review:<module>:<type>`   constraint 4, from review_queue

Every rule carries a purpose (`pipeline/validation_rules.py`), the modules
and fields it touches, and recent pass/failure counts. Failure examples are
reduced to their *shape* before they leave the process — the raw fragment,
which can hold personal data, is never sent. Writes nothing.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from pipeline.validation_rules import (
    EXAMPLE_REDACTION,
    PURPOSE_BY_KIND,
    RULE_NOTES,
)

_WINDOW_DAYS = 30
_EXAMPLES_PER_RULE = 3
_SHAPE_MAX = 120

# Constraint 1's columns: an evidence row without these is not written.
_PROVENANCE_COLUMNS = ("source_url", "retrieved_at", "payload_sha256")

_CHECK_IN = re.compile(
    r"\b([a-z_][a-z0-9_]*)\b[^,]*?\bCHECK\s*\(\s*\1\s+IN\s*\(([^)]*)\)",
    re.IGNORECASE)


def _shape(text: str | None) -> str:
    """A fragment reduced to structure: letters -> x, digits -> 9, the rest
    kept. Reveals a recurring pattern without any readable content."""
    if not text:
        return ""
    out = re.sub(r"[A-Za-z]", "x", text)
    out = re.sub(r"[0-9]", "9", out)
    return out[:_SHAPE_MAX] + ("…" if len(out) > _SHAPE_MAX else "")


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlsplit(url).netloc or None
    except ValueError:
        return None


def _purpose(rule_id: str, kind: str) -> str:
    return RULE_NOTES.get(rule_id) or PURPOSE_BY_KIND.get(kind, "")


def _schema_rules(conn) -> list[dict]:
    """CHECK, provenance NOT NULL and trigger rules read from the live schema.

    PostgreSQL keeps these separately in `pg_constraint`,
    `information_schema.columns` and `pg_trigger`; reading those catalogs keeps
    the explorer useful after the SQLite backend was removed.
    """
    rules: list[dict] = []

    columns = {
        row["table_name"]: row["columns"]
        for row in conn.execute(
            "SELECT table_name, array_agg(column_name ORDER BY ordinal_position) "
            "AS columns FROM information_schema.columns "
            "WHERE table_schema = current_schema() GROUP BY table_name")
    }
    for table, names in columns.items():
        provenance = [name for name in _PROVENANCE_COLUMNS if name in names]
        if not provenance:
            continue
        notnull = {
            row["column_name"]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s "
                "AND is_nullable = 'NO'", (table,))
        }
        enforced = [name for name in provenance if name in notnull]
        rid = f"provenance:{table}"
        rules.append({
            "id": rid, "kind": "provenance",
            "title": f"{table}: provenance columns",
            "purpose": _purpose(rid, "provenance"),
            "modules": [], "fields": provenance, "table": table,
            "detail": ("NOT NULL: " + ", ".join(enforced)) if enforced
                      else "present but nullable — provenance not enforced",
            "enforced": len(enforced) == len(provenance),
        })

    for row in conn.execute(
            "SELECT c.relname AS table_name, pg_get_constraintdef(co.oid) AS definition "
            "FROM pg_constraint co JOIN pg_class c ON c.oid = co.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE co.contype = 'c' AND n.nspname = current_schema() "
            "ORDER BY c.relname, co.conname"):
        definition = row["definition"] or ""
        match = re.search(
            r"\(\(?([a-z_][a-z0-9_]*)\s*=\s*ANY\s*\(ARRAY\[(.*?)\]",
            definition, re.IGNORECASE)
        if not match:
            continue
        values = re.findall(r"'([^']*)'", match.group(2))
        table, column = row["table_name"], match.group(1)
        rid = f"check:{table}:{column}"
        rules.append({
            "id": rid, "kind": "check", "title": f"{table}.{column}",
            "purpose": _purpose(rid, "check"), "modules": [],
            "fields": [column], "table": table,
            "detail": f"one of: {', '.join(values)}",
        })

    for row in conn.execute(
            "SELECT t.tgname AS name, c.relname AS table_name, "
            "pg_get_triggerdef(t.oid) AS definition "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE NOT t.tgisinternal AND n.nspname = current_schema() "
            "ORDER BY t.tgname"):
        rid = f"trigger:{row['name']}"
        rules.append({
            "id": rid, "kind": "trigger", "title": row["name"],
            "purpose": _purpose(rid, "trigger"), "modules": [], "fields": [],
            "table": row["table_name"], "detail": row["definition"],
        })
    return rules


def _parse_rules(conn, since: str) -> list[dict]:
    rows = conn.execute(
        "SELECT module, field_name, COUNT(*) AS total, "
        "  SUM(CASE WHEN created_at >= %s THEN 1 ELSE 0 END) AS recent, "
        "  MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
        "FROM parse_failures GROUP BY module, field_name "
        "ORDER BY total DESC, module, field_name", (since,)).fetchall()
    out: list[dict] = []
    for row in rows:
        module, field = row["module"], row["field_name"]
        rid = f"parse:{module}:{field or '—'}"
        reasons = [r["reason"] for r in conn.execute(
            "SELECT DISTINCT reason FROM parse_failures "
            "WHERE module = %s AND field_name IS NOT DISTINCT FROM %s AND reason IS NOT NULL "
            "ORDER BY reason LIMIT 8", (module, field)).fetchall()]
        examples = [{
            "field": ex["field_name"],
            "reason": ex["reason"],
            "source_host": _host(ex["source_url"]),
            "at": ex["created_at"],
            "shape": _shape(ex["raw_fragment"]),
            "chars": len(ex["raw_fragment"] or ""),
        } for ex in conn.execute(
            "SELECT field_name, reason, source_url, raw_fragment, created_at "
            "FROM parse_failures WHERE module = %s AND field_name IS NOT DISTINCT FROM %s "
            "ORDER BY created_at DESC LIMIT %s",
            (module, field, _EXAMPLES_PER_RULE)).fetchall()]
        out.append({
            "id": rid, "kind": "parse_failure",
            "title": f"{module}: {field or 'unnamed field'}",
            "purpose": _purpose(rid, "parse_failure"),
            "modules": [module], "fields": [field] if field else [],
            "reasons": reasons,
            "counts": {"total": row["total"], "recent": row["recent"] or 0},
            "first_seen": row["first_seen"], "last_seen": row["last_seen"],
            "examples": examples,
        })
    return out


def _review_rules(conn, since: str) -> list[dict]:
    rows = conn.execute(
        "SELECT module, item_type, "
        "  SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending, "
        "  SUM(CASE WHEN status <> 'pending' THEN 1 ELSE 0 END) AS resolved, "
        "  SUM(CASE WHEN resolved_at >= %s THEN 1 ELSE 0 END) AS resolved_recent, "
        "  COUNT(*) AS total "
        "FROM review_queue GROUP BY module, item_type "
        "ORDER BY pending DESC, module, item_type", (since,)).fetchall()
    out: list[dict] = []
    for row in rows:
        rid = f"review:{row['module']}:{row['item_type']}"
        out.append({
            "id": rid, "kind": "review_gate",
            "title": f"{row['module']}: {row['item_type']}",
            "purpose": _purpose(rid, "review_gate"),
            "modules": [row["module"]], "fields": [],
            "counts": {
                "pending": row["pending"] or 0,
                "resolved": row["resolved"] or 0,
                "resolved_recent": row["resolved_recent"] or 0,
                "total": row["total"],
            },
        })
    return out


def rules(conn, *, today: str | None = None) -> dict:
    as_of = date.fromisoformat(today) if today else date.today()
    since = (as_of - timedelta(days=_WINDOW_DAYS)).isoformat()

    schema = _schema_rules(conn)
    parse = _parse_rules(conn, since)
    review = _review_rules(conn, since)

    by_kind: dict[str, int] = {}
    for rule in (*schema, *parse, *review):
        by_kind[rule["kind"]] = by_kind.get(rule["kind"], 0) + 1

    return {
        "as_of": as_of.isoformat(),
        "window_days": _WINDOW_DAYS,
        "backend": "postgres",
        "schema_rules": schema,
        "observed_rules": [*parse, *review],
        "counts": {"by_kind": by_kind},
        "kinds": ["trigger", "check", "provenance", "parse_failure", "review_gate"],
        "redaction": EXAMPLE_REDACTION,
        "note": "Rules are derived on the request: schema rules from the live "
                "PostgreSQL catalog, observed rules from "
                "parse_failures and review_queue. Purpose text is the only "
                "hand-kept part. Failure examples never carry the raw "
                "fragment.",
    }
