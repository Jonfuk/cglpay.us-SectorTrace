"""Record revision comparison (BETA-092).

Two rows that represent the same thing at two points in time, diffed
field-aware (procurement notices sharing an OCID) and text-aware (two parsed
versions of one document). The point of the labels is the one the rationale
names: a change to a **source** field is an amendment the *publisher* made; a
change to a **derived** field is a normalisation this pipeline recomputed
between collections, with the underlying record possibly unchanged. The two
are counted separately and never added.

Read-only. Documents are gated by the same `DOCUMENT_SEARCH_SOURCES`
allowlist as `document_search` — a source that is not searchable there is not
diffable here either.
"""
from __future__ import annotations

import sqlite3

from pipeline.web.public_queries import (
    DOCUMENT_SEARCH_SOURCES,
    _one,
    _public,
    _rows,
)
from pipeline.web.queries import QueryError

# Each contract field, and whether it is verbatim from the OCDS release
# (`source`) or something this pipeline computes/matches (`derived`).
_CONTRACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("notice_type", "source"),
    ("title", "source"),
    ("description", "source"),
    ("buyer_name", "source"),
    ("buyer_ons_code", "derived"),
    ("value_core", "source"),
    ("value_max", "source"),
    ("currency", "source"),
    ("date_published", "source"),
    ("date_start", "source"),
    ("date_end", "source"),
    ("procedure_type", "source"),
    ("cpv_codes", "source"),
    ("psr_basis", "derived"),
    ("psr_direct_award_option", "source"),
)

_VERSION_META: tuple[str, ...] = (
    "parser_name", "parser_version", "parse_schema_version",
    "config_hash", "text_sha256", "status", "is_active", "created_at",
)

_TEXT_ELEMENTS_MAX = 600

_DIFF_NOTE = (
    "A change to a 'source' field is an amendment the publisher made. A change "
    "to a 'derived' field is a normalisation or match this pipeline recomputed "
    "between collections — the underlying record may be unchanged. The two "
    "counts are reported separately and never added."
)


def _contract_row(conn: sqlite3.Connection, notice_id: str) -> dict | None:
    return _one(
        conn,
        "SELECT notice_id, ocid, notice_type, title, description, buyer_name, "
        " buyer_ons_code, value_core, value_max, currency, date_published, "
        " date_start, date_end, procedure_type, cpv_codes, psr_basis, "
        " psr_direct_award_option, source_url, retrieved_at "
        "FROM contracts WHERE notice_id = ? "
        "ORDER BY supplier_id LIMIT 1",
        (notice_id,)) or None


def ocds_diff(conn: sqlite3.Connection, *, a=None, b=None, ocid=None) -> dict:
    """Field-aware diff of two procurement notices. Pass explicit `a`/`b`
    notice ids, or an `ocid` to diff its two most recently published
    notices."""
    _public(["contracts"])
    if ocid and not (a and b):
        recent = _rows(
            conn,
            "SELECT DISTINCT notice_id, date_published FROM contracts "
            "WHERE ocid = ? ORDER BY date_published DESC, notice_id DESC "
            "LIMIT 2", (ocid,))
        if len(recent) < 2:
            raise QueryError(f"OCID {ocid!r} has fewer than two notices to compare.")
        b, a = recent[0]["notice_id"], recent[1]["notice_id"]

    row_a, row_b = _contract_row(conn, a), _contract_row(conn, b)
    if row_a is None or row_b is None:
        missing = a if row_a is None else b
        raise QueryError(f"No procurement notice {missing!r}.")

    fields = []
    for name, cls in _CONTRACT_FIELDS:
        av, bv = row_a.get(name), row_b.get(name)
        fields.append({"field": name, "class": cls,
                        "a": av, "b": bv, "changed": av != bv})
    changed = [f for f in fields if f["changed"]]

    return {
        "kind": "ocds",
        "a": {"notice_id": a, "ocid": row_a["ocid"],
              "retrieved_at": row_a["retrieved_at"], "source_url": row_a["source_url"]},
        "b": {"notice_id": b, "ocid": row_b["ocid"],
              "retrieved_at": row_b["retrieved_at"], "source_url": row_b["source_url"]},
        "same_ocid": row_a["ocid"] == row_b["ocid"],
        "fields": fields,
        "counts": {
            "changed_source": sum(1 for f in changed if f["class"] == "source"),
            "changed_derived": sum(1 for f in changed if f["class"] == "derived"),
        },
        "note": _DIFF_NOTE,
    }


