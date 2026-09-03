"""Validation-rule explorer (BETA-104).

A read-only catalogue of the warehouse's validation rules, derived on the
request: schema rules from the live schema, observed rules from
`parse_failures` and `review_queue`. Failure examples are reduced to their
shape before they leave the process — the raw fragment is never sent.
"""
from __future__ import annotations

import re
import sqlite3
import threading

import httpx

from pipeline.validation_rules import RULE_NOTES
from pipeline.web import validation
from pipeline.web.server import build_server


def _rule(out: dict, rule_id: str) -> dict | None:
    for rule in (*out["schema_rules"], *out["observed_rules"]):
        if rule["id"] == rule_id:
            return rule
    return None


def test_rules_are_typed_and_derived(conn: sqlite3.Connection) -> None:
    out = validation.rules(conn, today="2026-08-29")
    assert out["backend"] == "postgres"
    assert set(out["kinds"]) == {"trigger", "check", "provenance",
                                  "parse_failure", "review_gate"}
    assert set(out["counts"]["by_kind"]) <= set(out["kinds"])
    kinds_present = {r["kind"] for r in out["schema_rules"]}
    assert {"trigger", "provenance"} <= kinds_present
    assert "derived on the request" in out["note"].lower()
    assert "raw fragment never sent" in out["redaction"].lower()
    for rule in (*out["schema_rules"], *out["observed_rules"]):
        assert rule["purpose"], rule["id"]


def test_promotion_triggers_are_catalogued_with_a_specific_purpose(
        conn: sqlite3.Connection) -> None:
    rule = _rule(validation.rules(conn), "trigger:cdp_documents_need_a_promotion")
    assert rule is not None and rule["kind"] == "trigger"
    assert rule["purpose"] == RULE_NOTES["trigger:cdp_documents_need_a_promotion"]
    assert "promot" in rule["detail"].lower()


def test_no_rule_note_is_stale(conn: sqlite3.Connection) -> None:
    """Every hand-kept note must still match a rule the derivation produces."""
    out = validation.rules(conn)
    ids = {r["id"] for r in (*out["schema_rules"], *out["observed_rules"])}
    assert set(RULE_NOTES) <= ids, set(RULE_NOTES) - ids


def test_provenance_is_one_rule_per_evidence_table(conn: sqlite3.Connection) -> None:
    rule = _rule(validation.rules(conn), "provenance:contracts")
    assert rule is not None and rule["kind"] == "provenance"
    assert set(rule["fields"]) <= {"source_url", "retrieved_at", "payload_sha256"}
    assert isinstance(rule["enforced"], bool)


def test_parse_failures_become_rules_with_shape_only_examples(
        conn: sqlite3.Connection) -> None:
    fragment = "Jane Doe, 07/1980, ref AB-99"
    conn.execute(
        "INSERT INTO parse_failures (module, source_url, field_name, "
        " raw_fragment, reason, created_at) VALUES "
        "('m02_tribunals', 'https://www.gov.uk/a/b?token=secret', "
        " 'claimant', ?, 'name not in expected position', '2026-08-20T00:00:00Z')",
        (fragment,))
    conn.commit()

    rule = _rule(validation.rules(conn, today="2026-08-29"),
                 "parse:m02_tribunals:claimant")
    assert rule is not None and rule["kind"] == "parse_failure"
    assert rule["counts"] == {"total": 1, "recent": 1}
    assert rule["modules"] == ["m02_tribunals"] and rule["fields"] == ["claimant"]

    ex = rule["examples"][0]
    assert "raw_fragment" not in ex
    assert ex["chars"] == len(fragment)
    # shape keeps only x / 9 / punctuation — nothing readable survives
    assert re.fullmatch(r"[x9\W]+", ex["shape"])
    assert "Jane" not in ex["shape"] and "1980" not in ex["shape"]
    # the source URL is reduced to its host, no path and no query
    assert ex["source_host"] == "www.gov.uk"
    assert "/" not in ex["source_host"] and "?" not in ex["source_host"]

    # outside the window the recent count falls to zero, total stays
    old = _rule(validation.rules(conn, today="2099-01-01"),
                "parse:m02_tribunals:claimant")
    assert old["counts"] == {"total": 1, "recent": 0}


def test_review_queue_becomes_a_gate_rule(conn: sqlite3.Connection) -> None:
    for value, status in [("ACME", "pending"), ("BETA CO", "pending"),
                           ("GAMMA", "confirmed")]:
        conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            " created_at) VALUES ('m01_procurement', 'buyer_name', ?, ?, "
            " '2026-08-01T00:00:00Z')", (value, status))
    conn.commit()
    rule = _rule(validation.rules(conn), "review:m01_procurement:buyer_name")
    assert rule is not None and rule["kind"] == "review_gate"
    assert rule["counts"]["pending"] == 2
    assert rule["counts"]["resolved"] == 1


def test_the_route_serves_the_catalogue(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            out = http.get("/api/admin/validation-rules").json()
            assert out["counts"]["by_kind"]["trigger"] > 0
            assert "schema_rules" in out and "observed_rules" in out
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
