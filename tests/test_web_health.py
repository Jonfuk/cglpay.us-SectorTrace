"""Coverage, freshness and the parse-failure list.

The assertion that matters most here is about a denominator. England has 347
local authorities in this warehouse and 159 of them are responsible for public
health; the other 188 are non-metropolitan districts with no treatment role.
A coverage figure computed against 347 is arithmetically correct and says
something false, and it is exactly the sort of number that gets quoted. So the
tier is the default, the denominator is returned alongside every count, and
both are pinned by tests.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.web import health, queries
from pipeline.web.server import build_server


@pytest.fixture
def geography(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Four authorities: three responsible for public health, one district."""
    rows = [
        ("E08000025", "Birmingham", "metropolitan_district", "West Midlands"),
        ("E10000028", "Staffordshire", "county", "West Midlands"),
        ("E06000019", "Herefordshire", "unitary", "West Midlands"),
        # No public health role. Its presence in a coverage denominator is the
        # bug this fixture exists to catch.
        ("E07000192", "Cannock Chase", "non_metropolitan_district", "West Midlands"),
    ]
    for ons_code, name, kind, region in rows:
        conn.execute(
            "INSERT INTO authorities (ons_code, name, type, region, active_from, "
            " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (?, ?, ?, ?, '2021-04-01', '2024', '2026', "
            " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
            (ons_code, name, kind, region))
    conn.commit()
    return conn


