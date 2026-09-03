"""Deterministic ontology labelling — `document_chunks` -> provisional
`document_topics` rows with `match_method = 'ontology_v1'`.

The 034C layer over the ontology (034B). For every live chunk it runs the
ontology's whole-token matcher over each element the chunk covers and records,
per element:

  * one row per concept found   `topic = <concept_id>`
        e.g. `workforce.recruitment_difficulty`
  * one row per category found  `topic = 'cat:' + <category>`
        e.g. `cat:workforce`

`match_count` is the number of distinct alias spans in that element (concept
rows) or the sum across the category's concepts (category rows).

The rows are PROVISIONAL. An ontology hit means the wording is present, not
that a claim is true — negation and context are 034E's job, and nothing is
promoted to a claim or attributed to a provider without a person.

`keyword_v1` is left entirely alone. Its topics are UPPERCASE buckets
(`classify.TOPICS`); `ontology_v1` topics are dotted concept ids or
`cat:`-prefixed categories, so the two never collide on `document_topics`'
`(document_element_id, topic)` primary key. This stage deletes and rewrites
only its own `ontology_v1` rows.
"""

from __future__ import annotations

from pipeline.config import get_settings
from pipeline.nlp import accelerator, runs, stage_state
from pipeline.nlp import ontology as ontology_mod

STAGE = "label"
MATCH_METHOD = "ontology_v1"
CATEGORY_PREFIX = "cat:"


def label_text(onto: ontology_mod.Ontology, text: str) -> dict[str, int]:
    """`{topic: match_count}` for one element's text: a concept id per concept
    found plus a `cat:<category>` rollup. Pure — no DB."""
    concept_counts = onto.match_counts(text)
    if not concept_counts:
        return {}
    topics: dict[str, int] = dict(concept_counts)
    for concept_id, count in concept_counts.items():
        concept = onto.concept(concept_id)
        if concept is None:  # pragma: no cover - match_counts only yields known ids
            continue
        for category in concept.categories:
            key = CATEGORY_PREFIX + category
            topics[key] = topics.get(key, 0) + count
    return topics


def _topics_from_matches(onto: ontology_mod.Ontology, matches) -> dict[str, int]:
    concept_counts: dict[str, int] = {}
    for match in matches:
        concept_counts[match.concept_id] = concept_counts.get(match.concept_id, 0) + 1
    topics = dict(concept_counts)
    for concept_id, count in concept_counts.items():
        concept = onto.concept(concept_id)
        if concept is None:
            continue
        for category in concept.categories:
            key = CATEGORY_PREFIX + category
            topics[key] = topics.get(key, 0) + count
    return topics


def label_chunk(conn, onto: ontology_mod.Ontology, chunk_row, nlp_run_id: str | None,
                *, accelerator_mode: str = "python") -> int:
    rows = conn.execute(
        "SELECT de.document_element_id,de.text FROM document_elements de "
        "JOIN document_elements s ON s.document_element_id=%s "
        "JOIN document_elements z ON z.document_element_id=%s "
        "WHERE de.document_version_id=%s AND de.sequence BETWEEN s.sequence AND z.sequence "
        "ORDER BY de.sequence",
        (
            chunk_row["element_start_id"],
            chunk_row["element_end_id"],
            chunk_row["document_version_id"],
        ),
    ).fetchall()
    element_ids = [row["document_element_id"] for row in rows]
    if not element_ids:
        return 0
    conn.execute(
        "DELETE FROM document_topics WHERE match_method=%s AND document_element_id=ANY(%s)",
        (MATCH_METHOD, element_ids),
    )
    values = []
    match_batches = accelerator.ontology_matches(
        onto, [row["text"] or "" for row in rows], mode=accelerator_mode)
    for row, matches in zip(rows, match_batches):
        for topic, count in _topics_from_matches(onto, matches).items():
            values.append((row["document_element_id"], topic, count, MATCH_METHOD))
    conn.executemany(
        "INSERT INTO document_topics(document_element_id,topic,match_count,match_method) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT(document_element_id,topic) DO UPDATE SET "
        "match_count=excluded.match_count WHERE document_topics.match_method=excluded.match_method",
        values,
    )
    return len(values)


def _live_chunks_page(conn, source_system: str | None, *, after: str | None,
                      page_size: int) -> list:
    sql = (
        "SELECT dc.document_chunk_id,dc.document_version_id,dc.text_sha256,"
        "dc.element_start_id,dc.element_end_id "
        "FROM document_chunks dc "
        "JOIN document_versions v ON v.document_version_id=dc.document_version_id AND v.is_active=1 "
        "JOIN document_records d ON d.document_id=v.document_id "
        "JOIN evidence_records e ON e.evidence_id=d.evidence_id WHERE dc.superseded=0"
    )
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    if after is not None:
        sql += " AND dc.document_chunk_id > %s"
        params.append(after)
    sql += " ORDER BY dc.document_chunk_id LIMIT %s"
    params.append(page_size)
    return conn.execute(sql, params).fetchall()


