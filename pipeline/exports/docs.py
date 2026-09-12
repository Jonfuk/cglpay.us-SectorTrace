"""Generates docs/DATA_DICTIONARY.md from the live schema.

The brief requires the dictionary be generated rather than written by hand,
so it cannot drift from the database. Table and column comments are read from
the migration files, which is where the reasoning already lives.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline import catalog
from pipeline.exports import PERSONAL_DATA_COLUMNS, RESTRICTED_PREFIX
from pipeline.exports.sheets import TAB_TABLES

_TABLE_COMMENT_RE = re.compile(
    r"((?:^--[^\n]*\n)+)\s*CREATE TABLE(?: IF NOT EXISTS)? (\w+)", re.MULTILINE)


def collect_table_notes(migrations_dir: Path) -> dict[str, str]:
    """Leading comment block above each CREATE TABLE, as its description."""
    notes: dict[str, str] = {}
    paths = sorted(migrations_dir.glob("*.sql"))
    if not paths and migrations_dir.name != "postgres":
        paths = sorted((migrations_dir / "postgres").glob("*.sql"))
    for path in paths:
        sql = path.read_text(encoding="utf-8")
        for comment_block, table in _TABLE_COMMENT_RE.findall(sql):
            lines = [re.sub(r"^--\s?", "", line).rstrip()
                      for line in comment_block.strip().splitlines()]
            text = " ".join(line for line in lines if line).strip()
            if text:
                notes.setdefault(table, text)
    return notes


def _exportable(table: str, column: str) -> str:
    if table.startswith(RESTRICTED_PREFIX):
        return "restricted"
    if column in PERSONAL_DATA_COLUMNS:
        return "restricted"
    return "exportable"


def render_data_dictionary(conn, migrations_dir: Path) -> str:
    notes = collect_table_notes(migrations_dir)
    tab_for_table: dict[str, list[str]] = {}
    for tab, tables in TAB_TABLES.items():
        for table in tables:
            tab_for_table.setdefault(table, []).append(tab)

    objects = catalog.list_objects(conn)
    objects.sort(key=lambda obj: (obj["type"], obj["name"]))

    lines = [
        "# Data dictionary",
        "",
        "**Generated from the live schema — do not edit by hand.** Regenerate with:",
        "",
        "```bash",
        "./start.sh export docs",
        "```",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "`restricted` columns hold personal data. They are excluded from every export by "
        "default and `pipeline.exports.guard_columns()` raises if one is referenced.",
        "",
    ]

    restricted_tables = [o["name"] for o in objects
                          if o["name"].startswith(RESTRICTED_PREFIX)]
    if restricted_tables:
        lines += [
            "## Restricted tables",
            "",
            "Never exported. Listed here so the boundary is visible, not to invite use.",
            "",
            *[f"- `{name}`" for name in restricted_tables],
            "",
        ]

    for obj in objects:
        name, kind = obj["name"], obj["type"]
        columns = catalog.columns_of(conn, name)
        if not columns:
            continue
        row_count = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]

        lines.append(f"## `{name}`")
        lines.append("")
        lines.append(f"*{kind}* — {row_count:,} rows.")
        if name in notes:
            lines.append("")
            lines.append(notes[name])
        if name in tab_for_table:
            lines.append("")
            lines.append(f"Feeds Sheets tab(s): {', '.join(sorted(tab_for_table[name]))}.")
        lines += ["", "| Column | Type | Null | Export |", "| --- | --- | --- | --- |"]
        for column in columns:
            column_name = column["name"]
            column_type = column["type"] or ""
            notnull = column["notnull"]
            lines.append(
                f"| `{column_name}` | {column_type} | "
                f"{'NOT NULL' if notnull else 'nullable'} | "
                f"{_exportable(name, column_name)} |")
        lines.append("")

    return "\n".join(lines)


def write_data_dictionary(conn, migrations_dir: Path, docs_dir: Path) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / "DATA_DICTIONARY.md"
    path.write_text(render_data_dictionary(conn, migrations_dir), encoding="utf-8")
    return path