@pytest.fixture
def client(geography, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=30.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def grant(conn, ons_code, year="2025-26"):
    conn.execute(
        "INSERT INTO public_health_grants (ons_code, financial_year, grant_type, "
        " allocation_status, amount, unit, source_column_header, source_document, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'public_health_grant', 'final', 1000000, 'gbp', "
        " '2025-26 allocation', 'allocations.xlsx', "
        " 'https://gov.example/g', '2026-08-01T00:00:00Z', 200, 'dhsc', 'y')",
        (ons_code, year))


# --- the denominator ------------------------------------------------------------


def test_coverage_counts_only_the_authorities_that_could_have_the_evidence(
        geography, settings):
    """Three of the four fixture authorities are responsible for public health.
    A district appearing in the denominator would report 2 of 4 where the
    truth is 2 of 3."""
    ro = queries.readonly_connection(settings)
    try:
        result = health.coverage(ro, tier="upper")
    finally:
        ro.close()

    assert result["authority_count"] == 3
    assert {a["name"] for a in result["authorities"]} == {
        "Birmingham", "Staffordshire", "Herefordshire"}
    assert "Cannock Chase" not in {a["name"] for a in result["authorities"]}


def test_coverage_for_all_tiers_is_available_but_not_the_default(geography, settings):
    """Contracts and CQC locations legitimately attach to districts, so the
    wider view exists -- it is just not what "coverage" means unqualified."""
    ro = queries.readonly_connection(settings)
    try:
        assert health.coverage(ro, tier="all")["authority_count"] == 4
        assert health.coverage(ro)["tier"] == "upper"
        with pytest.raises(queries.QueryError):
            health.coverage(ro, tier="everything")
    finally:
        ro.close()


def test_coverage_reports_which_authorities_have_what(geography, settings):
    grant(geography, "E08000025")
    grant(geography, "E10000028")
    geography.commit()

    ro = queries.readonly_connection(settings)
    try:
        result = health.coverage(ro)
    finally:
        ro.close()

    cells = {a["name"]: a["cells"] for a in result["authorities"]}
    assert cells["Birmingham"]["Grant"] == 1
    assert cells["Staffordshire"]["Grant"] == 1
    assert "Grant" not in cells["Herefordshire"], "a gap is an absent cell, not a zero"

    column = next(c for c in result["columns"] if c["label"] == "Grant")
    assert column["covered"] == 2
    assert column["total_rows"] == 2
    assert column["module"] == "m11_public_health_grant"


def test_evidence_for_an_authority_outside_the_tier_is_counted_but_not_covered(
        geography, settings):
    """A district with a contract is real evidence and belongs in the row
    total. It is not coverage of a public health authority."""
    grant(geography, "E07000192")   # the district
    grant(geography, "E08000025")
    geography.commit()

    ro = queries.readonly_connection(settings)
    try:
        result = health.coverage(ro, tier="upper")
    finally:
        ro.close()

    column = next(c for c in result["columns"] if c["label"] == "Grant")
    assert column["total_rows"] == 2, "both rows exist"
    assert column["covered"] == 1, "only one of them is an authority of this tier"


def test_candidate_tables_are_shown_beside_confirmed_ones(geography, settings):
    """m09 and m10 hold hundreds of candidates and zero confirmed documents.
    Folding them together would report the pipeline as more finished than it
    is."""
    ro = queries.readonly_connection(settings)
    try:
        labels = [c["label"] for c in health.coverage(ro)["columns"]]
    finally:
        ro.close()

    assert "CDP docs" in labels and "CDP cands" in labels
    assert "Papers" in labels and "Paper cands" in labels


def test_council_spend_coverage_uses_the_file_record(geography, settings):
    """Finding a file is coverage even when its rows cannot be parsed.

    m24 records that distinction in council_spend_files.parse_status. Basing
    the matrix on line items would make an unreadable publication look like a
    council the crawler never reached.
    """
    geography.execute(
        "INSERT INTO council_spend_files "
        "(authority_ons_code, file_url, file_format, parse_status, row_count, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E08000025', 'https://example.test/spend.csv', 'csv', "
        "        'unreadable', NULL, 'https://example.test/spend.csv', "
        "        '2026-08-17T00:00:00Z', 200, 'council_spend', 'abc')")
    geography.commit()

    result = health.coverage(geography)
    column = next(c for c in result["columns"] if c["label"] == "Spend files")
    birmingham = next(a for a in result["authorities"]
                      if a["ons_code"] == "E08000025")

    assert column["module"] == "m24_council_spend"
    assert column["covered"] == 1
    assert birmingham["cells"]["Spend files"] == 1


def test_coverage_survives_a_table_that_is_not_there_yet(geography, settings, monkeypatch):
    monkeypatch.setattr(health, "COVERAGE_COLUMNS",
                         (("Imaginary", "not_a_table", "ons_code", "m99"),))
    ro = queries.readonly_connection(settings)
    try:
        column = health.coverage(ro)["columns"][0]
    finally:
        ro.close()
    assert column["missing"] is True
    assert column["covered"] == 0


# --- warehouse state --------------------------------------------------------------


def test_warehouse_reports_size_and_the_migrations_that_built_it(client, settings):
    payload = client.get("/api/admin/health").json()["warehouse"]

    assert payload["bytes"] > 0
    assert payload["applied_migrations"], "migrations were applied by the fixture"
    assert payload["unapplied"] == []
    assert payload["applied_without_file"] == []
    assert payload["migrations_on_disk"] == sorted(payload["migrations_on_disk"])


def test_an_unapplied_migration_is_visible(client, conn, settings):
    """The failure this catches is a warehouse one schema behind the checkout,
    which shows up as a module failing on a missing column mid-run."""
    conn.execute("DELETE FROM schema_migrations WHERE filename = "
                  "(SELECT MAX(filename) FROM schema_migrations)")
    conn.commit()

    payload = client.get("/api/admin/health").json()["warehouse"]
    assert len(payload["unapplied"]) == 1


# --- storage ----------------------------------------------------------------------
#
# W-21: the cards reported the warehouse's own size and nothing else, while the
# raw archive beside it is 3.5 GiB. The archive is the audit trail, so the
# answer to its growth is to watch it — and the only instrument was a one-off
# measurement in the roadmap.


def _fill(directory, files: dict[str, bytes]):
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_the_storage_card_equals_a_direct_listing_of_the_directories(
        client, settings):
    """The whole value of the card is that the number is right. Computed here
    the other way round — walk the directories and add them up."""
    _fill(settings.raw_archive_dir, {"m01/a.json": b"x" * 100,
                                      "m01/b.json": b"y" * 250})
    _fill(settings.backup_dir, {"warehouse-2026.db": b"z" * 4096})
    _fill(settings.export_output_dir, {"sheets/01.csv": b"a,b\n"})

    rows = {row["key"]: row for row in
             client.get("/api/admin/storage").json()["storage"]}

    for key, attribute in (("raw_archive", "raw_archive_dir"),
                            ("backups", "backup_dir"),
                            ("exports", "export_output_dir"),
                            ("logs", "logs_dir")):
        directory = Path(getattr(settings, attribute))
        on_disk = [p for p in directory.rglob("*") if p.is_file()]
        assert rows[key]["files"] == len(on_disk), key
        assert rows[key]["bytes"] == sum(p.stat().st_size for p in on_disk), key
        assert rows[key]["path"] == str(directory)


def test_a_directory_that_does_not_exist_yet_reports_zero_rather_than_failing(
        client, settings):
    """A fresh checkout has none of these. The card is where an operator finds
    out that nothing has been collected, so it has to render."""
    rows = {row["key"]: row for row in
             client.get("/api/admin/storage").json()["storage"]}

    assert rows["backups"]["exists"] is False
    assert rows["backups"]["bytes"] == 0
    assert rows["backups"]["files"] == 0


def test_the_storage_card_names_the_archive_as_the_thing_not_to_delete(client):
    """P-02's conclusion travels with the number: the archive is the audit
    trail, so the answer to its growth is measurement, not deletion."""
    rows = {row["key"]: row for row in
             client.get("/api/admin/storage").json()["storage"]}
    assert "audit trail" in rows["raw_archive"]["note"]


def test_storage_is_its_own_route_and_not_in_the_cheap_half(client):
    """Six seconds of stat calls over 8,502 archived files, measured against
    the real archive. The Health tab's cards must not wait for it — the same
    call `freshness` already forced."""
    assert "storage" not in client.get("/api/admin/health").json()
    assert client.get("/api/admin/storage").json()["storage"]


def test_freshness_reads_the_rows_not_the_cursor(client, geography):
    """A module that ran this morning and fetched nothing leaves a fresh
    cursor and stale evidence. The rows know when they were retrieved."""
    payload = client.get("/api/admin/freshness").json()["freshness"]
    authorities = next(row for row in payload if row["table"] == "authorities")

    assert authorities["rows"] == 4
    assert authorities["newest"] == "2026-08-01T00:00:00Z"


def test_freshness_does_not_read_personal_data_tables(client, conn):
    conn.execute("CREATE TABLE restricted_people "
                  "(id INTEGER PRIMARY KEY, retrieved_at TEXT)")
    conn.execute("INSERT INTO restricted_people (retrieved_at) VALUES ('2026-01-01')")
    conn.commit()

    tables = {row["table"] for row in client.get("/api/admin/freshness").json()["freshness"]}
    assert "restricted_people" not in tables


def test_hosts_report_when_each_source_was_last_asked(client, conn):
    for url, host, when in [
        ("https://a.example/1", "a.example", "2026-08-01T00:00:00Z"),
        ("https://a.example/2", "a.example", "2026-08-05T00:00:00Z"),
        ("https://b.example/1", "b.example", "2026-07-01T00:00:00Z"),
    ]:
        conn.execute(
            "INSERT INTO http_cache (url, host, updated_at) VALUES (?, ?, ?)",
            (url, host, when))
    conn.commit()

    hosts = {row["host"]: row for row in client.get("/api/admin/health").json()["hosts"]}
    assert hosts["a.example"]["urls"] == 2
    assert hosts["a.example"]["newest"] == "2026-08-05T00:00:00Z"
    assert hosts["a.example"]["oldest"] == "2026-08-01T00:00:00Z"


# --- evidence graph status ---------------------------------------------------------
#
# docs/evidence-graph.md documents a whole subsystem (migration 0050) that had
# no answer anywhere in the UI to "has this ever run, and how stale is it" --
# a CLI-only `pipeline graph status` was the only way to know.


def _run(conn, run_id, started_at, *, completed_at=None, status="completed",
          entity_count=0, relationship_count=0, claim_count=0, error_detail=None):
    conn.execute(
        "INSERT INTO graph_projection_runs (run_id, started_at, completed_at, "
        " status, schema_version, projector_version, entity_count, "
        " relationship_count, claim_count, error_detail) "
        "VALUES (?, ?, ?, ?, '0050', '1', ?, ?, ?, ?)",
        (run_id, started_at, completed_at, status, entity_count,
         relationship_count, claim_count, error_detail))


def test_graph_status_reports_never_run_when_nothing_has_projected(client):
    payload = client.get("/api/admin/health").json()["graph"]
    assert payload == {"last_run": None, "pending_queue": 0}


def test_graph_status_reports_the_most_recent_run(conn, client):
    _run(conn, "run-1", "2026-08-01T00:00:00Z", completed_at="2026-08-01T00:05:00Z",
         entity_count=10)
    _run(conn, "run-2", "2026-08-10T00:00:00Z", completed_at="2026-08-10T00:05:00Z",
         entity_count=25, relationship_count=40, claim_count=3)
    conn.commit()

    last_run = client.get("/api/admin/health").json()["graph"]["last_run"]
    assert last_run["run_id"] == "run-2", "the newer run, not insertion order"
    assert last_run["entity_count"] == 25


def test_graph_status_surfaces_a_failed_run(conn, client):
    _run(conn, "run-1", "2026-08-01T00:00:00Z", completed_at="2026-08-01T00:05:00Z",
         status="failed", error_detail="Neo4j connection refused")
    conn.commit()

    last_run = client.get("/api/admin/health").json()["graph"]["last_run"]
    assert last_run["status"] == "failed"
    assert last_run["error_detail"] == "Neo4j connection refused"


def test_graph_status_counts_only_unprocessed_queue_items(conn, client):
    conn.execute(
        "INSERT INTO graph_projection_queue "
        "(object_type, object_id, operation, created_at, processed_at) "
        "VALUES ('entity', 'e1', 'UPSERT_ENTITY', '2026-08-01T00:00:00Z', NULL)")
    conn.execute(
        "INSERT INTO graph_projection_queue "
        "(object_type, object_id, operation, created_at, processed_at) "
        "VALUES ('entity', 'e2', 'UPSERT_ENTITY', '2026-08-01T00:00:00Z', NULL)")
    conn.execute(
        "INSERT INTO graph_projection_queue "
        "(object_type, object_id, operation, created_at, processed_at) "
        "VALUES ('entity', 'e3', 'UPSERT_ENTITY', '2026-08-01T00:00:00Z', "
        "'2026-08-01T00:01:00Z')")
    conn.commit()

    assert client.get("/api/admin/health").json()["graph"]["pending_queue"] == 2


def test_graph_status_survives_a_warehouse_that_predates_the_graph_tables(
        conn, settings):
    conn.execute("DROP TABLE graph_projection_runs")
    conn.execute("DROP TABLE graph_projection_queue")
    conn.commit()

    ro = queries.readonly_connection(settings)
    try:
        assert health.graph_status(ro) == {"last_run": None, "pending_queue": 0}
    finally:
        ro.close()


def test_graph_status_is_in_the_cheap_half_not_a_separate_route(client):
    """Unlike storage/freshness, one indexed row and one count is cheap enough
    to belong in /api/admin/health directly."""
    assert "graph" in client.get("/api/admin/health").json()


# --- document-analysis status -------------------------------------------------
#
# docs/document-analysis.md documents a whole subsystem (migration 0053:
# inspection, OCR, parsing, classification, quality) that had no answer
# anywhere in the UI to "how much has been processed" -- a CLI-only
# `pipeline documents stats` was the only way to know, the same gap
# graph_status closed for the evidence graph.


def _evidence(conn, evidence_id, *, source_system="m09_cdp_documents"):
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, payload_sha256, created_at) "
        "VALUES (?, ?, 'https://example.test/doc.pdf', '2026-08-01T00:00:00Z', "
        " ?, '2026-08-01T00:00:00Z')",
        (evidence_id, source_system, f"hash-{evidence_id}"))


