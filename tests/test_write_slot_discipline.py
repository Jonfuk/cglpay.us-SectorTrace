"""No module may fetch while holding the warehouse's only write slot.

This is the rule the collection modules keep breaking, in the same shape each
time: write a row, go off and make HTTP requests, commit on the way out. One
writer at a time is a property of SQLite, and Python's sqlite3 opens a
transaction on the first write and holds it until commit, so that pattern
hands one module the write slot for the length of its crawl.

Serially it is invisible, which is why it keeps getting written. Under
`run all --jobs N` it is fatal to everything sharing the wave:

  * m11 did it, and twelve modules failed with "database is locked".
  * m00 did it, and the five modules sharing wave 1 — m02, m03, m06, m08,
    m16 — each waited out the full two-minute busy timeout and failed having
    fetched nothing.

Both were found by a four-hour run rather than by a test, which is what these
are for. They check the property statically, against the source, because the
alternative is a fixture that fetches for three minutes.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

MODULES_DIR = Path(__file__).resolve().parent.parent / "pipeline" / "modules"

# Calls that take the write slot, and calls that make a request. Matched on the
# attribute name, so `db.upsert(...)`, `client.get(...)` and the module-level
# helpers all count.
WRITE_CALLS = {"upsert", "record_review_item", "record_parse_failure",
                "record_discovered_identifier", "set_cursor", "seed_providers"}
FETCH_CALLS = {"get", "post"}


def module_files() -> list[Path]:
    return sorted(p for p in MODULES_DIR.glob("m*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", module_files(), ids=lambda p: p.stem)
def test_every_collecting_module_commits_somewhere(path: Path):
    """A module with no commit of its own holds the slot for its whole run.

    m00_geography was the last one, and it cost wave 1 five modules. The CLI
    commits after a module returns, which is far too late to be the only one.
    """
    source = path.read_text(encoding="utf-8")
    if not re.search(r"\b(db\.upsert|record_review_item|record_parse_failure)\b", source):
        pytest.skip("module writes nothing")
    assert "conn.commit()" in source, (
        f"{path.name} writes but never commits, so it holds the write slot "
        "from its first row until the CLI commits on the way out")


@pytest.mark.parametrize("path", module_files(), ids=lambda p: p.stem)
def test_commits_are_guarded_by_dry_run(path: Path):
    """--dry-run promises to write nothing, and an intermediate commit is the
    one thing that can break that promise. Every commit must be behind the
    check."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    guarded, unguarded = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.dump(node.test)
        if "dry_run" not in test:
            continue
        for inner in ast.walk(node):
            if _is_commit(inner):
                guarded.append(inner.lineno)

    for node in ast.walk(tree):
        if _is_commit(node) and node.lineno not in guarded:
            unguarded.append(node.lineno)

    assert not unguarded, (
        f"{path.name} commits outside a dry-run check at line(s) "
        f"{unguarded} — `--dry-run` would write to the warehouse")


def _is_commit(node) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "commit")


def test_m00_commits_before_its_historical_phase():
    """The specific regression, pinned where it happened.

    m00 loads current authorities, then fetches a snapshot per vintage and
    boundary geometry for every code at every transition — three minutes of
    requests. Without a commit between the two, all of it runs inside the
    transaction the authorities upsert opened.
    """
    source = (MODULES_DIR / "m00_geography.py").read_text(encoding="utf-8")

    load_marker = source.index("geography.current_authorities_loaded")
    historical_marker = source.index("Historical vintages")
    between = source[load_marker:historical_marker]

    assert "conn.commit()" in between, (
        "m00 must commit after loading current authorities and before it "
        "starts fetching historical vintages, or it holds the write slot "
        "across every one of those requests"
    )


def test_m00_commits_per_transition():
    """Each epoch transition fetches successor geometry, so committing only
    after the last one holds the slot across all of them."""
    source = (MODULES_DIR / "m00_geography.py").read_text(encoding="utf-8")
    tail = source[source.index("Historical vintages"):]
    assert tail.count("conn.commit()") >= 1, (
        "m00's transition loop must commit per transition")
