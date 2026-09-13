"""Offline contract tests for the operator-only OpenAlex shadow collector."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.modules import m36_openalex
from pipeline.registry import ModuleContext


FIXTURE = Path(__file__).parent / "fixtures" / "openalex_works.json"


def _response(httpx_mock, payload: dict, *, since: str | None = None):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.openalex\.org/robots\.txt"),
        status_code=200,
        text="",
    )
    pattern = r"https://api\.openalex\.org/works\?.*"
    if since:
        pattern = r"https://api\.openalex\.org/works\?.*from_updated_date.*"
    httpx_mock.add_response(
        url=re.compile(pattern),
        status_code=200,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def test_disabled_collector_does_not_touch_connection_or_network(settings):
    class NoUse:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("disabled collector touched the database")

    settings.openalex_enabled = False
    ctx = ModuleContext(conn=NoUse(), settings=settings, since=None, dry_run=False, limit=None)
    assert m36_openalex.collect(ctx) == {"queries": 0, "pages": 0, "records": 0}


def test_collects_public_metadata_and_restricts_authorships(settings, conn, httpx_mock):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _response(httpx_mock, payload)
    settings.openalex_enabled = True
    settings.openalex_api_key = "test-openalex-key"
    settings.openalex_query_terms = "substance misuse evaluation"
    settings.openalex_max_pages_per_query = 2
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    assert m36_openalex.collect(ctx) == {"queries": 1, "pages": 1, "records": 4}
    work = conn.execute("SELECT * FROM openalex_records WHERE entity_type = 'work'").fetchone()
    assert work["entity_id"].endswith("W1234567890")
    assert "authorships" not in json.loads(work["payload_json"])
    assert "Example NHS Trust, England" not in work["payload_json"]
    authorship = conn.execute("SELECT * FROM restricted_openalex_authorships").fetchone()
    assert authorship["orcid"].endswith("2345-6789")
    assert "Example NHS Trust, England" in authorship["raw_affiliation_strings_json"]
    candidates = conn.execute(
        "SELECT relationship_type, object_type, status FROM openalex_relationship_candidates "
        "ORDER BY relationship_type"
    ).fetchall()
    assert {(row["relationship_type"], row["object_type"], row["status"]) for row in candidates} == {
        ("about_topic", "topic", "pending_review"),
        ("affiliated_with", "institution", "pending_review"),
        ("funded_by", "funder", "pending_review"),
    }
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE module = 'openalex'"
    ).fetchone()["n"] == 3


def test_since_uses_incremental_filter_and_resets_checkpoint(settings, conn, httpx_mock):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _response(httpx_mock, payload, since="2026-01-01")
    settings.openalex_enabled = True
    settings.openalex_api_key = "test-openalex-key"
    settings.openalex_query_terms = "substance misuse evaluation"
    ctx = ModuleContext(conn=conn, settings=settings, since="2026-01-01", dry_run=False, limit=None)

    m36_openalex.collect(ctx)
    request = next(req for req in httpx_mock.get_requests() if req.url.path.endswith("/works"))
    assert request.url.params["filter"] == "from_updated_date:2026-01-01"
    cursor_key = m36_openalex._cursor_key("substance misuse evaluation", "2026-01-01")
    assert conn.execute("SELECT cursor_value FROM module_cursors WHERE module = %s", (cursor_key,)).fetchone()["cursor_value"] == "*"
