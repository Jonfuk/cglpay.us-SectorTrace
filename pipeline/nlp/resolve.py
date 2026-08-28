"""Deterministic entity resolution — `document_concept_mentions` (PROVIDER /
COMMISSIONER spans) -> `document_entity_mentions`.

034D, and a hard boundary: a GLiNER / stub span is a *candidate*, and only an
exact, deterministic name match turns it into an entity mention. There is no
fuzzy matching and no model here. A span that does not resolve stays a bare
concept mention -- a lead for a person, not an attribution.

* PROVIDER spans are matched, whole-string after normalisation, against the
  maintained provider name variants (`keywords.SUPPLIER_NAME_VARIANTS`) and,
  on a hit, linked to the Evidence Graph entity `provider:<provider_key>`
  when that entity exists (it is seeded by `pipeline graph backfill`).
* COMMISSIONER spans are matched against `entities` rows of type
  `LOCAL_AUTHORITY` by canonical normalised name. Generic commissioner
  concepts (OHID, ICB, …) have no entity and stay unresolved.

`match_method` records how: `'<extractor>+alias'`. `document_entity_mentions`
is written at the element grain it already uses (migration 0053), with the
element-relative offsets `document_concept_mentions` carried for exactly this.
"""
from __future__ import annotations

import hashlib
import re

from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.nlp import runs
from pipeline.nlp.ontology import _UNSAFE_VARIANTS, _normalise
from pipeline.nlp.spans import _UNSAFE_PROVIDER_VARIANTS

STAGE = "resolve"

# Element ids per DELETE. Well under psycopg's 65535-parameter hard limit,
# and SQLite's default SQLITE_MAX_VARIABLE_NUMBER (999 before 3.32, 32766
# after) — one statement, both engines.
_DELETE_BATCH = 900


def _provider_index() -> dict[str, str]:
    """normalised full variant -> provider_key. Whole-string, not whole-token:
    a PROVIDER span already *is* a name, so the bar is that the whole span
    equals a known variant once normalised."""
    index: dict[str, str] = {}
    for provider_key, variants in SUPPLIER_NAME_VARIANTS.items():
        for variant in variants:
            if variant.strip().lower() in _UNSAFE_PROVIDER_VARIANTS:
                continue
            norm = _normalise(variant)
            if norm and norm not in _UNSAFE_VARIANTS:
                index.setdefault(norm, provider_key)
    return index


def _graph_normalise(value: str) -> str:
    # The normaliser pipeline/graph/backfill.py used to write
    # entities.canonical_name_normalized. Kept in step deliberately.
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _mention_id(element_id: str, entity_id: str, start, end, method: str) -> str:
    seed = f"{element_id}|{entity_id}|{start}|{end}|{method}"
    return "dem-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _scoped_mentions(conn, source_system: str | None, limit: int | None) -> list:
    """PROVIDER / COMMISSIONER concept mentions on live chunks, in scope."""
    sql = (
        "SELECT m.document_concept_mention_id, m.document_element_id, m.label, m.span_text, "
        "m.element_char_start, m.element_char_end, m.extractor_name "
        "FROM document_concept_mentions m "
        "JOIN document_chunks dc ON dc.document_chunk_id = m.document_chunk_id AND dc.superseded = 0 "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE m.superseded = 0 AND m.label IN ('PROVIDER', 'COMMISSIONER') "
        "AND m.document_element_id IS NOT NULL")
    params: list = []
    if source_system:
        sql += " AND e.source_system = ?"
        params.append(source_system)
    sql += " ORDER BY m.document_concept_mention_id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def _local_authority_index(conn) -> dict[str, str]:
    return {
        row["canonical_name_normalized"]: row["entity_id"]
        for row in conn.execute(
            "SELECT entity_id, canonical_name_normalized FROM entities "
            "WHERE entity_type = 'LOCAL_AUTHORITY'")}


def _provider_entity_exists(conn, entity_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM entities WHERE entity_id = ? AND entity_type = 'PROVIDER'",
        (entity_id,)).fetchone() is not None


def run(conn, *, source_system: str | None = None, limit: int | None = None,
        dry_run: bool = False) -> dict:
    """Resolve PROVIDER / COMMISSIONER spans to registered entities. Only an
    exact normalised name match writes a row; everything else is left as a
    concept mention. Idempotent for the scoped elements."""
    config = {"source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config,
                            input_scope={"source_system": source_system, "limit": limit})
    mentions = _scoped_mentions(conn, source_system, limit)
    providers = _provider_index()
    authorities = _local_authority_index(conn)

    element_ids = sorted({m["document_element_id"] for m in mentions})
    resolved = 0
    try:
        # Batched: one `?` per element id, and a full-corpus resolve carries
        # more distinct elements than psycopg's 65535-parameter ceiling. The
        # DELETE only clears this run's own prior `%+alias` rows so the write
        # below is idempotent, so splitting it across statements is harmless.
        for start in range(0, len(element_ids), _DELETE_BATCH):
            batch = element_ids[start:start + _DELETE_BATCH]
            placeholders = ",".join("?" for _ in batch)
            conn.execute(
                f"DELETE FROM document_entity_mentions WHERE match_method LIKE '%+alias' "
                f"AND document_element_id IN ({placeholders})", batch)

        for m in mentions:
            method = f"{m['extractor_name']}+alias"
            norm = _normalise(m["span_text"])
            entity_id: str | None = None
            if m["label"] == "PROVIDER":
                key = providers.get(norm)
                if key is not None:
                    candidate = f"provider:{key}"
                    if _provider_entity_exists(conn, candidate):
                        entity_id = candidate
            else:  # COMMISSIONER
                entity_id = authorities.get(_graph_normalise(m["span_text"]))
            if entity_id is None:
                continue
            conn.execute(
                "INSERT INTO document_entity_mentions (document_entity_mention_id, "
                "document_element_id, entity_id, matched_text, match_method, start_offset, end_offset) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(document_entity_mention_id) DO NOTHING",
                (_mention_id(m["document_element_id"], entity_id, m["element_char_start"],
                             m["element_char_end"], method),
                 m["document_element_id"], entity_id, m["span_text"], method,
                 m["element_char_start"], m["element_char_end"]))
            resolved += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=len(mentions),
                        rows_written=resolved, error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(mentions), rows_written=resolved)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"run_id": run_id, "candidates": len(mentions), "resolved": resolved,
            "dry_run": dry_run}
