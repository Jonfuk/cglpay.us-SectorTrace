"""The entity graph: views over evidence already collected.

No new source and no new fetching — company officers from m04, charity
identifiers from m03, contract suppliers from m01, CQC registrations from m05
and tribunal respondents from m02, joined. The data was already on disk and
unconnected.

Two things must hold. Every edge has to say what it rests on, because an edge
built from an unconfirmed name match is a lead rather than a fact. And
anything that can name a person has to be restricted, because a graph linking
a person to a company to a contract to a local authority is a personal-data
product however public each individual fact is.
"""
from __future__ import annotations

import pytest

from pipeline import db
from pipeline.exports import assert_no_restricted_tables, guard_not_restricted

GRAPH_VIEWS = ["v_entity_edges", "v_entity_edge_confidence"]
RESTRICTED_VIEWS = ["restricted_v_shared_officers", "restricted_v_officer_edges"]


def _views(conn) -> set[str]:
    return {r["viewname"] for r in conn.execute(
        "SELECT viewname FROM pg_views WHERE schemaname = current_schema()")}


def test_the_graph_views_exist(conn):
    present = _views(conn)
    for view in GRAPH_VIEWS + RESTRICTED_VIEWS:
        assert view in present, f"{view} was not created"


@pytest.mark.parametrize("view", GRAPH_VIEWS + RESTRICTED_VIEWS)
def test_every_view_is_queryable(conn, view):
    """A view whose SQL references a column that does not exist fails only
    when someone selects from it — which would be in front of a user.
    """
    conn.execute(f"SELECT * FROM {view} LIMIT 1").fetchall()


def test_every_edge_declares_what_it_rests_on(conn):
    columns = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        ("v_entity_edges",),
    )}
    assert {"source_type", "source_id", "relationship",
            "target_type", "target_id", "basis"} <= columns


def test_the_confidence_view_breaks_edges_down_by_basis():
    """Published beside any graph figure. On the live warehouse, 210 of 262
    edges rest on an unmatched supplier name — a graph read as fact without
    this number would be badly misleading.
    """
    from pathlib import Path

    sql = (Path(__file__).resolve().parent.parent / "pipeline" / "migrations"
           / "postgres" / "0023_entity_graph.sql").read_text(encoding="utf-8")
    assert "v_entity_edge_confidence" in sql
    assert "GROUP BY relationship, basis" in sql


# --- personal data ------------------------------------------------------------------

def test_officer_views_are_restricted(conn):
    """They name individuals. The prefix is what the export guard keys on."""
    for view in RESTRICTED_VIEWS:
        assert view.startswith("restricted_")
        with pytest.raises(ValueError):
            guard_not_restricted(view)


def test_the_guard_now_sees_views_not_just_tables(conn):
    """The gap this closed: restricted_tables() filtered on type='table', so a
    restricted_ view — a personal-data query saved under a name — passed
    assert_no_restricted_tables untouched.
    """
    found = db.restricted_tables(conn)
    for view in RESTRICTED_VIEWS:
        assert view in found, f"{view} is invisible to the export guard"

    with pytest.raises(ValueError):
        assert_no_restricted_tables(conn, ["v_entity_edges", RESTRICTED_VIEWS[0]])


def test_the_public_edge_view_names_no_one(conn):
    """Organisation-to-organisation only. Officer names live exclusively in
    the restricted views.
    """
    columns = {r["column_name"].lower() for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        ("v_entity_edges",),
    )}
    assert not any("officer" in c or "person" in c or "name" in c and "target_label" != c
                    for c in columns if c not in {"target_label"})


def test_a_public_export_cannot_pull_in_an_officer_view(conn):
    assert_no_restricted_tables(conn, GRAPH_VIEWS)   # must not raise
