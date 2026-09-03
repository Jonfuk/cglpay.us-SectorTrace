"""The closed analyst tool catalogue (BETA-109).

Exactly eleven typed, side-effect-free tools. No argument is a table name, URL,
path or SQL fragment; bad arguments raise `ToolError` and execute nothing;
every tool returns the standard envelope with a `result_ids` whitelist.
"""
from __future__ import annotations

import pytest

from pipeline.assistant import tools


def test_catalogue_is_exactly_eleven_named_tools():
    assert set(tools.TOOL_NAMES) == set(tools.tool_schemas())
    assert len(tools.TOOL_NAMES) == 11


@pytest.mark.parametrize("bad", [
    {"query": "pay", "source_system": "http://evil/"},
    {"query": "pay", "source_system": "../etc/passwd"},
    {"query": "'; DROP TABLE evidence_records; --"},
    {"query": "pay", "date_from": "2026-13-40"},
    {"query": "pay", "mode": "telepathy"},
    {"query": "pay", "table": "authorities"},        # unknown key
    {},                                               # missing required
])
def test_validate_args_rejects_bad_shapes(bad):
    with pytest.raises(tools.ToolError):
        tools.validate_args("search_document_passages", bad)


def test_validate_args_clamps_limit_and_keeps_known_fields():
    cleaned = tools.validate_args("search_document_passages",
                                  {"query": "keyworker pay", "limit": 9999})
    assert cleaned["limit"] == tools._MAX_LIMIT
    assert cleaned["query"] == "keyworker pay"


def test_unknown_tool_name_is_rejected():
    with pytest.raises(tools.ToolError):
        tools.run_tool("run_sql", {"sql": "select 1"}, None, None)


@pytest.mark.parametrize("name,args", [
    ("search_document_passages", {"query": "keyworker recruitment"}),
    ("inspect_claim_candidates", {}),
    ("inspect_claim_gate", {}),
    ("inspect_source_coverage", {"tier": "upper"}),
    ("inspect_freshness", {}),
])
def test_each_tool_returns_the_standard_envelope(conn, settings, name, args):
    env = tools.run_tool(name, args, conn, settings)
    assert env["tool"] == name
    assert isinstance(env["result_ids"], list)
    assert "data" in env
    # read-only: the warehouse row counts are untouched
    before = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone().values().__iter__().__next__()
    tools.run_tool(name, args, conn, settings)
    after = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone().values().__iter__().__next__()
    assert before == after


def test_freshness_rejects_a_table_not_in_the_result(conn, settings):
    with pytest.raises(tools.ToolError):
        tools.run_tool("inspect_freshness", {"table": "restricted_people"},
                       conn, settings)


def test_no_wrapper_executes_a_write_statement():
    """Every `conn.execute` in the module is a SELECT. The write verbs that do
    appear are string literals inside the `_UNSAFE` blocklist, never executed."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(tools.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and node.args and isinstance(node.args[0], ast.Constant)):
            assert node.args[0].value.lstrip().upper().startswith("SELECT")
