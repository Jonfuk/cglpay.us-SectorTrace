"""Feature-level graceful degradation (BETA-068).

Live review of the populated beta found schema drift reaching the reader as
raw PostgreSQL error text on the document-search and run-ledger surfaces: a
`UndefinedTable` traceback where a section should be. A partial deployment —
a migration not yet applied, an extension the server lacks, one section of a
page timing out — must degrade one capability at a time and must never make
internal SQL part of the user interface.

Two things live here:

* ``FeatureUnavailable`` — the typed refusal a capability raises, or that the
  server synthesises from a database error it recognises as schema drift. It
  carries a stable ``code``, an operator-safe ``message``, whether a retry
  might plausibly succeed, and the ``feature`` it names. ``server.py`` turns
  it into the wire envelope, adding the build and schema identity every
  response already knows and a short diagnostic ``ref`` it also logs.

* ``REQUIREMENTS`` / :func:`preflight` — a per-feature declaration of the
  migration level, tables and PostgreSQL extensions a capability needs,
  checked *before* the capability runs so the failure names the missing
  piece instead of surfacing as a ``no such column`` from three joins deep.

The wire shape, built in ``server.py``:

    {
      "error": "<human message>",              # unchanged: portal + tests read this
      "error_detail": {                         # additive (BETA-068)
        "code": "missing_migration",
        "message": "<human message>",
        "retryable": false,
        "feature": "document_search",
        "build": {"revision": "...", "build_time": "..."},
        "schema": {"latest_migration": 71, "applied_count": 71},
        "ref": "a1b2c3d4"
      }
    }

Nothing here computes a figure or reads evidence: it inspects the schema
catalogue only.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .. import catalog, db
from . import health

__all__ = [
    "FeatureUnavailable",
    "REQUIREMENTS",
    "preflight",
    "classify_db_error",
    "max_applied_migration",
]


class FeatureUnavailable(Exception):
    """One capability cannot be served on this build.

    ``status`` defaults to 503 (the capability may come back once a migration
    is applied or a slow query is retried) but a genuinely absent extension
    with no fallback is still a 503, not a 500: the *service* is healthy, this
    *feature* is not.
    """

    def __init__(
        self,
        feature: str,
        message: str,
        *,
        code: str = "feature_unavailable",
        retryable: bool = False,
        status: int = 503,
    ) -> None:
        super().__init__(message)
        self.feature = feature
        self.message = message
        self.code = code
        self.retryable = retryable
        self.status = status


@dataclass(frozen=True)
class Requirement:
    """What a named feature needs before it can answer.

    ``min_migration`` is the numeric prefix of the earliest migration that
    must be applied (``71`` means ``0071_*`` or later). ``tables`` are object
    names that must exist in the catalogue — views count. ``extensions`` are
    PostgreSQL extension names that must be installed *in this database*;
    ignored on SQLite, where every such feature has a pure-Python fallback.
    """

    min_migration: int | None = None
    tables: tuple[str, ...] = ()
    extensions: tuple[str, ...] = ()
    label: str = ""


# The closed registry. A feature absent from here is not checked — preflight
# is opt-in, added to a route when that route has a schema dependency worth
# naming. Keep the keys aligned with the `feature` strings the portal shows.
REQUIREMENTS: dict[str, Requirement] = {
    "document_search": Requirement(
        min_migration=53,
        tables=("document_records", "document_elements", "evidence_records"),
        label="Document search",
    ),
    "run_ledger": Requirement(
        min_migration=73,
        tables=("run_ledger",),
        label="Run ledger",
    ),
    "hse_enforcement": Requirement(
        min_migration=72,
        tables=("hse_enforcement_notices",),
        label="HSE enforcement notices",
    ),
    "cqc_locations": Requirement(
        min_migration=10,
        tables=("cqc_locations",),
        label="CQC regulated-location explorer",
    ),
    "archive_audits": Requirement(
        min_migration=74,
        tables=("archive_audits",),
        label="Raw-archive integrity trends",
    ),
    "temporary_accommodation": Requirement(
        min_migration=77,
        tables=("temporary_accommodation_breakdowns",),
        label="Temporary-accommodation breakdown",
    ),
    "semantic_search": Requirement(
        min_migration=65,
        tables=("document_chunks", "document_embeddings"),
        extensions=("vector",),
        label="Semantic search",
    ),
    "assistant_runs": Requirement(
        min_migration=79,
        tables=("assistant_runs",),
        label="Assistant run ledger",
    ),
}


_NUM = re.compile(r"^(\d+)")


def max_applied_migration(applied: set[str]) -> int:
    """Highest numeric prefix among applied migration filenames, or 0.

    ``db.applied_migrations`` returns filenames (``0071_document_embeddings_vector.sql``);
    the prefix is the ordering key the runner already applies them in.
    """

    best = 0
    for name in applied:
        m = _NUM.match(name)
        if m:
            best = max(best, int(m.group(1)))
    return best


def preflight(conn, feature: str) -> None:
    """Raise :class:`FeatureUnavailable` if ``feature``'s schema needs are unmet.

    Cheap on purpose — one catalogue read, one migrations read, and (only on
    PostgreSQL) one `pg_available_extensions` read. Called at the top of a
    route handler so a missing migration is reported as
    ``{code: "missing_migration"}`` rather than as whatever the first broken
    query happens to raise.
    """

    req = REQUIREMENTS.get(feature)
    if req is None:
        return

    if req.min_migration is not None:
        applied = db.applied_migrations(conn)
        level = max_applied_migration(applied)
        if level < req.min_migration:
            raise FeatureUnavailable(
                feature,
                f"{req.label or feature} needs schema revision "
                f"{req.min_migration:04d} or later; this build is at "
                f"{level:04d}. Apply the pending migrations and retry.",
                code="missing_migration",
                retryable=False,
            )

    if req.tables:
        present = {obj["name"] for obj in catalog.list_objects(conn)}
        missing = [t for t in req.tables if t not in present]
        if missing:
            raise FeatureUnavailable(
                feature,
                f"{req.label or feature} is not available on this build: "
                f"the {', '.join(missing)} "
                f"{'table is' if len(missing) == 1 else 'tables are'} absent.",
                code="missing_table",
                retryable=False,
            )

    if req.extensions and db.backend_of(conn) == "postgres":
        installed = {
            ext["name"] for ext in health.extensions(conn) if ext["installed"]
        }
        missing = [e for e in req.extensions if e not in installed]
        if missing:
            raise FeatureUnavailable(
                feature,
                f"{req.label or feature} needs the "
                f"{', '.join(missing)} PostgreSQL "
                f"{'extension' if len(missing) == 1 else 'extensions'}, "
                f"which this database does not have installed.",
                code="missing_extension",
                retryable=False,
            )


# --- recognising schema drift in a raw database error ----------------------

# SQLite phrases these as OperationalError; psycopg raises distinct classes
# whose names we match textually to avoid importing psycopg here (it is an
# optional dependency on the SQLite-only checkout).
_DRIFT_SQLITE = re.compile(
    r"no such (table|column|module|view|function)\b", re.I
)
_DRIFT_PG_CLASSES = {
    "UndefinedTable": ("missing_table", False),
    "UndefinedColumn": ("missing_table", False),
    "UndefinedObject": ("missing_extension", False),
    "UndefinedFunction": ("missing_extension", False),
    "InsufficientPrivilege": ("insufficient_privilege", False),
    "InvalidSchemaName": ("missing_table", False),
    "QueryCanceled": ("timeout", True),
    "OperationalError": ("database_error", True),
}


def classify_db_error(exc: BaseException, feature: str = "unknown") -> FeatureUnavailable | None:
    """Map a raw database error onto a :class:`FeatureUnavailable`, or ``None``.

    The catch-all in ``server.py`` runs this before falling back to a 500. A
    schema-drift error becomes a bounded unavailable state naming ``feature``
    (``"unknown"`` when the route did not preflight); anything unrecognised
    returns ``None`` and the 500 path stands.
    """

    name = type(exc).__name__
    text = str(exc)

    if isinstance(exc, sqlite3.OperationalError):
        if "interrupted" in text or "timeout" in text.lower():
            return FeatureUnavailable(
                feature,
                "This section took too long to build and was stopped. Try again.",
                code="timeout",
                retryable=True,
            )
        if _DRIFT_SQLITE.search(text):
            return FeatureUnavailable(
                feature,
                "This section depends on a database object this build does "
                "not have. It is unavailable until the schema is updated.",
                code="missing_table",
                retryable=False,
            )
        return None

    hit = _DRIFT_PG_CLASSES.get(name)
    # psycopg wraps the SQLSTATE class name in the exception's own name for
    # the errors above; for the generic OperationalError only treat it as
    # drift when the text points at a cancelled statement.
    if hit is None:
        return None
    if name == "OperationalError" and "canceling statement" not in text:
        return None
    code, retryable = hit
    human = {
        "missing_table": "This section depends on a database object this "
                         "build does not have. It is unavailable until the "
                         "schema is updated.",
        "missing_extension": "This section needs a PostgreSQL extension this "
                             "database does not have installed.",
        "insufficient_privilege": "This section could not be read with the "
                                  "current database permissions.",
        "timeout": "This section took too long to build and was stopped. "
                   "Try again.",
        "database_error": "This section could not be read from the database. "
                          "Try again.",
    }[code]
    return FeatureUnavailable(feature, human, code=code, retryable=retryable)
