"""`observe_many`: the same bitemporal accounting as `observe()`, batched.

Equivalence matters more than speed here — see the `observe_many` docstring
in `pipeline/evidence_state.py` and CLAUDE.md's insistence that a wrong
figure in this pipeline is the exact failure it exists to prevent. The first
test below runs one literal batch of observations through `observe()` called
once per entry, and through `observe_many()` in a single call, against two
independently migrated PostgreSQL schemas that start from the same seeded
state — then diffs the resulting `evidence_temporal_state` and
`evidence_change_events` rows, not just the return values.
"""
from __future__ import annotations

import hashlib

import pytest
from conftest import scratch_schema
from test_postgres_live import POSTGRES_TEST_URL

from pipeline import evidence_state
from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement, ParsedTable

LIVE_POSTGRES = bool(POSTGRES_TEST_URL)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _batch() -> list[dict]:
    """8 entries spanning every classification `classify_change` makes.

    A plain list of literal dicts (not built from any DB state) so the exact
    same batch can be replayed, unmodified, against two schemas that were
    seeded identically by `_seed_prior`.
    """
    return [
        dict(identity="elem-new-1", evidence_hash=_hash("new one"),
             source_url="https://example.test/a", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-new-2", evidence_hash=_hash("new two"),
             source_url="https://example.test/b", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-unchanged", evidence_hash=_hash("stable text"),
             source_url="https://example.test/c", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-modified", evidence_hash=_hash("changed text"),
             source_url="https://example.test/d", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-redirected", evidence_hash=_hash("same bytes"),
             source_url="https://example.test/d2-new", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-reappeared", evidence_hash=_hash("came back"),
             source_url="https://example.test/e", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
        dict(identity="elem-explicit-removed", evidence_hash=_hash("gone bytes"),
             source_url="https://example.test/f", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00", explicit_state="removed"),
        dict(identity="elem-unchanged-2", evidence_hash=_hash("also stable"),
             source_url="https://example.test/g", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00"),
    ]


def _seed_prior(conn) -> None:
    """The state each batch entry in `_batch()` observes *against*.

    Run identically against both schemas before the batch under test, so the
    two runs start from byte-identical prior state.
    """
    evidence_state.observe(conn, layer="element", identity="elem-unchanged",
                            evidence_hash=_hash("stable text"), source_url="https://example.test/c",
                            observed_at="2026-08-01T00:00:00+00:00")
    evidence_state.observe(conn, layer="element", identity="elem-modified",
                            evidence_hash=_hash("original text"), source_url="https://example.test/d",
                            observed_at="2026-08-01T00:00:00+00:00")
    evidence_state.observe(conn, layer="element", identity="elem-redirected",
                            evidence_hash=_hash("same bytes"), source_url="https://example.test/d2-old",
                            observed_at="2026-08-01T00:00:00+00:00")
    # Seeded, then explicitly removed: the batch observes the very same bytes
    # again, which `classify_change` must call "new" rather than "unchanged"
    # (a current `removed` row describes the last observation, not the fact).
    evidence_state.observe(conn, layer="element", identity="elem-reappeared",
                            evidence_hash=_hash("came back"), source_url="https://example.test/e",
                            observed_at="2026-07-01T00:00:00+00:00")
    evidence_state.observe(conn, layer="element", identity="elem-reappeared",
                            evidence_hash=_hash("came back"), source_url="https://example.test/e",
                            observed_at="2026-07-15T00:00:00+00:00", explicit_state="removed")
    evidence_state.observe(conn, layer="element", identity="elem-explicit-removed",
                            evidence_hash=_hash("still here"), source_url="https://example.test/f",
                            observed_at="2026-08-01T00:00:00+00:00")
    evidence_state.observe(conn, layer="element", identity="elem-unchanged-2",
                            evidence_hash=_hash("also stable"), source_url="https://example.test/g",
                            observed_at="2026-08-01T00:00:00+00:00")
    conn.commit()


def _rows(conn, table: str, *, exclude: frozenset[str] = frozenset()) -> list[dict]:
    """All rows of `table` as plain dicts, columns sorted and `exclude`d ones
    dropped, ordered by primary key so two independently built schemas
    compare in the same order."""
    columns = [
        row["column_name"] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "ORDER BY ordinal_position", (table,)).fetchall()
        if row["column_name"] not in exclude
    ]
    pk = "temporal_state_id" if table == "evidence_temporal_state" else "change_event_id"
    select = ", ".join(columns)
    return [dict(row) for row in conn.execute(f"SELECT {select} FROM {table} ORDER BY {pk}").fetchall()]


@pytest.mark.skipif(not LIVE_POSTGRES, reason="POSTGRES_TEST_URL is not set")
def test_observe_many_matches_observe_called_once_per_entry():
    with scratch_schema(POSTGRES_TEST_URL) as sequential, scratch_schema(POSTGRES_TEST_URL) as batched:
        _seed_prior(sequential.conn)
        _seed_prior(batched.conn)

        batch = _batch()
        sequential_results = [
            evidence_state.observe(sequential.conn, layer="element", **entry) for entry in batch]
        sequential.conn.commit()

        batched_results = evidence_state.observe_many(batched.conn, layer="element", entries=batch)
        batched.conn.commit()

        assert [r["change_state"] for r in sequential_results] == [
            "new", "new", "unchanged", "modified", "redirected", "new", "removed", "unchanged"]
        # The return values agree entry-for-entry...
        assert batched_results == sequential_results
        # ...and so does everything actually written. created_at is wall-clock
        # and outside the contract; state_id, change_state, is_current and the
        # supersedes_id chain are not, and every one of them must match.
        assert _rows(sequential.conn, "evidence_temporal_state", exclude={"created_at"}) == \
            _rows(batched.conn, "evidence_temporal_state", exclude={"created_at"})
        assert _rows(sequential.conn, "evidence_change_events") == \
            _rows(batched.conn, "evidence_change_events")


def test_observe_many_issues_a_bounded_number_of_statements_regardless_of_batch_size(conn):
    """200 entries must not mean 200 round trips.

    `observe()` issues a SELECT plus at least one write per call — O(N) for
    N entries. `observe_many` is meant to issue a small, fixed number of
    statements no matter how large the batch is; this seeds half the
    identities so the batch under test exercises every branch (the bulk
    SELECT, the batched supersede UPDATE, the batched state INSERT and the
    always-on change-event INSERT) and still stays bounded.
    """
    seeded = [
        dict(identity=f"bulk-{i}", evidence_hash=_hash(f"seed-{i}"),
             source_url="https://example.test/bulk", retrieved_at="2026-09-01T00:00:00+00:00",
             observed_at="2026-09-01T00:00:00+00:00")
        for i in range(50)
    ]
    evidence_state.observe_many(conn, layer="bulk", entries=seeded)
    conn.commit()

    calls: list[str] = []
    original_execute, original_executemany = conn.execute, conn.executemany
    conn.execute = lambda sql, params=(): (calls.append("execute"), original_execute(sql, params))[1]
    conn.executemany = lambda sql, params: (calls.append("executemany"), original_executemany(sql, params))[1]
    try:
        entries = (
            # 50 modified (exercises the batched supersede UPDATE)...
            [dict(identity=f"bulk-{i}", evidence_hash=_hash(f"changed-{i}"),
                  source_url="https://example.test/bulk", retrieved_at="2026-09-01T00:00:00+00:00",
                  observed_at="2026-09-02T00:00:00+00:00") for i in range(50)]
            # ...and 150 brand new, for 200 entries total.
            + [dict(identity=f"bulk-new-{i}", evidence_hash=_hash(f"new-{i}"),
                    source_url="https://example.test/bulk", retrieved_at="2026-09-01T00:00:00+00:00",
                    observed_at="2026-09-01T00:00:00+00:00") for i in range(150)]
        )
        results = evidence_state.observe_many(conn, layer="bulk", entries=entries)
    finally:
        conn.execute, conn.executemany = original_execute, original_executemany

    assert len(results) == 200
    assert len(calls) <= 5, f"expected a handful of statements for 200 entries, got {calls}"


def _document_reference() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evidence-observe-many", source_system="fixture",
        source_url="https://example.test/report", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256="c" * 64,
        raw_object_path="data/raw/fixture/" + "c" * 64 + ".pdf", mime_type="application/pdf")


def test_persist_parse_writes_correct_evidence_state_through_observe_many(conn, settings):
    """`persist_parse` now drives `observe_many`, not `observe`, per element
    and table. This pins the same element/table lifecycle (new, then a
    reparse that leaves one unchanged, modifies one, and drops two) that
    `test_documents.py` already exercises for `observe()`, so a regression in
    the batched path shows up here rather than only in the unit-level
    equivalence test above."""
    source = _document_reference()
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "report.pdf", "application/pdf", 1, "Report")

    first = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Recruitment is increasing.", page_number=1),
        ParsedElement("PARAGRAPH", 3, text="Budget pressure continues.", page_number=1),
        ParsedElement("TABLE", 4, text="Year | Value\n2025 | 1", page_number=1),
    ], tables=[ParsedTable(element_sequence=4, rows=[["Year", "Value"], ["2025", "1"]],
                           markdown="Year | Value\n2025 | 1")])
    repository.persist_parse(conn, document_id, first, "config", None, "GOOD", {}, [], settings)

    element_rows = conn.execute(
        "SELECT state, is_current FROM evidence_temporal_state WHERE layer='document_element' "
        "ORDER BY provenance_json->>'sequence'").fetchall()
    assert [(r["state"], r["is_current"]) for r in element_rows] == [
        ("new", True), ("new", True), ("new", True), ("new", True)]
    table_rows = conn.execute(
        "SELECT state, is_current FROM evidence_temporal_state WHERE layer='document_table'").fetchall()
    assert [(r["state"], r["is_current"]) for r in table_rows] == [("new", True)]
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM evidence_change_events WHERE layer='document_element'"
    ).fetchone()["n"] == 4
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM evidence_change_events WHERE layer='document_table'"
    ).fetchone()["n"] == 1

    # A later retrieved_at, as a genuine refetch would produce -- the removed
    # elements below carry their old hash forward unchanged (persist_parse's
    # "absent, not proof the fact ended" convention), and reusing the exact
    # retrieved_at of their creation would make their state_id collide with
    # the row `_id()` already gave that (layer, identity, hash, url,
    # observed) tuple, an existing property of `_id`/`observe()` this test is
    # not exercising.
    repository.upsert_evidence(conn, EvidenceReference(
        evidence_id=source.evidence_id, source_system=source.source_system,
        source_url=source.source_url, retrieved_at="2026-08-20T00:00:00+00:00",
        http_status=200, payload_sha256=source.payload_sha256,
        raw_object_path=source.raw_object_path, mime_type=source.mime_type))

    # Reparse under a new parser config, so this is a fresh document_version
    # (leaving the first version's elements, and the document_topics rows
    # that reference them, untouched -- persist_parse's DELETE is scoped to
    # the version being (re)written). Sequence 1 unchanged, 2 modified, 3 and
    # the table (via its element, 4) absent -> both classified "removed".
    second = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Recruitment has fallen.", page_number=1),
    ])
    repository.persist_parse(conn, document_id, second, "config-2", None, "GOOD", {}, [], settings)

    # The removed-elements branch doesn't carry "sequence" in provenance_json
    # (see repository.py's removed_element_entries) -- the identity string
    # itself ("...|<sequence>|<element_type>") is the reliable source.
    current_elements = conn.execute(
        "SELECT evidence_identity, state FROM evidence_temporal_state "
        "WHERE layer='document_element' AND is_current").fetchall()
    assert {(r["evidence_identity"].split("|")[-2], r["state"]) for r in current_elements} == {
        ("1", "new"), ("2", "modified"), ("3", "removed"), ("4", "removed")}
    current_table = conn.execute(
        "SELECT state FROM evidence_temporal_state WHERE layer='document_table' AND is_current").fetchall()
    assert [r["state"] for r in current_table] == ["removed"]

    assert conn.execute(
        "SELECT COUNT(*) AS n FROM evidence_change_events WHERE layer='document_element'"
    ).fetchone()["n"] == 8
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM evidence_change_events WHERE layer='document_table'"
    ).fetchone()["n"] == 2
