"""Atom feed for external subscription (BETA-089).

One stable Atom 1.0 feed over the "what changed?" stream, filterable by the
same kind / source / since parameters as /api/v1/changes. Entry ids are
host-independent tag URIs so a subscription survives a move between hosts.
"""
from __future__ import annotations

import sqlite3
import threading
from xml.etree import ElementTree as ET

import httpx

from pipeline.web import feeds
from pipeline.web.server import build_server

ATOM = "{http://www.w3.org/2005/Atom}"


def _seed_run(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO run_ledger (run_id, origin, revision, environment, "
        " module_selector, dry_run, started_at, finished_at, status, "
        " modules_total, modules_ok, modules_failed, results_json) VALUES "
        "('rf1', 'cli', 'abc', 'test', 'all', 0, '2026-08-05T00:00:00Z', "
        " '2026-08-05T01:00:00Z', 'ok', 2, 2, 0, '[]')")
    conn.commit()


def test_the_feed_is_wellformed_atom(conn: sqlite3.Connection) -> None:
    xml = feeds.changes_atom(
        conn, self_url="http://localhost:9/api/v1/feed/changes.atom")
    root = ET.fromstring(xml)
    assert root.tag == f"{ATOM}feed"
    assert root.findtext(f"{ATOM}title")
    assert root.findtext(f"{ATOM}id", "").startswith("tag:trace.cglpay.us,2026:feed/changes/")
    assert root.findtext(f"{ATOM}updated")
    self_links = [lk for lk in root.findall(f"{ATOM}link") if lk.get("rel") == "self"]
    assert self_links and self_links[0].get("type") == "application/atom+xml"


def test_entry_ids_are_stable_and_host_independent(conn: sqlite3.Connection) -> None:
    _seed_run(conn)
    a = feeds.changes_atom(conn, self_url="http://host-a/api/v1/feed/changes.atom")
    b = feeds.changes_atom(conn, self_url="https://host-b.example/api/v1/feed/changes.atom")
    ids_a = [e.findtext(f"{ATOM}id") for e in ET.fromstring(a).findall(f"{ATOM}entry")]
    ids_b = [e.findtext(f"{ATOM}id") for e in ET.fromstring(b).findall(f"{ATOM}entry")]
    assert ids_a and ids_a == ids_b                     # same across hosts
    assert all(i.startswith("tag:trace.cglpay.us,2026:change/") for i in ids_a)
    assert all("host-a" not in i and "host-b" not in i for i in ids_a)


def test_the_kind_filter_is_passed_through(conn: sqlite3.Connection) -> None:
    _seed_run(conn)
    xml = feeds.changes_atom(
        conn, kind="release",
        self_url="http://localhost/api/v1/feed/changes.atom?kind=release")
    root = ET.fromstring(xml)
    cats = {c.get("term") for e in root.findall(f"{ATOM}entry")
            for c in e.findall(f"{ATOM}category")}
    assert cats == {"release"}
    assert root.findtext(f"{ATOM}id", "").endswith("/release")


def test_the_route_serves_atom(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    _seed_run(conn)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            r = http.get("/api/v1/feed/changes.atom")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("application/atom+xml")
            root = ET.fromstring(r.text)
            assert root.tag == f"{ATOM}feed"
            # the self link echoes the request host
            self_link = next(lk for lk in root.findall(f"{ATOM}link")
                             if lk.get("rel") == "self")
            assert "127.0.0.1" in self_link.get("href")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_it_is_documented_and_on_the_frozen_surface() -> None:
    from pipeline.web import openapi
    from tests.test_portal_isolation import PUBLIC_API_EXTRA

    assert "/api/v1/feed/changes.atom" in openapi.document()["paths"]
    assert "feed" in PUBLIC_API_EXTRA
