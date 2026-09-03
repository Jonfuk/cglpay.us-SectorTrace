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

from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp import runs

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


def _live_chunk_elements(conn, document_version_id: str) -> list[str]:
    """Distinct element ids covered by this version's non-superseded chunks,
    resolved through the chunk's `element_start_id`..`element_end_id`
    sequence range."""
    rows = conn.execute(
        "SELECT DISTINCT de.document_element_id AS eid, de.sequence AS seq "
        "FROM document_chunks dc "
        "JOIN document_elements s ON s.document_element_id = dc.element_start_id "
        "JOIN document_elements e ON e.document_element_id = dc.element_end_id "
        "JOIN document_elements de ON de.document_version_id = dc.document_version_id "
        "  AND de.sequence BETWEEN s.sequence AND e.sequence "
        "WHERE dc.document_version_id = %s AND dc.superseded = 0 "
        "ORDER BY de.sequence",
        (document_version_id,)).fetchall()
    return [row["eid"] for row in rows]


def label_version(conn, onto: ontology_mod.Ontology, document_version_id: str,
                  nlp_run_id: str | None) -> int:
    """(Re)label one version's chunked elements. Idempotent: its own
    `ontology_v1` rows for those elements are cleared first, then rewritten;
    `keyword_v1` rows are never touched. Returns rows written."""
    element_ids = _live_chunk_elements(conn, document_version_id)
    if not element_ids:
        return 0
    placeholders = ",".join("%s" for _ in element_ids)
    # Clear only this stage's own prior output for these elements. keyword_v1
    # rows carry UPPERCASE bucket topics and are never in this set.
    conn.execute(
        f"DELETE FROM document_topics WHERE match_method = %s "
        f"AND document_element_id IN ({placeholders})",
        [MATCH_METHOD, *element_ids])

    texts = {
        row["document_element_id"]: (row["text"] or "")
        for row in conn.execute(
            f"SELECT document_element_id, text FROM document_elements "
            f"WHERE document_element_id IN ({placeholders})", element_ids)}

    written = 0
    for element_id in element_ids:
        for topic, count in label_text(onto, texts.get(element_id, "")).items():
            # ON CONFLICT is a belt-and-braces guard: the DELETE above already
            # cleared any ontology_v1 row, and the WHERE makes doubly sure a
            # keyword_v1 row is never overwritten if the topic strings ever
            # did collide.
            conn.execute(
                "INSERT INTO document_topics (document_element_id, topic, match_count, match_method) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT(document_element_id, topic) DO UPDATE SET match_count = excluded.match_count "
                "WHERE document_topics.match_method = excluded.match_method",
                (element_id, topic, count, MATCH_METHOD))
            written += 1
    return written


def _versions_with_live_chunks(conn, source_system: str | None,
                               limit: int | None) -> list[str]:
    sql = (
        "SELECT DISTINCT dc.document_version_id AS vid, MIN(dc.created_at) AS created "
        "FROM document_chunks dc "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE dc.superseded = 0")
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    sql += " GROUP BY dc.document_version_id ORDER BY created"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return [row["vid"] for row in conn.execute(sql, params).fetchall()]


def run(conn, *, source_system: str | None = None, limit: int | None = None,
        dry_run: bool = False) -> dict:
    """Label every chunked, non-superseded document version (optionally scoped
    by source system). Bounded by `limit`; safe to repeat."""
    onto = ontology_mod.default()
    config = {"ontology_version": onto.version, "match_method": MATCH_METHOD,
              "source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config, ontology_version=onto.version,
                            input_scope={"source_system": source_system, "limit": limit})
    versions = _versions_with_live_chunks(conn, source_system, limit)
    written = 0
    try:
        for version_id in versions:
            written += label_version(conn, onto, version_id, run_id)
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=len(versions),
                        rows_written=written, error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(versions),
                    rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"run_id": run_id, "ontology_version": onto.version,
            "versions": len(versions), "rows": written, "dry_run": dry_run}
