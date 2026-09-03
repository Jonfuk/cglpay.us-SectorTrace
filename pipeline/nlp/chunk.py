"""Paragraph-level chunking of `document_elements`.

Retrieval and every span-level annotation downstream work on chunks, not on
raw elements (too small, no context) and not on whole documents (too coarse
to cite). A chunk is a contiguous run of body elements merged to a token
target, never split mid-element — docling's elements are already
paragraph-sized, and splitting one would put half a sentence in each of two
chunks.

Two properties the rest of the layer depends on:

* **Content-derived id.** `document_chunk_id` is a hash of the version, the
  chunker name+version, the chunk index and the chunk's own text. Change the
  chunker and the ids change with it — an id can never quietly come to mean
  different text. Old-version chunks are marked `superseded`, not deleted, so
  a re-chunk and its embeddings/annotations can coexist during a migration.
* **Element-level provenance.** Every chunk records `element_start_id` /
  `element_end_id`, so the trail is chunk -> elements -> document_version ->
  archived payload, not a reconstruction from character offsets alone.
  `char_start` / `char_end` are offsets into the version's concatenated
  element text, for mapping a within-chunk span back to the whole document.
"""

from __future__ import annotations

import hashlib

from pipeline.nlp import runs, stage_state

CHUNKER_NAME = "paragraph"
CHUNKER_VERSION = "1"

# A body element is merged into a chunk; a heading flushes the current chunk
# and is remembered as the chunk's section context instead. docling emits
# `heading_level` on headings; some parsers only vary `element_type`.
_HEADING_TYPES = frozenset({"title", "section_header", "heading", "header", "subtitle"})

TARGET_TOKENS = 180
MAX_TOKENS = 400


def _is_heading(element) -> bool:
    if element["heading_level"] is not None:
        return True
    kind = (element["element_type"] or "").strip().lower()
    return kind in _HEADING_TYPES or kind.endswith("_header")


def _tokens(text: str) -> int:
    return len(text.split())


def _chunk_id(version_id: str, index: int, text_sha256: str) -> str:
    seed = f"{version_id}|{CHUNKER_NAME}|{CHUNKER_VERSION}|{index}|{text_sha256}"
    return "dc-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_chunks(elements: list) -> list[dict]:
    """Chunk one version's ordered elements. Pure — no DB, no ids beyond the
    content hash — so it is trivially testable against a fixture.

    `elements` rows carry: document_element_id, element_type, page_number,
    heading_level, text, in `sequence` order.
    """
    # The version's full text, elements joined by newline. A buffered run is
    # always contiguous in this list (a heading between two body elements
    # flushes the buffer), so a chunk's own "\n".join matches this slice
    # exactly and char_end = char_start + len(text).
    offsets: list[int] = []
    running = 0
    texts = [(e["text"] or "") for e in elements]
    for text in texts:
        offsets.append(running)
        running += len(text) + 1  # + newline separator

    chunks: list[dict] = []
    buffer: list[int] = []  # indices into `elements`
    buffer_tokens = 0
    heading_id: str | None = None
    index = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens, index
        if not buffer:
            return
        first, last = buffer[0], buffer[-1]
        body = "\n".join(texts[i] for i in buffer)
        text_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        pages = [
            elements[i]["page_number"] for i in buffer if elements[i]["page_number"] is not None
        ]
        char_start = offsets[first]
        chunks.append(
            {
                # `document_chunk_id` is assigned by chunk_version(), which knows
                # the version id; build_chunks stays pure and version-agnostic.
                "chunk_index": index,
                "text": body,
                "text_sha256": text_sha256,
                "token_estimate": buffer_tokens,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "element_start_id": elements[first]["document_element_id"],
                "element_end_id": elements[last]["document_element_id"],
                "preceding_heading_element_id": heading_id,
                "char_start": char_start,
                "char_end": char_start + len(body),
            }
        )
        index += 1
        buffer = []
        buffer_tokens = 0

    for i, element in enumerate(elements):
        if _is_heading(element):
            flush()
            heading_id = element["document_element_id"]
            continue
        if not texts[i].strip():
            continue
        buffer.append(i)
        buffer_tokens += _tokens(texts[i])
        if buffer_tokens >= TARGET_TOKENS:
            flush()
    flush()
    return chunks


def _elements(conn, document_version_id: str) -> list:
    return conn.execute(
        "SELECT document_element_id, element_type, page_number, heading_level, text "
        "FROM document_elements WHERE document_version_id=%s ORDER BY sequence",
        (document_version_id,),
    ).fetchall()


