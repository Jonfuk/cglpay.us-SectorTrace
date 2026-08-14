"""The parameter-style scanner.

Every case here is a statement this codebase actually executes, or a shape it
would execute if someone wrote one more query in the existing style. A bug in
this file's subject is silent — the statement runs, binds the wrong thing or
searches for the wrong pattern, and returns a plausible answer — so the cases
are deliberately exhaustive about the states the scanner can be in rather
than about the queries that happen to exist today.
"""
from __future__ import annotations

import pytest

from pipeline.sqldialect import to_psycopg


class TestNoParameters:
    """Without parameters psycopg sends the text untouched, so the scanner
    must not run at all — doubling a `%` here would leave `%%` in the query."""

    @pytest.mark.parametrize("params", [None, (), [], {}])
    def test_statement_is_returned_verbatim(self, params):
        sql = "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        assert to_psycopg(sql, params) == (sql, None)

    def test_question_mark_is_left_alone_without_parameters(self):
        # Not a real statement, but it pins the rule: no parameters means no
        # translation, not "translate anyway and hope".
        assert to_psycopg("SELECT '?'", None)[0] == "SELECT '?'"


class TestPositional:
    def test_qmark_becomes_percent_s(self):
        sql, params = to_psycopg("SELECT * FROM http_cache WHERE url = ?", ("u",))
        assert sql == "SELECT * FROM http_cache WHERE url = %s"
        assert params == ("u",)

    def test_every_placeholder_is_translated(self):
        sql, _ = to_psycopg(
            "INSERT INTO module_cursors (module, cursor_value, updated_at) "
            "VALUES (?, ?, ?)", ("m", "c", "t"))
        assert sql.endswith("VALUES (%s, %s, %s)")

    def test_limit_offset(self):
        sql, _ = to_psycopg("SELECT 1 FROM t ORDER BY id LIMIT ? OFFSET ?", (10, 0))
        assert sql.endswith("LIMIT %s OFFSET %s")


class TestNamed:
    def test_named_becomes_pyformat(self):
        sql, params = to_psycopg("SELECT :a, :b_2", {"a": 1, "b_2": 2})
        assert sql == "SELECT %(a)s, %(b_2)s"
        assert params == {"a": 1, "b_2": 2}

    def test_upsert_shape_from_db_upsert(self):
        sql, _ = to_psycopg(
            "INSERT INTO authorities (ons_code, name) VALUES (:ons_code, :name) "
            "ON CONFLICT (ons_code) DO UPDATE SET name = excluded.name",
            {"ons_code": "E06", "name": "x"})
        assert "VALUES (%(ons_code)s, %(name)s)" in sql
        assert "name = excluded.name" in sql

    def test_colon_not_followed_by_a_name_is_left_alone(self):
        sql, _ = to_psycopg("SELECT '12:30' AS t, ? AS x", ("x",))
        assert "12:30" in sql

    def test_double_colon_cast_survives(self):
        # Only the PostgreSQL migration tree writes these, but this function
        # is the only thing between that tree and psycopg.
        sql, _ = to_psycopg("SELECT value::text FROM t WHERE id = ?", (1,))
        assert sql == "SELECT value::text FROM t WHERE id = %s"


