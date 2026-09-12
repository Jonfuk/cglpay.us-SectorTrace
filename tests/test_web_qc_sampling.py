"""Quality-control sampling workspace (BETA-106).

Reproducible random / stratified samples of previously decided records, with
append-only second-look findings. The same seed + source + method + filter
reproduce the same sample; a finding changes no review decision.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.web import qc_sampling
from pipeline.web.queries import QueryError
from pipeline.web.server import build_server


def _seed_rq(conn, n=40):
    for i in range(n):
        conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            " created_at, resolved_at) VALUES (%s, %s, %s, 'confirmed', "
            " '2026-06-01T00:00:00Z', '2026-06-02T00:00:00Z')",
            ("m01" if i % 2 else "m10", "buyer" if i % 3 else "url", f"v{i}"))
    # one unresolved item that must never be sampled
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, status, "
        " created_at) VALUES ('m01', 'buyer', 'pending-x', 'pending', "
        " '2026-06-01T00:00:00Z')")
    conn.commit()


def test_the_draw_is_reproducible_and_seed_sensitive(conn: sqlite3.Connection) -> None:
    _seed_rq(conn)
    a = qc_sampling.draw(conn, seed="audit-2026", source="review_queue", size=10)
    b = qc_sampling.draw(conn, seed="audit-2026", source="review_queue", size=10)
    assert a["record_ids"] == b["record_ids"]
    assert a["sample_size"] == 10 and a["population_size"] == 40  # unresolved excluded
    c = qc_sampling.draw(conn, seed="other", source="review_queue", size=10)
    assert set(c["record_ids"]) != set(a["record_ids"])


def test_a_stratified_draw_hits_the_size(conn: sqlite3.Connection) -> None:
    _seed_rq(conn)
    s = qc_sampling.draw(conn, seed="audit", source="review_queue", size=12,
                          method="stratified", stratify_by="module")
    assert s["sample_size"] == 12 and s["method"] == "stratified"
    strata = {r["module"] for r in s["records"]}
    assert len(strata) >= 2   # both m01 and m10 represented


def test_the_manifest_is_written_once(conn: sqlite3.Connection) -> None:
    _seed_rq(conn)
    a = qc_sampling.draw(conn, seed="s", source="review_queue", size=5)
    qc_sampling.draw(conn, seed="s", source="review_queue", size=5)  # re-draw
    n = conn.execute("SELECT COUNT(*) FROM qc_samples WHERE sample_id = %s",
                     (a["sample_id"],)).fetchone().values().__iter__().__next__()
    assert n == 1
    row = conn.execute("SELECT seed, method, population_size FROM qc_samples "
                       "WHERE sample_id = %s", (a["sample_id"],)).fetchone()
    assert row["seed"] == "s" and row["method"] == "random" and row["population_size"] == 40


def test_findings_are_append_only(conn: sqlite3.Connection) -> None:
    _seed_rq(conn)
    s = qc_sampling.draw(conn, seed="s", source="review_queue", size=5)
    ref = s["record_ids"][0]
    qc_sampling.record_finding(conn, sample_id=s["sample_id"], record_ref=ref,
                                verdict="disagree", note="first look")
    qc_sampling.record_finding(conn, sample_id=s["sample_id"], record_ref=ref,
                                verdict="agree", note="on reflection")
    got = qc_sampling.get(conn, s["sample_id"])
    assert len(got["findings"]) == 2          # both kept, nothing overwritten
    assert got["reviewed"] == 1              # one distinct record

    with pytest.raises(QueryError):
        qc_sampling.record_finding(conn, sample_id=s["sample_id"],
                                    record_ref="999999", verdict="agree")
    with pytest.raises(QueryError):
        qc_sampling.record_finding(conn, sample_id=s["sample_id"],
                                    record_ref=ref, verdict="looks-fine")


def test_the_module_never_updates_or_deletes_findings() -> None:
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "pipeline" / "web"
           / "qc_sampling.py").read_text(encoding="utf-8")
    assert "UPDATE qc_sample_findings" not in src
    assert "DELETE FROM qc_sample_findings" not in src


def test_alias_decisions_is_a_valid_source(conn: sqlite3.Connection) -> None:
    for i in range(8):
        conn.execute(
            "INSERT INTO alias_decisions (decision_id, unmatched_name, "
            " target_scheme, status, decided_by, decided_at) VALUES "
            "(%s, %s, 'buyer', 'accepted', 'r', '2026-07-01T00:00:00Z')",
            (f"d{i}", f"Name {i}"))
    conn.commit()
    s = qc_sampling.draw(conn, seed="s", source="alias_decisions", size=3)
    assert s["sample_size"] == 3 and s["source"] == "alias_decisions"


def test_the_http_routes(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    _seed_rq(conn)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            drawn = http.post("/api/admin/qc-sample/draw",
                              json={"seed": "s", "source": "review_queue", "size": 5}).json()
            sid = drawn["sample_id"]
            assert len(drawn["record_ids"]) == 5
            got = http.get(f"/api/admin/qc-samples/{sid}").json()
            assert got["sample_id"] == sid
            fin = http.post("/api/admin/qc-finding",
                            json={"sample_id": sid, "record_ref": drawn["record_ids"][0],
                                   "verdict": "agree"}).json()
            assert fin["appended"] is True
            after = http.get(f"/api/admin/qc-samples/{sid}").json()
            assert after["reviewed"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
