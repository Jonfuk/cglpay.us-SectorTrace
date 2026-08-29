"""Feature-level graceful degradation (BETA-068).

Live review of the populated beta found raw PostgreSQL tracebacks rendered
where a section should be, when a deployment was missing a migration or an
extension. These tests pin the replacement: a bounded, feature-specific
unavailable envelope that never carries internal SQL, with the plain `error`
string kept exactly as it was so the portal and the older tests still read it.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.web import degrade
from pipeline.web.server import build_server

# --- unit: preflight ------------------------------------------------------


def test_preflight_passes_on_a_fully_migrated_warehouse(conn: sqlite3.Connection) -> None:
    # The template warehouse has every migration; nothing should refuse.
    for feature in ("document_search", "run_ledger", "cqc_locations"):
        degrade.preflight(conn, feature)


def test_preflight_unknown_feature_is_a_noop(conn: sqlite3.Connection) -> None:
    degrade.preflight(conn, "not-a-real-feature")


def test_preflight_names_a_missing_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE run_ledger")
    conn.commit()
    with pytest.raises(degrade.FeatureUnavailable) as caught:
        degrade.preflight(conn, "run_ledger")
    exc = caught.value
    assert exc.feature == "run_ledger"
    assert exc.code == "missing_table"
    assert exc.retryable is False
    assert "run_ledger" in str(exc)


def test_preflight_names_a_missing_migration(conn: sqlite3.Connection, monkeypatch) -> None:
    # A build stuck at revision 0040: document search wants 0041.
    monkeypatch.setattr(
        degrade.db, "applied_migrations",
        lambda _c: {f"{n:04d}_x.sql" for n in range(1, 41)},
    )
    with pytest.raises(degrade.FeatureUnavailable) as caught:
        degrade.preflight(conn, "document_search")
    assert caught.value.code == "missing_migration"
    assert "0053" in str(caught.value) and "0040" in str(caught.value)


def test_max_applied_migration_reads_the_numeric_prefix() -> None:
    assert degrade.max_applied_migration(set()) == 0
    assert degrade.max_applied_migration(
        {"0001_a.sql", "0077_temporary_accommodation_breakdowns.sql", "0009_b.sql"}
    ) == 77


# --- unit: classify_db_error --------------------------------------------


def test_classify_recognises_a_missing_sqlite_table() -> None:
    exc = sqlite3.OperationalError("no such table: run_ledger")
    out = degrade.classify_db_error(exc, feature="run_ledger")
    assert out is not None
    assert out.code == "missing_table"
    assert out.feature == "run_ledger"
    assert "run_ledger" not in out.message  # no raw object name to the reader


def test_classify_recognises_an_interrupted_query_as_a_retryable_timeout() -> None:
    out = degrade.classify_db_error(sqlite3.OperationalError("interrupted"))
    assert out is not None
    assert out.code == "timeout"
    assert out.retryable is True


def test_classify_leaves_an_unrelated_error_for_the_500_path() -> None:
    assert degrade.classify_db_error(ValueError("nope")) is None
    assert degrade.classify_db_error(
        sqlite3.OperationalError("database is locked")
    ) is None


# --- integration: the wire envelope ------------------------------------


@pytest.fixture
def client(conn: sqlite3.Connection, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=30.0
        ) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_ledger_without_its_table_degrades_by_feature(client, conn) -> None:
    conn.execute("DROP TABLE run_ledger")
    conn.commit()

    response = client.get("/api/admin/run-ledger")
    assert response.status_code == 503
    body = response.json()

    # Backward compatible: `error` is still a plain human string.
    assert isinstance(body["error"], str)
    assert "SQL" not in body["error"].upper() or "run_ledger" not in body["error"]

    detail = body["error_detail"]
    assert detail["code"] == "missing_table"
    assert detail["feature"] == "run_ledger"
    assert detail["retryable"] is False
    assert detail["ref"] and len(detail["ref"]) >= 6
    assert detail["build"]["environment"]
    assert detail["schema"]["available"] is True
    assert isinstance(detail["schema"]["latest_migration"], int)


def test_document_search_without_its_element_table_degrades(client, conn) -> None:
    conn.execute("DROP TABLE document_elements")
    conn.commit()

    response = client.get("/api/v1/document_search", params={"q": "grant"})
    assert response.status_code == 503
    detail = response.json()["error_detail"]
    assert detail["feature"] == "document_search"
    assert detail["code"] == "missing_table"


def test_a_healthy_build_still_answers_normally(client) -> None:
    assert client.get("/api/admin/run-ledger").status_code == 200
    assert client.get("/api/v1/document_search", params={"q": "x"}).status_code == 200


def test_an_ordinary_bad_request_keeps_the_flat_error_shape(client) -> None:
    # A validation refusal is not a degradation: no error_detail, `error` is
    # still the bare string older code and tests expect.
    response = client.get("/api/v1/contracts", params={"limit": "not-a-number"})
    assert response.status_code == 400
    body = response.json()
    assert isinstance(body["error"], str)
    assert "error_detail" not in body