class TestLiteralPercent:
    """The rule that costs a silent wrong answer when it is missed."""

    def test_percent_in_a_string_literal_is_doubled(self):
        sql, _ = to_psycopg(
            "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            "AND type = ?", ("table",))
        assert "'sqlite\\_%%'" not in sql          # not escaped, just doubled
        assert "'sqlite_%%'" in sql
        assert sql.endswith("type = %s")

    def test_multiple_percents_in_one_literal(self):
        # pipeline/exports/echarts.py:137
        sql, _ = to_psycopg(
            "SELECT 1 FROM la_public_health_grants "
            "WHERE grant_type LIKE '%drug%alcohol%' AND unit = ?", ("gbp",))
        assert "'%%drug%%alcohol%%'" in sql

    def test_bare_percent_outside_a_literal_is_doubled(self):
        sql, _ = to_psycopg("SELECT 10 % ? AS r", (3,))
        assert sql == "SELECT 10 %% %s AS r"

    def test_percent_in_a_quoted_identifier_is_doubled(self):
        sql, _ = to_psycopg('SELECT "odd%name" FROM t WHERE id = ?', (1,))
        assert '"odd%%name"' in sql


class TestStringLiteralIsOpaque:
    def test_question_mark_inside_a_literal_is_not_a_placeholder(self):
        sql, _ = to_psycopg("SELECT 'why?' AS q, ? AS given", ("x",))
        assert sql == "SELECT 'why?' AS q, %s AS given"

    def test_named_placeholder_inside_a_literal_is_not_one(self):
        sql, _ = to_psycopg("SELECT ':not_a_param' AS q, :real", {"real": 1})
        assert sql == "SELECT ':not_a_param' AS q, %(real)s"

    def test_doubled_quote_does_not_end_the_literal(self):
        sql, _ = to_psycopg("SELECT 'it''s ? here' AS q, ? AS given", ("x",))
        assert sql == "SELECT 'it''s ? here' AS q, %s AS given"

    def test_backslash_is_an_ordinary_character(self):
        """`ESCAPE '\\'` is the live case.

        Treating a backslash as an escape would consume the closing quote,
        leave the scanner inside a string literal for the rest of the
        statement, and silently stop translating every placeholder after it.
        """
        sql, _ = to_psycopg(
            r"SELECT * FROM t WHERE name LIKE ? ESCAPE '\' AND id = ?",
            ("100\\%", 1))
        assert sql == r"SELECT * FROM t WHERE name LIKE %s ESCAPE '\' AND id = %s"

    def test_escape_literal_followed_by_more_placeholders(self):
        # pipeline/web/queries.py:255 builds one of these per column.
        sql, _ = to_psycopg(
            "SELECT * FROM t WHERE CAST(\"a\" AS TEXT) LIKE :q ESCAPE '\\' "
            "OR CAST(\"b\" AS TEXT) LIKE :q ESCAPE '\\'", {"q": "%x%"})
        assert sql.count("%(q)s") == 2


class TestComments:
    def test_line_comment_percent_is_doubled_and_contents_ignored(self):
        sql, _ = to_psycopg("SELECT ?  -- 50% of rows, ? is not a param\nFROM t",
                             (1,))
        assert sql.startswith("SELECT %s")
        assert "50%% of rows, ? is not a param" in sql

    def test_block_comment_is_opaque(self):
        sql, _ = to_psycopg("SELECT /* ? and :x and 9% */ ? FROM t", (1,))
        assert "/* ? and :x and 9%% */" in sql
        assert sql.endswith("%s FROM t")

    def test_nested_block_comment(self):
        sql, _ = to_psycopg("SELECT /* a /* b ? */ c */ ? FROM t", (1,))
        assert sql == "SELECT /* a /* b ? */ c */ %s FROM t"


class TestDollarQuoting:
    def test_function_body_is_opaque(self):
        """The PostgreSQL trigger bodies in migrations/postgres/ contain `%`
        in their RAISE messages and must reach the server unaltered."""
        sql, _ = to_psycopg(
            "CREATE FUNCTION f() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'no: 100% refused, ? too'; END $$ "
            "LANGUAGE plpgsql; SELECT ?", (1,))
        assert "'no: 100%% refused, ? too'" in sql
        assert sql.endswith("SELECT %s")

    def test_tagged_dollar_quote(self):
        sql, _ = to_psycopg("SELECT $tag$ ? :x 5% $tag$, ?", (1,))
        assert "$tag$ ? :x 5%% $tag$" in sql
        assert sql.endswith(", %s")


class TestRealStatementsFromTheCodebase:
    """Statements copied from the tree, so a change to one of them that this
    scanner cannot handle fails here rather than in production."""

    def test_record_parse_failure(self):
        sql, _ = to_psycopg(
            "INSERT INTO parse_failures (module, source_url, field_name, "
            "raw_fragment, reason, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (module, COALESCE(source_url, ''), "
            "COALESCE(field_name, ''), COALESCE(raw_fragment, '')) "
            "DO UPDATE SET reason = excluded.reason",
            ("m", None, "f", "r", "why", "now"))
        assert "VALUES (%s, %s, %s, %s, %s, %s)" in sql
        # The conflict target's empty-string literals must survive exactly:
        # PostgreSQL matches the index expression textually.
        assert "COALESCE(source_url, '')" in sql

    def test_record_review_item_with_its_where_clause(self):
        sql, _ = to_psycopg(
            "INSERT INTO review_queue (module, item_type, raw_value, "
            "context_json, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?) "
            "ON CONFLICT (module, item_type, raw_value) DO UPDATE SET "
            "context_json = excluded.context_json "
            "WHERE review_queue.status = 'pending'",
            ("m", "t", "v", None, "now"))
        assert "'pending'" in sql
        assert sql.count("%s") == 5

    def test_restricted_tables_lookup(self):
        sql, params = to_psycopg(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
            "AND name LIKE ?", ("restricted_%",))
        assert sql.endswith("name LIKE %s")
        # The wildcard is in the parameter, where psycopg never looks.
        assert params == ("restricted_%",)
