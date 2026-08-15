"""Parameter-style translation between the SQL this codebase writes and the
style psycopg wants.

Every query in this project is written once, in SQLite's style: `?` for
positional parameters and `:name` for named ones. On the SQLite path it is
executed as written. On the PostgreSQL path it passes through `to_psycopg`
below, which rewrites the placeholders to `%s` / `%(name)s`.

The alternative — the one the migration plan proposed — was to rewrite all
146 `conn.execute` call sites to psycopg's style. That was rejected because
it does not actually work: sqlite3 does not accept `%s`, so every query would
have had to exist twice, once per backend, and the two copies would drift.
One SQL string per query, translated at the boundary, keeps the SQLite path
byte-identical and gives PostgreSQL exactly the same statement.

What makes that safe is that this is a scanner and not a regular expression.
A regex over SQL gets `'sqlite_%'` wrong, gets `ESCAPE '\'` wrong, and gets
`?` inside a string literal wrong, and each of those is a silent
wrong-answer rather than an error. The scanner below knows which of five
states it is in, and the test file walks every one of them.

The `%` rule is the non-obvious part. psycopg interpolates `%` in the query
text whenever parameters are passed, so a literal `%` in the SQL — this
codebase has several, e.g. `name NOT LIKE 'sqlite_%'` and
`grant_type LIKE '%drug%alcohol%'` — has to be doubled to survive. That is
true inside string literals, identifiers and comments as much as outside
them, because psycopg scans the whole string and does not parse SQL. It is
*not* true when no parameters are passed: psycopg sends the text untouched
then, so doubling would leave a literal `%%` in the query.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# `:name` — the same character set sqlite3 accepts for a named placeholder.
_NAMED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# `$tag$` / `$$`, PostgreSQL's dollar quoting. Nothing in the SQLite tree uses
# it; the PostgreSQL migration tree uses it for every plpgsql trigger body,
# and a `?` or a `%` inside one of those must survive untouched.
_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def to_psycopg(sql: str, params: Sequence[Any] | Mapping[str, Any] | None
                ) -> tuple[str, Sequence[Any] | Mapping[str, Any] | None]:
    """`(sql, params)` in psycopg's parameter style.

    Returns the statement unchanged, with `None` parameters, when there are
    none to bind. That is not just an optimisation: psycopg only interpolates
    `%` when parameters are present, so a statement sent without them must
    keep its `%` characters exactly as written.

    An empty sequence counts as "no parameters" — `conn.execute(sql, ())` is
    how this codebase spells a statement that takes none, and passing an empty
    tuple through to psycopg would put it in the interpolating path with
    nothing to interpolate.
    """
    if not params:
        return sql, None

    out: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # --- string literal -------------------------------------------------
        # Standard-conforming strings on both engines: a backslash is an
        # ordinary character and a quote is escaped by doubling it. This is
        # what keeps `ESCAPE '\'` intact — treating `\` as an escape would
        # swallow the closing quote and run the scanner off the end of the
        # literal into the rest of the statement.
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append("%%" if sql[i] == "%" else sql[i])
                i += 1
            continue

        # --- quoted identifier ----------------------------------------------
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        out.append('""')
                        i += 2
                        continue
                    out.append('"')
                    i += 1
                    break
                out.append("%%" if sql[i] == "%" else sql[i])
                i += 1
            continue

        # --- dollar-quoted body ---------------------------------------------
        if ch == "$":
            match = _DOLLAR_TAG.match(sql, i)
            if match:
                tag = match.group(0)
                end = sql.find(tag, match.end())
                end = n if end == -1 else end + len(tag)
                body = sql[i:end]
                out.append(body.replace("%", "%%"))
                i = end
                continue

        # --- line comment ---------------------------------------------------
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            end = n if end == -1 else end
            out.append(sql[i:end].replace("%", "%%"))
            i = end
            continue

        # --- block comment (PostgreSQL nests these; SQLite does not) --------
        if sql.startswith("/*", i):
            depth = 0
            start = i
            while i < n:
                if sql.startswith("/*", i):
                    depth += 1
                    i += 2
                elif sql.startswith("*/", i):
                    depth -= 1
                    i += 2
                    if depth == 0:
                        break
                else:
                    i += 1
            out.append(sql[start:i].replace("%", "%%"))
            continue

        # --- placeholders and everything else -------------------------------
        if ch == "?":
            out.append("%s")
            i += 1
            continue

        if ch == ":":
            # `::` is PostgreSQL's cast operator, not a placeholder. Nothing in
            # the SQLite tree writes one, but the PostgreSQL migration tree
            # does, and this function is the only thing standing between the
            # two.
            if sql.startswith("::", i):
                out.append("::")
                i += 2
                continue
            match = _NAMED.match(sql, i + 1)
            if match:
                out.append(f"%({match.group(0)})s")
                i = match.end()
                continue

        if ch == "%":
            out.append("%%")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), params
