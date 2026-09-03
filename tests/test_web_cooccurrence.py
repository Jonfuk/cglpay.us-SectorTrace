"""Entity co-occurrence explorer (BETA-095).

Documents and records naming two or more selected tracked entities together,
with the exact passage or field. Verified name variants only, same-record
only. Co-occurrence is location, never an asserted relationship.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import cooccurrence
from pipeline.web.queries import QueryError

_NOW = "2026-08-01T00:00:00Z"


def _providers(conn):
    for key, name in [("cgl", "Change Grow Live"), ("tp", "Turning Point")]:
        conn.execute("INSERT INTO providers (provider_key, canonical_name, "
                     "is_target, notes) VALUES (%s, %s, 0, NULL)", (key, name))
        conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, "
                     "canonical_name) VALUES (%s, %s, %s)", (name, key, name))
    conn.commit()


def _document(conn, element_text):
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, mime_type, "
        " content_length, source_table, source_key, created_at) VALUES "
        "('ev1', 'committee_paper_promotion', 'https://x/1', %s, 200, 's1', "
        " 'r/x.pdf', 'application/pdf', 10, 'committee_papers', 'k1', %s)",
        (_NOW, _NOW))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, "
        " source_key, document_type, mime_type, title, created_at, updated_at) "
        "VALUES ('d1', 'ev1', 'committee_papers', 'k1', 'committee_paper', "
        " 'application/pdf', 'Board minutes', %s, %s)", (_NOW, _NOW))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, "
        " parser_name, parser_version, parse_schema_version, config_hash, "
        " text_sha256, status, is_active, created_at) VALUES "
        "('v1', 'd1', 'docling', '1.0.0', '1', 'c', 't', 'parsed', 1, %s)", (_NOW,))
    conn.execute(
        "INSERT INTO document_elements (document_element_id, "
        " document_version_id, element_type, sequence, text, text_sha256, "
        " metadata_json) VALUES ('e1', 'v1', 'para', 0, %s, 'h', '{}')",
        (element_text,))
    conn.commit()


def test_a_shared_coroner_report_is_a_co_occurrence(conn: sqlite3.Connection) -> None:
    _providers(conn)
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_date, coroner_area, "
        " report_url, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('2024-0001', '2024-05-01', 'Inner London', "
        " 'https://j/x', 'https://j/x', %s, 200, 'judiciary', 'h')", (_NOW,))
    for pk, name in [("cgl", "Change Grow Live"), ("tp", "Turning Point")]:
        conn.execute(
            "INSERT INTO pfd_provider_mentions (report_ref, provider_key, "
            " mention_type, matched_name) VALUES ('2024-0001', %s, 'body_text', %s)",
            (pk, name))
    conn.commit()

    out = cooccurrence.find(conn, ["cgl", "tp"])
    assert out["counts"]["by_record_type"] == {"coroner_report": 1}
    row = out["results"][0]
    assert row["record_type"] == "coroner_report"
    assert set(row["matched"]) == {"cgl", "tp"}
    assert "location, not a relationship" in out["note"].lower()


def test_documents_match_on_verified_variants_and_need_all_entities(
        conn: sqlite3.Connection) -> None:
    _providers(conn)
    _document(conn, "The board heard from Change Grow Live and Turning Point "
                    "about waiting times.")
    out = cooccurrence.find(conn, ["cgl", "tp"])
    doc = next(r for r in out["results"] if r["record_type"] == "document")
    assert "Change Grow Live" in doc["text"] and "Turning Point" in doc["text"]
    assert doc["link"] == "#/documents?doc=d1&el=e1"      # into the reading room
    assert doc["source_system"] == "committee_paper_promotion"


def test_a_passage_with_only_one_entity_is_not_a_hit(conn: sqlite3.Connection) -> None:
    _providers(conn)
    _document(conn, "Change Grow Live reported no change in demand.")
    out = cooccurrence.find(conn, ["cgl", "tp"])
    assert not any(r["record_type"] == "document" for r in out["results"])


def test_it_needs_two_to_five_entities(conn: sqlite3.Connection) -> None:
    _providers(conn)
    with pytest.raises(QueryError):
        cooccurrence.find(conn, ["cgl"])
    with pytest.raises(QueryError):
        cooccurrence.find(conn, ["a", "b", "c", "d", "e", "f"])


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/cooccurrence" in openapi.document()["paths"]