def _version_row(conn: sqlite3.Connection, version_id: str) -> dict | None:
    return _one(
        conn,
        "SELECT v.document_version_id, v.document_id, v.parser_name, "
        " v.parser_version, v.parse_schema_version, v.config_hash, "
        " v.text_sha256, v.status, v.is_active, v.created_at, d.title, "
        " e.source_system "
        "FROM document_versions v "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE v.document_version_id = ?",
        (version_id,)) or None


def document_version_diff(conn: sqlite3.Connection, *,
                           a=None, b=None, document_id=None) -> dict:
    """Metadata diff plus a text-aware, element-aligned diff of two parsed
    versions of one document. Pass explicit version ids, or a `document_id`
    to diff its two most recent versions."""
    _public(["document_versions", "document_records", "document_elements",
              "evidence_records"])
    if document_id and not (a and b):
        recent = _rows(
            conn,
            "SELECT v.document_version_id FROM document_versions v "
            "JOIN document_records d ON d.document_id = v.document_id "
            "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
            "WHERE v.document_id = ? AND e.source_system IN (%s) "
            "ORDER BY v.created_at DESC LIMIT 2"
            % ",".join("?" * len(DOCUMENT_SEARCH_SOURCES)),
            (document_id, *DOCUMENT_SEARCH_SOURCES))
        if len(recent) < 2:
            raise QueryError(
                f"Document {document_id!r} has fewer than two comparable versions.")
        b, a = recent[0]["document_version_id"], recent[1]["document_version_id"]

    va, vb = _version_row(conn, a), _version_row(conn, b)
    if va is None or vb is None:
        missing = a if va is None else b
        raise QueryError(f"No document version {missing!r}.")
    if va["document_id"] != vb["document_id"]:
        raise QueryError("Those versions belong to different documents.")
    for row in (va, vb):
        if row["source_system"] not in DOCUMENT_SEARCH_SOURCES:
            raise QueryError("That document is not comparable on the portal.")

    meta = [{"field": name, "a": va.get(name), "b": vb.get(name),
             "changed": va.get(name) != vb.get(name)}
            for name in _VERSION_META]

    def _elements(version_id: str) -> dict[int, dict]:
        return {r["sequence"]: r for r in _rows(
            conn,
            "SELECT sequence, element_type, text, text_sha256 "
            "FROM document_elements WHERE document_version_id = ? "
            "ORDER BY sequence LIMIT ?",
            (version_id, _TEXT_ELEMENTS_MAX + 1))}

    ea, eb = _elements(a), _elements(b)
    sequences = sorted(set(ea) | set(eb))
    truncated = len(sequences) > _TEXT_ELEMENTS_MAX
    sequences = sequences[:_TEXT_ELEMENTS_MAX]

    text_changes: list[dict] = []
    added = removed = changed = 0
    for seq in sequences:
        ra, rb = ea.get(seq), eb.get(seq)
        if ra and not rb:
            kind, removed = "removed", removed + 1
        elif rb and not ra:
            kind, added = "added", added + 1
        elif ra["text_sha256"] == rb["text_sha256"]:
            continue
        else:
            kind, changed = "changed", changed + 1
        text_changes.append({
            "sequence": seq,
            "element_type": (rb or ra)["element_type"],
            "a": ra["text"] if ra else None,
            "b": rb["text"] if rb else None,
            "kind": kind,
        })

    return {
        "kind": "document",
        "document_id": va["document_id"],
        "title": va["title"],
        "a": {"document_version_id": a, "created_at": va["created_at"],
              "parser": f"{va['parser_name']} {va['parser_version']}"},
        "b": {"document_version_id": b, "created_at": vb["created_at"],
              "parser": f"{vb['parser_name']} {vb['parser_version']}"},
        "meta": meta,
        "text_changes": text_changes,
        "counts": {"added": added, "removed": removed, "changed": changed},
        "truncated": truncated,
        "note": "A metadata change (parser, schema, config hash) explains a "
                "text change that is not a source amendment: the bytes are the "
                "same, the parser read them differently. Element alignment is "
                "by sequence; unchanged elements are omitted.",
    }


def record_diff(conn: sqlite3.Connection, *, kind, a=None, b=None,
                 ocid=None, document_id=None) -> dict:
    if kind == "ocds":
        return ocds_diff(conn, a=a, b=b, ocid=ocid)
    if kind == "document":
        return document_version_diff(conn, a=a, b=b, document_id=document_id)
    raise QueryError(f"kind must be 'ocds' or 'document', got {kind!r}.")
