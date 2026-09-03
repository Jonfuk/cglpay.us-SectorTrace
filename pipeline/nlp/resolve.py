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

from pipeline import evidence_state
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.nlp import runs, stage_state
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


def _scoped_mentions_page(conn, source_system: str | None, *, after: str | None,
                          page_size: int) -> list:
    """PROVIDER / COMMISSIONER concept mentions on live chunks, in scope."""
    sql = (
        "SELECT m.document_concept_mention_id,m.document_chunk_id,m.document_element_id,"
        "m.label,m.span_text, "
        "m.element_char_start, m.element_char_end, m.extractor_name, "
        "EXISTS(SELECT 1 FROM document_entity_mentions dem WHERE "
        "dem.document_element_id=m.document_element_id "
        "AND dem.start_offset=m.element_char_start AND dem.end_offset=m.element_char_end "
        "AND dem.matched_text=m.span_text) AS has_entity_resolution, "
        "(SELECT dem.entity_id FROM document_entity_mentions dem WHERE "
        "dem.document_element_id=m.document_element_id "
        "AND dem.start_offset=m.element_char_start AND dem.end_offset=m.element_char_end "
        "AND dem.matched_text=m.span_text ORDER BY dem.document_entity_mention_id LIMIT 1) "
        "AS prior_entity_id "
        "FROM document_concept_mentions m "
        "JOIN document_chunks dc ON dc.document_chunk_id = m.document_chunk_id AND dc.superseded = 0 "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id AND v.is_active = 1 "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE m.superseded = 0 AND m.label IN ('PROVIDER', 'COMMISSIONER') "
        "AND m.document_element_id IS NOT NULL"
    )
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    if after is not None:
        sql += " AND m.document_concept_mention_id > %s"
        params.append(after)
    sql += " ORDER BY m.document_concept_mention_id LIMIT %s"
    params.append(page_size)
    return conn.execute(sql, params).fetchall()


def _resolution_targets(conn, page, providers: dict[str, str]) -> dict[str, str | None]:
    """Resolve one bounded mention page with two bounded lookup queries."""
    provider_candidates = {
        f"provider:{key}" for m in page if m["label"] == "PROVIDER"
        if (key := providers.get(_normalise(m["span_text"]))) is not None
    }
    commissioner_names = {
        _graph_normalise(m["span_text"]) for m in page if m["label"] == "COMMISSIONER"
    }
    existing_providers = set()
    if provider_candidates:
        existing_providers = {row["entity_id"] for row in conn.execute(
            "SELECT entity_id FROM entities WHERE entity_type='PROVIDER' AND entity_id=ANY(%s)",
            (sorted(provider_candidates),))}
    authorities = {}
    if commissioner_names:
        authorities = {row["canonical_name_normalized"]: row["entity_id"]
                       for row in conn.execute(
            "SELECT entity_id,canonical_name_normalized FROM entities "
            "WHERE entity_type='LOCAL_AUTHORITY' AND canonical_name_normalized=ANY(%s)",
            (sorted(commissioner_names),))}
    targets = {}
    for m in page:
        if m["label"] == "PROVIDER":
            key = providers.get(_normalise(m["span_text"]))
            candidate = f"provider:{key}" if key is not None else None
            targets[m["document_concept_mention_id"]] = (
                candidate if candidate in existing_providers else None)
        else:
            targets[m["document_concept_mention_id"]] = authorities.get(
                _graph_normalise(m["span_text"]))
    return targets