def _document(conn, document_id, evidence_id):
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, document_type, "
        " created_at, updated_at) "
        "VALUES (?, ?, 'UNKNOWN', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')",
        (document_id, evidence_id))


def _processing_state(conn, evidence_id, parse_status):
    conn.execute(
        "INSERT INTO document_processing_states (evidence_id, parse_status) "
        "VALUES (?, ?)", (evidence_id, parse_status))


def test_document_status_reports_nothing_registered_when_empty(client):
    payload = client.get("/api/admin/health").json()["documents"]
    assert payload == {"registered": 0, "parsed": 0, "failed": 0, "documents": 0}


def test_document_status_counts_by_parse_outcome(conn, client):
    for i, status in enumerate(["SUCCESS", "SUCCESS", "FAILED", "PENDING"]):
        evidence_id, document_id = f"evidence:{i}", f"document:{i}"
        _evidence(conn, evidence_id)
        _document(conn, document_id, evidence_id)
        _processing_state(conn, evidence_id, status)
    conn.commit()

    payload = client.get("/api/admin/health").json()["documents"]
    assert payload["registered"] == 4
    assert payload["parsed"] == 2
    assert payload["failed"] == 1
    assert payload["documents"] == 4


def test_document_status_survives_a_warehouse_that_predates_document_analysis(
        conn, settings):
    for table in ("document_processing_states", "document_topics",
                  "document_parse_runs", "document_versions",
                  "derived_artifacts", "document_records"):
        conn.execute(f"DROP TABLE {table}")
    conn.commit()

    ro = queries.readonly_connection(settings)
    try:
        assert health.document_status(ro) == {
            "registered": 0, "parsed": 0, "failed": 0, "documents": 0}
    finally:
        ro.close()