def chunk_version(conn, document_version_id: str, nlp_run_id: str | None = None) -> int:
    """(Re)chunk one active document version. Idempotent for a fixed
    CHUNKER_VERSION; a bumped version supersedes the old rows rather than
    dropping them. Returns the number of chunks written."""
    elements = _elements(conn, document_version_id)
    chunks = build_chunks(elements)
    now = runs.utcnow()
    # Retire the current ordinal rows before inserting their content-addressed
    # replacements. Updating a row's primary key would both erase chunk
    # history and break references held by downstream NLP tables.
    conn.execute(
        "UPDATE document_chunks SET superseded=1 WHERE document_version_id=%s "
        "AND chunker_name=%s AND chunker_version=%s AND superseded=0",
        (document_version_id, CHUNKER_NAME, CHUNKER_VERSION),
    )
    for chunk in chunks:
        chunk_id = _chunk_id(document_version_id, chunk["chunk_index"], chunk["text_sha256"])
        conn.execute(
            "INSERT INTO document_chunks (document_chunk_id, document_version_id, chunker_name, "
            "chunker_version, chunk_index, text, text_sha256, token_estimate, page_start, page_end, "
            "element_start_id, element_end_id, preceding_heading_element_id, char_start, char_end, "
            "superseded, nlp_run_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s) "
            "ON CONFLICT(document_chunk_id) DO UPDATE SET "
            "text=excluded.text, text_sha256=excluded.text_sha256, "
            "token_estimate=excluded.token_estimate, "
            "page_start=excluded.page_start, page_end=excluded.page_end, "
            "element_start_id=excluded.element_start_id, element_end_id=excluded.element_end_id, "
            "preceding_heading_element_id=excluded.preceding_heading_element_id, "
            "char_start=excluded.char_start, char_end=excluded.char_end, superseded=0, "
            "nlp_run_id=excluded.nlp_run_id, created_at=excluded.created_at",
            (
                chunk_id,
                document_version_id,
                CHUNKER_NAME,
                CHUNKER_VERSION,
                chunk["chunk_index"],
                chunk["text"],
                chunk["text_sha256"],
                chunk["token_estimate"],
                chunk["page_start"],
                chunk["page_end"],
                chunk["element_start_id"],
                chunk["element_end_id"],
                chunk["preceding_heading_element_id"],
                chunk["char_start"],
                chunk["char_end"],
                nlp_run_id,
                now,
            ),
        )
    conn.execute(
        "UPDATE document_chunks SET superseded=1 WHERE document_version_id=%s AND chunker_version<>%s",
        (document_version_id, CHUNKER_VERSION),
    )
    return len(chunks)


def _active_versions_page(conn, source_system: str | None, *, after: str | None,
                          page_size: int) -> list:
    sql = (
        "SELECT v.document_version_id,v.text_sha256 FROM document_versions v "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE v.is_active = 1"
    )
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    if after is not None:
        sql += " AND v.document_version_id > %s"
        params.append(after)
    sql += " ORDER BY v.document_version_id"
    sql += " LIMIT %s"
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
    """Chunk every active document version (optionally filtered by source
    system). Bounded by `limit`; safe to repeat."""
    config = {
        "chunker_name": CHUNKER_NAME,
        "chunker_version": CHUNKER_VERSION,
        "target_tokens": TARGET_TOKENS,
        "max_tokens": MAX_TOKENS,
        "source_system": source_system,
        "limit": limit,
    }
    run_id = runs.start_run(
        conn,
        "chunk",
        config=config,
        chunker_version=CHUNKER_VERSION,
        input_scope={"source_system": source_system, "limit": limit},
    )
    state_config = {"target_tokens": TARGET_TOKENS, "max_tokens": MAX_TOKENS}
    written = 0
    processed = 0
    scanned = 0
    skipped = 0
    after_key = None
    batch_ordinal = 0
    try:
        while limit is None or scanned < limit:
            size = min(max(1, batch_size), limit - scanned) if limit is not None else max(1, batch_size)
            page = _active_versions_page(
                conn, source_system, after=after_key, page_size=size)
            if not page:
                break
            after_key = page[-1]["document_version_id"]
            scanned += len(page)
            pending = stage_state.pending_identities(
                conn, "chunking",
                [(row["document_version_id"], row["text_sha256"] or "", None) for row in page],
                processor_version=f"{CHUNKER_NAME}:{CHUNKER_VERSION}",
                configuration=state_config, force=force)
            skipped += len(page) - len(pending)
            for version in page:
                version_id = version["document_version_id"]
                if version_id not in pending:
                    continue
                before = conn.execute(
                    "SELECT document_chunk_id FROM document_chunks WHERE document_version_id=%s "
                    "AND superseded=0 ORDER BY document_chunk_id", (version_id,)).fetchall()
                try:
                    with conn.raw.transaction():
                        count = chunk_version(conn, version_id, run_id)
                        current = conn.execute(
                            "SELECT document_chunk_id,text_sha256 FROM document_chunks "
                            "WHERE document_version_id=%s AND superseded=0 ORDER BY document_chunk_id",
                            (version_id,)).fetchall()
                        stage_state.invalidate_downstream(
                            conn, "chunking", version_id,
                            [row["document_chunk_id"] for row in before]
                            + [row["document_chunk_id"] for row in current])
                        stage_state.mark_complete(
                            conn, "chunking", version_id, version["text_sha256"] or "",
                            processor_version=f"{CHUNKER_NAME}:{CHUNKER_VERSION}",
                            configuration=state_config,
                            output=[(row["document_chunk_id"], row["text_sha256"])
                                    for row in current], run_id=run_id)
                        written += count
                        processed += 1
                except Exception as input_exc:
                    stage_state.mark_failed(
                        conn, "chunking", version_id, version["text_sha256"] or "",
                        processor_version=f"{CHUNKER_NAME}:{CHUNKER_VERSION}",
                        error=input_exc, run_id=run_id, configuration=state_config)
                    raise
            if not dry_run:
                stage_state.checkpoint(
                    conn, run_id=run_id, stage="chunking", batch_ordinal=batch_ordinal,
                    last_input_identity=after_key, rows_processed=scanned, rows_written=written)
                conn.commit()
            batch_ordinal += 1
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
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
        "versions": processed,
        "chunks": written,
        "skipped_unchanged": skipped,
        "dry_run": dry_run,
    }