def run(
    conn,
    *,
    source_system: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    batch_size: int = 200,
) -> dict:
    """Resolve PROVIDER / COMMISSIONER spans to registered entities. Only an
    exact normalised name match writes a row; everything else is left as a
    concept mention. Idempotent for the scoped elements."""
    config = {"source_system": source_system, "limit": limit}
    run_id = runs.start_run(
        conn, STAGE, config=config, input_scope={"source_system": source_system, "limit": limit}
    )
    providers = _provider_index()
    # Registry contents belong in the per-mention dependency below. Putting
    # the whole registry in this version would make an unrelated authority
    # edit rescan every already-resolved mention.
    resolution_version = stage_state.combined_hash(
        "exact-alias-v2", sorted(_UNSAFE_VARIANTS), sorted(_UNSAFE_PROVIDER_VARIANTS))
    resolved = 0
    processed = 0
    scanned = 0
    skipped = 0
    after_key = None
    batch_ordinal = 0
    state_config = {"method": "exact_normalised_alias"}
    try:
        size = max(1, batch_size)
        while limit is None or scanned < limit:
            page_size = min(size, limit - scanned) if limit is not None else size
            page = _scoped_mentions_page(
                conn, source_system, after=after_key, page_size=page_size)
            if not page:
                break
            after_key = page[-1]["document_concept_mention_id"]
            scanned += len(page)
            hashes = {m["document_concept_mention_id"]: stage_state.content_hash([
                m["document_element_id"], m["label"], m["span_text"],
                m["element_char_start"], m["element_char_end"], m["extractor_name"]])
                for m in page}
            targets = _resolution_targets(conn, page, providers)
            dependencies = {identity: stage_state.combined_hash(
                input_hash, targets[identity], resolution_version)
                for identity, input_hash in hashes.items()}
            pending = stage_state.pending_identities(
                conn, "resolution", [(identity, input_hash, dependencies[identity])
                                     for identity, input_hash in hashes.items()],
                processor_version="exact-alias-v2",
                model_or_ontology_version=resolution_version,
                configuration=state_config, force=force)
            pending.update(m["document_concept_mention_id"] for m in page
                           if not m["has_entity_resolution"])
            batch = [(m, hashes[m["document_concept_mention_id"]]) for m in page
                     if m["document_concept_mention_id"] in pending]
            skipped += len(page) - len(batch)
            batch_resolved = 0
            try:
                if not batch:
                    raise StopIteration
                with conn.raw.transaction():
                    # A changed or now-unresolved input replaces only the
                    # entity mention derived from that exact concept span.
                    conn.execute(
                        "DELETE FROM document_entity_mentions dem USING "
                        "document_concept_mentions m WHERE "
                        "m.document_concept_mention_id=ANY(%s) "
                        "AND dem.document_element_id=m.document_element_id "
                        "AND dem.start_offset=m.element_char_start "
                        "AND dem.end_offset=m.element_char_end "
                        "AND dem.matched_text=m.span_text",
                        ([m["document_concept_mention_id"] for m, _ in batch],),
                    )
                    values = []
                    for m, input_hash in batch:
                        method = f"{m['extractor_name']}+alias"
                        entity_id = targets[m["document_concept_mention_id"]]
                        if entity_id is not None:
                            values.append(
                                (
                                    _mention_id(
                                        m["document_element_id"],
                                        entity_id,
                                        m["element_char_start"],
                                        m["element_char_end"],
                                        method,
                                    ),
                                    m["document_element_id"],
                                    entity_id,
                                    m["span_text"],
                                    method,
                                    m["element_char_start"],
                                    m["element_char_end"],
                                )
                            )
                            batch_resolved += 1
                        if m["prior_entity_id"] != entity_id:
                            stage_state.invalidate_downstream(
                                conn, "resolution", m["document_concept_mention_id"],
                                [m["document_chunk_id"]])
                        stage_state.mark_complete(
                            conn,
                            "resolution",
                            m["document_concept_mention_id"],
                            input_hash,
                            processor_version="exact-alias-v2",
                            output={"entity_id": entity_id},
                            model_or_ontology_version=resolution_version,
                            configuration=state_config,
                            dependency_hash=dependencies[m["document_concept_mention_id"]],
                            run_id=run_id,
                        )
                        evidence_state.observe(
                            conn,
                            layer="entity_mention",
                            identity=m["document_concept_mention_id"],
                            evidence_hash=stage_state.content_hash(
                                [
                                    entity_id,
                                    m["span_text"],
                                    m["element_char_start"],
                                    m["element_char_end"],
                                ]
                            ),
                            provenance={
                                "entity_id": entity_id,
                                "match_method": method,
                                "nlp_run_id": run_id,
                                "unresolved": entity_id is None,
                            },
                        )
                    conn.executemany(
                        "INSERT INTO document_entity_mentions(document_entity_mention_id,"
                        "document_element_id,entity_id,matched_text,match_method,start_offset,"
                        "end_offset) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT(document_entity_mention_id) DO NOTHING",
                        values,
                    )
                resolved += batch_resolved
                processed += len(batch)
            except StopIteration:
                pass
            except Exception as input_exc:
                for m, input_hash in batch:
                    stage_state.mark_failed(
                        conn,
                        "resolution",
                        m["document_concept_mention_id"],
                        input_hash,
                        processor_version="exact-alias-v2",
                        error=input_exc,
                        run_id=run_id,
                        model_or_ontology_version=resolution_version,
                        configuration=state_config,
                        dependency_hash=dependencies[m["document_concept_mention_id"]],
                    )
                raise
            if not dry_run:
                stage_state.checkpoint(
                    conn,
                    run_id=run_id,
                    stage="resolution",
                    batch_ordinal=batch_ordinal,
                    last_input_identity=after_key,
                    rows_processed=scanned,
                    rows_written=resolved,
                )
                conn.commit()
            batch_ordinal += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(
            conn,
            run_id,
            status="failed",
            rows_processed=processed,
            rows_written=resolved,
            error=f"{type(exc).__name__}: {exc}",
        )
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=processed, rows_written=resolved)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {
        "run_id": run_id,
        "candidates": processed,
        "resolved": resolved,
        "skipped_unchanged": skipped,
        "dry_run": dry_run,
    }