# --- parse failures ----------------------------------------------------------------


@pytest.fixture
def some_failures(conn):
    from pipeline import db

    # Distinct fragments, because record_parse_failure deduplicates on its
    # natural key: the same parser tripping over the same text twice is one
    # bug seen twice, and the table says so.
    for fragment in ("£not-a-number", "£also-bad", "£nope", "£---"):
        db.record_parse_failure(conn, "m03_charity_finance", "wages", fragment,
                                 "could not parse currency amount")
    db.record_parse_failure(conn, "m11_public_health_grant", "allocation", "n/a",
                             "empty cell")
    conn.commit()
    return conn


def test_the_same_failure_recorded_twice_stays_one_row(conn):
    """Relied on by the grouping above, and by the run summary's deltas."""
    from pipeline import db

    for _ in range(3):
        db.record_parse_failure(conn, "m03_charity_finance", "wages", "£x", "bad")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM parse_failures").fetchone()[0] == 1


def test_failures_group_by_the_thing_that_makes_them_one_bug(client, some_failures):
    """Four failures from one broken currency parser are one problem."""
    payload = client.get("/api/admin/failures").json()

    groups = {(g["module"], g["reason"]): g for g in payload["groups"]}
    currency = groups[("m03_charity_finance", "could not parse currency amount")]
    assert currency["n"] == 4
    assert currency["field_name"] == "wages"
    assert len(payload["groups"]) == 2, "two distinct problems, not five failures"