def run(
    conn,
    *,
    source_system: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    batch_size: int = 200,
) -> dict:
    """Label every chunked, non-superseded document version (optionally scoped
    by source system). Bounded by `limit`; safe to repeat."""
    onto = ontology_mod.default()
    accelerator_mode = get_settings().nlp_accelerator
    # Selection is explicit even while the compiled kernel remains gated on
    # parity. Forced Mojo therefore fails rather than silently using Python;
    # auto emits one diagnostic and proceeds with the authoritative trie.
    accelerator.select(accelerator_mode)
    config = {
        "ontology_version": onto.version,
        "match_method": MATCH_METHOD,
        "source_system": source_system,
        "limit": limit,
        "accelerator": accelerator_mode,
    }
    run_id = runs.start_run(
        conn,
        STAGE,
        config=config,
        ontology_version=onto.version,
        input_scope={"source_system": source_system, "limit": limit},
    )
    state_config = {"match_method": MATCH_METHOD, "accelerator": accelerator_mode}
    written = 0
    processed = 0
    scanned = 0
    skipped = 0
    version_ids = set()
    after_key = None
    batch_ordinal = 0
    try:
        while limit is None or scanned < limit:
            size = min(max(1, batch_size), limit - scanned) if limit is not None else max(1, batch_size)
            page = _live_chunks_page(conn, source_system, after=after_key, page_size=size)
            if not page:
                break
            after_key = page[-1]["document_chunk_id"]
            scanned += len(page)
            dependencies = {row["document_chunk_id"]: stage_state.combined_hash(
                row["text_sha256"], onto.version) for row in page}
            pending = stage_state.pending_identities(
                conn, "labels", [(row["document_chunk_id"], row["text_sha256"],
                                  dependencies[row["document_chunk_id"]]) for row in page],
                processor_version="token-trie-v1",
                model_or_ontology_version=onto.version,
                configuration=state_config, force=force)
            skipped += len(page) - len(pending)
            for chunk_row in page:
                chunk_id = chunk_row["document_chunk_id"]
                if chunk_id not in pending:
                    continue
                try:
                    with conn.raw.transaction():
                        count = label_chunk(
                            conn, onto, chunk_row, run_id,
                            accelerator_mode=accelerator_mode)
                        output = conn.execute(
                            "SELECT topic,match_count FROM document_topics WHERE match_method=%s "
                            "AND document_element_id IN (SELECT de.document_element_id "
                            "FROM document_elements de JOIN document_elements s "
                            "ON s.document_element_id=%s JOIN document_elements z "
                            "ON z.document_element_id=%s WHERE de.document_version_id=%s "
                            "AND de.sequence BETWEEN s.sequence AND z.sequence) ORDER BY topic",
                            (MATCH_METHOD, chunk_row["element_start_id"],
                             chunk_row["element_end_id"],
                             chunk_row["document_version_id"])).fetchall()
                        stage_state.mark_complete(
                            conn, "labels", chunk_id, chunk_row["text_sha256"],
                            processor_version="token-trie-v1",
                            model_or_ontology_version=onto.version,
                            configuration=state_config, dependency_hash=dependencies[chunk_id],
                            output=[dict(row) for row in output], run_id=run_id)
                        written += count
                        processed += 1
                        version_ids.add(chunk_row["document_version_id"])
                except Exception as input_exc:
                    stage_state.mark_failed(
                        conn, "labels", chunk_id, chunk_row["text_sha256"],
                        processor_version="token-trie-v1", error=input_exc, run_id=run_id,
                        model_or_ontology_version=onto.version, configuration=state_config,
                        dependency_hash=dependencies[chunk_id])
                    raise
            if not dry_run:
                stage_state.checkpoint(
                    conn, run_id=run_id, stage="labels", batch_ordinal=batch_ordinal,
                    last_input_identity=after_key, rows_processed=scanned, rows_written=written)
                conn.commit()
            batch_ordinal += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(
            conn,
            run_id,
            status="failed",
            rows_processed=processed,
            rows_written=written,
            error=f"{type(exc).__name__}: {exc}",
        )
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=processed, rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {
        "run_id": run_id,
        "ontology_version": onto.version,
        "versions": len(version_ids),
        "chunks": processed,
        "rows": written,
        "skipped_unchanged": skipped,
        "dry_run": dry_run,
    }
