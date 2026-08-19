"""The two migration trees describe the same warehouse.

`pipeline/migrations/` is SQLite's and `pipeline/migrations/postgres/` is
PostgreSQL's, and the whole argument for keeping two hand-written trees rather
than generating one from the other is that they can be checked against each
other. This is that check.

It is deliberately structural rather than executed: it reads both trees as
text and compares what they declare. That means it runs in the offline suite,
on every commit, with no PostgreSQL server anywhere — which matters, because
the failure this is guarding against is somebody adding `0034_thing.sql` to
one tree and not the other, and that mistake should not wait for a server to
be reachable before it is caught.

What it cannot check is that the two produce the same *behaviour*. Only a
live server does that, and those tests live behind the `postgres` marker.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"
POSTGRES = MIGRATIONS / "postgres"

_TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
                     re.IGNORECASE)
_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE)
_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE)
_TRIGGER = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE)


def strip_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def declarations(directory: Path) -> dict[str, set[str]]:
    """Every object each tree declares, by kind."""
    text = strip_comments(
        "\n".join(p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.sql"))))
    return {
        "tables": set(_TABLE.findall(text)),
        "views": set(_VIEW.findall(text)),
        "indexes": set(_INDEX.findall(text)),
        "triggers": set(_TRIGGER.findall(text)),
    }


def columns_by_table(directory: Path) -> dict[str, list[str]]:
    """Column names per table, in declaration order.

    A rough parse — it reads the parenthesised body of each `CREATE TABLE` and
    takes the first identifier of every line that starts one. Good enough to
    catch a column present in one tree and absent from the other, which is the
    thing worth catching; it deliberately does not try to compare types, since
    those legitimately differ (`TEXT` vs `text`, `INTEGER` vs `bigint`).
    """
    out: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.sql")):
        sql = strip_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\n\s*\);",
                sql, re.IGNORECASE | re.DOTALL):
            table, body = match.group(1), match.group(2)
            names = []
            for line in body.splitlines():
                line = line.strip()
                if not line:
                    continue
                head = line.split()[0]
                if head.upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
                    continue
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", head):
                    names.append(head)
            out[table] = names
    return out


class TestTheTreesMatch:
    def test_same_filenames(self):
        """Same names, so the two files for one change are diffable side by
        side and `git log` on one leads to the other."""
        sqlite_names = {p.name for p in MIGRATIONS.glob("*.sql")}
        postgres_names = {p.name for p in POSTGRES.glob("*.sql")}
        assert sqlite_names == postgres_names, (
            f"only in SQLite tree: {sorted(sqlite_names - postgres_names)}; "
            f"only in PostgreSQL tree: {sorted(postgres_names - sqlite_names)}")

    def test_the_expected_number_of_them(self):
        # A count, so that deleting the same file from both trees is still a
        # deliberate act rather than something the equality check above waves
        # through. 51 = 50 + 0051 (entity-name lookup correction).
        assert len(list(MIGRATIONS.glob("*.sql"))) == 51

    @pytest.mark.parametrize("kind", ["tables", "views", "indexes", "triggers"])
    def test_same_objects_declared(self, kind):
        sqlite_objects = declarations(MIGRATIONS)[kind]
        postgres_objects = declarations(POSTGRES)[kind]
        assert sqlite_objects == postgres_objects, (
            f"{kind} only in SQLite: {sorted(sqlite_objects - postgres_objects)}; "
            f"only in PostgreSQL: {sorted(postgres_objects - sqlite_objects)}")

    def test_same_columns_per_table(self):
        sqlite_columns = columns_by_table(MIGRATIONS)
        postgres_columns = columns_by_table(POSTGRES)
        assert set(sqlite_columns) == set(postgres_columns)
        mismatched = {
            table: (sqlite_columns[table], postgres_columns[table])
            for table in sqlite_columns
            if sqlite_columns[table] != postgres_columns[table]
        }
        assert not mismatched, f"column lists differ: {mismatched}"

    def test_restricted_tables_are_restricted_in_both(self):
        """Settled decision 3 is enforced by a name prefix, so a table that
        lost the prefix in one tree would leave personal data exportable on
        that backend only."""
        sqlite_restricted = {t for t in declarations(MIGRATIONS)["tables"]
                              if t.startswith("restricted_")}
        postgres_restricted = {t for t in declarations(POSTGRES)["tables"]
                                if t.startswith("restricted_")}
        assert sqlite_restricted == postgres_restricted
        assert sqlite_restricted, "no restricted_ tables found — the parse is wrong"


class TestPostgresTreeSpecifics:
    # The one file allowed to say `group_concat`, because defining that name
    # for PostgreSQL is its entire job. Scoped to the filename rather than
    # relaxed for the whole tree, and paired with the test below so the
    # exemption cannot quietly start covering a real use of SQLite's aggregate.
    DEFINES_GROUP_CONCAT = "0034_group_concat_compat.sql"

    def test_no_sqlite_only_constructs_survive(self):
        """Checked against code, not comments — several of the comments in
        that tree name the construct they replaced, on purpose."""
        banned = re.compile(
            r"\b(AUTOINCREMENT|GROUP_CONCAT|sqlite_master|PRAGMA)\b|RAISE\s*\(\s*ABORT",
            re.IGNORECASE)
        offenders = []
        for path in sorted(POSTGRES.glob("*.sql")):
            if path.name == self.DEFINES_GROUP_CONCAT:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("--", 1)[0]
                if banned.search(code):
                    offenders.append(f"{path.name}:{number}")
        assert not offenders, f"SQLite-only constructs in the PostgreSQL tree: {offenders}"

    def test_the_exempt_file_only_defines_group_concat(self):
        """The exemption above is for a definition, not for a call.

        If this file ever grows a `SELECT ... GROUP_CONCAT(...)` — or any of
        the other banned constructs — the skip in the previous test would hide
        it, so the same ban is applied here minus the two forms that declare
        the aggregate.
        """
        path = POSTGRES / self.DEFINES_GROUP_CONCAT
        banned = re.compile(
            r"\b(AUTOINCREMENT|sqlite_master|PRAGMA)\b|RAISE\s*\(\s*ABORT", re.IGNORECASE)
        declaring = re.compile(
            r"CREATE\s+(OR\s+REPLACE\s+)?(AGGREGATE|FUNCTION)\s+_?group_concat", re.IGNORECASE)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("--", 1)[0]
            assert not banned.search(code), f"{path.name}:{number}"
            if re.search(r"\bgroup_concat\b", code, re.IGNORECASE):
                assert declaring.search(code), (
                    f"{path.name}:{number} mentions group_concat without declaring it: "
                    f"{code.strip()}")

    def test_both_arities_are_defined(self):
        """SQLite's GROUP_CONCAT takes one argument (comma-separated) or two
        (explicit separator), and the export layer uses both."""
        sql = (POSTGRES / self.DEFINES_GROUP_CONCAT).read_text(encoding="utf-8")
        assert "AGGREGATE group_concat(text, text)" in sql
        assert "AGGREGATE group_concat(text)" in sql

    def test_triggers_raise_an_integrity_error(self):
        """The five refusals are settled decision 4's mechanism.

        A plain `RAISE EXCEPTION` reaches Python as `RaiseException`, which is
        not an `IntegrityError` — so the suites asserting a refusal, and any
        call site catching one to show the operator a message instead of a
        traceback, would silently stop matching. Every raise in this tree must
        carry the errcode that puts it in the right class.
        """
        for path in sorted(POSTGRES.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            raises = text.count("RAISE EXCEPTION")
            errcodes = text.count("ERRCODE = 'integrity_constraint_violation'")
            assert raises == errcodes, (
                f"{path.name}: {raises} RAISE EXCEPTION but {errcodes} with an errcode")

    def test_all_refusals_are_present(self):
        """The seven refusals are settled decision 4's mechanism, plus the
        claims registry's (migration 0048): the trigger set is now seven, and
        this list is the contract a new one must be added to deliberately."""
        triggers = declarations(POSTGRES)["triggers"]
        assert triggers == {
            "cdp_documents_need_a_promotion",
            "committee_papers_need_a_promotion",
            "foi_requests_need_a_promotion",
            "census_metric_verify_needs_a_decision",
            "census_metric_insert_needs_a_decision",
            "claims_insert_needs_a_decision",
            "claims_status_needs_a_decision",
            "ai_promotion_requires_provenance",
        }

    def test_every_trigger_function_returns_new(self):
        """A BEFORE INSERT trigger returning NULL skips the row instead of
        refusing it — a refusal that silently succeeds is worse than no
        refusal at all."""
        for path in sorted(POSTGRES.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            functions = text.count("RETURNS trigger")
            returns = text.count("RETURN NEW;")
            assert functions == returns, (
                f"{path.name}: {functions} trigger functions but {returns} RETURN NEW")


class TestConflictTargetMatchesItsIndex:
    """`db.record_parse_failure` names an expression index by repeating its
    expressions. PostgreSQL matches them textually, and a mismatch is not a
    fallback — it is a runtime error on the first parse failure of a crawl
    that has already made all of its requests. The two live in different
    files, so something has to hold them together."""

    EXPRESSIONS = ("module", "COALESCE(source_url, '')", "COALESCE(field_name, '')",
                   "COALESCE(raw_fragment, '')")

    def test_the_index_declares_them(self):
        sql = (POSTGRES / "0007_dedupe_audit_tables.sql").read_text(encoding="utf-8")
        index = sql[sql.index("CREATE UNIQUE INDEX IF NOT EXISTS idx_parse_failures_natural"):]
        for expression in self.EXPRESSIONS:
            assert expression in index

    def test_the_upsert_names_the_same_ones(self):
        import inspect

        from pipeline import db

        source = inspect.getsource(db.record_parse_failure)
        for expression in self.EXPRESSIONS:
            assert expression in source

    def test_sqlite_tree_declares_them_identically(self):
        sql = (MIGRATIONS / "0007_dedupe_audit_tables.sql").read_text(encoding="utf-8")
        index = sql[sql.index("CREATE UNIQUE INDEX IF NOT EXISTS idx_parse_failures_natural"):]
        for expression in self.EXPRESSIONS:
            assert expression in index