def test_failures_carry_the_fragment_a_parser_author_needs(client, some_failures):
    rows = client.get("/api/admin/failures").json()["rows"]
    assert any(row["raw_fragment"] == "£also-bad" for row in rows)


def test_failures_filter_by_module_and_search(client, some_failures):
    assert client.get("/api/admin/failures?module=m11_public_health_grant"
                       ).json()["total"] == 1
    assert client.get("/api/admin/failures?q=currency").json()["total"] == 4
    assert client.get("/api/admin/failures?q=also-bad").json()["total"] == 1


def test_a_search_term_is_literal_text_not_a_pattern(client, some_failures):
    """Someone searching for `%` means that character."""
    assert client.get("/api/admin/failures?q=%25").json()["total"] == 0


def test_failures_list_the_modules_that_have_them(client, some_failures):
    modules = client.get("/api/admin/failures").json()["modules"]
    assert modules[0] == "m03_charity_finance", "most failures first"
    assert set(modules) == {"m03_charity_finance", "m11_public_health_grant"}


def test_failures_page(client, some_failures):
    page = client.get("/api/admin/failures?limit=2").json()
    assert len(page["rows"]) == 2
    assert page["total"] == 5
    assert len(client.get("/api/admin/failures?limit=2&offset=4").json()["rows"]) == 1


# --- integrity ----------------------------------------------------------------------


def test_the_integrity_check_runs_as_a_job_and_passes_on_a_good_warehouse(client):
    import time

    started = client.post("/api/admin/check", json={})
    assert started.status_code == 200
    job_id = started.json()["id"]

    deadline = time.time() + 30
    while time.time() < deadline:
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.02)

    assert job["state"] == "finished"
    assert job["summary"][0]["ok"] is True
    assert job["summary"][0]["integrity"] == ["ok"]


def test_the_integrity_check_takes_the_same_slot_as_a_run(client, monkeypatch):
    """Both want the whole warehouse. Checking one that is being written would
    report on a moving target."""
    from pipeline.registry import MODULE_REGISTRY

    release = threading.Event()
    monkeypatch.setitem(MODULE_REGISTRY, "a_slow", lambda ctx: release.wait(timeout=10))

    client.post("/api/admin/run", json={"module": "a_slow"})
    try:
        refused = client.post("/api/admin/check", json={})
        assert refused.status_code == 409
    finally:
        release.set()


def test_the_integrity_check_reads_without_writing(client, settings):
    """A corruption check that could write is not a check."""
    import inspect

    source = inspect.getsource(health.integrity_check)
    assert "readonly_connection" in source
