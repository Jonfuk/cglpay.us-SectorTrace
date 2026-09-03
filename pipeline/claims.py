"""The claims-to-evidence index (Workstream C, Phase 17).

A claim is a statement the campaign makes, and this is where the statement,
what supports it and who decided it are recorded. The difference between a
data portal and an evidence portfolio: claims as rows, each linked to the
verified evidence rows supporting it, with the caveats that travel with it.

Three rules hold here, and they are the phase plan's own:

  * **Nothing is computed.** A claim is a statement linked to rows, and the
    linkage is a human judgement recorded like every other decision in this
    warehouse. There is no derived figure here: the claim's text is what a
    person wrote, the citations are rows a person picked, and the caveats are
    lines a person wrote about what may not be computed from it.

  * **A claim without a recorded reviewer and decision history is not a
    claim** — the same standard migration 0030 sets for promotion, enforced
    structurally by migration 0048. `decide()` writes the verification row
    first and then moves the claim's status, the same ordering promote() and
    census_verify() use: the audit trail is not something the caller is
    trusted to remember afterwards.

  * **A citation must resolve.** The portal renders every citation, and a
    link to a row that is no longer there is worse than no link. `cite()`
    refuses a key that resolves to nothing — the same refusal promote()
    makes for a document that does not answer.

The lifecycle a claim moves through is the review-and-decide workflow the
rest of the operator UI uses, with the same named-person discipline: a claim
is written as a draft, and every later status ('published', 'rejected',
'retracted') is a decision recorded against the person who took it. Rejected
and retracted claims stay in the warehouse with their decision history — the
judgement was still taken, and the portal only ever renders 'published' ones.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import structlog

from pipeline import db

log = structlog.get_logger()

STATUSES = ("draft", "published", "rejected", "retracted")
DECISIONS = ("published", "rejected", "retracted")

# A claim's caveats column is one line per caveat, newline-separated. The
# portal renders each line as its own pinned caveat, so a claim that forbids
# two computations carries two lines, and an empty column carries none.
CAVEAT_SEPARATOR = "\n"

MAX_TEXT_LENGTH = 5000
MAX_CAVEATS_LENGTH = 2000
MAX_NOTE_LENGTH = 2000


class ClaimError(RuntimeError):
    """A claim that cannot be written or decided, and why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- the citation registry ----------------------------------------------------
#
# Which evidence tables a claim may cite, and how each one is resolved back to
# something the portal can render. The same shape promote.py's KINDS has:
# adding a citable table is filling in an entry here, and a citation whose
# table is not in this registry is refused at the door — a claim must never
# rest on rows the portal cannot show its reader.
#
# Each entry declares:
#   * `label` — the table's name for the admin picker.
#   * `key_columns` — the columns that identify a row, in key order.
#   * `search_columns` — the columns the admin picker searches with LIKE.
#   * `resolve(conn, parts)` — the row a key names, as a display payload:
#     {label, url, source_url, retrieved_at} or None. `parts` is the key
#     split on the key separator, in `key_columns` order.

# The same unit separator census_verify.metric_key uses between key parts, so
# a document URL or a census raw_text line containing it cannot forge a key.
KEY_SEPARATOR = "\x1f"


def _resolve_document(conn: sqlite3.Connection, table: str, columns: dict,
                      parts: list[str]):
    """Shared resolver for the three promoted-document tables.

    The natural key is the same "<authority>|<url>" pair evidence_promotions
    uses, which is not an accident: a claim cites the row, and the row's
    identity in the promotion ledger is the same key.
    """
    authority_col, url_col = columns["authority"], columns["url"]
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {authority_col} = %s AND {url_col} = %s",
        parts[:2]).fetchone()
    if row is None:
        return None
    row = dict(row)
    return {
        "label": (row.get("title") or row.get("report_title")
                  or row.get("subject") or row[url_col]),
        "url": row[url_col],
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
    }


def _census_metrics_by_key(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every verified census metric by its key, collisions refused.

    The same full-scan machinery census_verify uses; the table is a few dozen
    rows per round, so an index on a stored digest would be a second source
    of truth bought for nothing.
    """
    from pipeline.census_verify import metric_key

    out: dict[str, dict] = {}
    for row in conn.execute(
            "SELECT * FROM workforce_census_metrics WHERE verified = 1"):
        record = dict(row)
        key = metric_key(record)
        if key in out:
            raise ClaimError(
                f"two census metrics share the key {key}. A citation would "
                "be ambiguous; nothing has been written.")
        out[key] = record
    return out


def _census_key_builder(row: dict) -> str:
    from pipeline.census_verify import metric_key

    return metric_key(row)


def _resolve_census_metric(conn: sqlite3.Connection,
                           parts: list[str]) -> dict | None:
    from pipeline.census_verify import metric_key

    wanted = (parts or [None])[0]
    if not wanted:
        return None
    for record in _census_metrics_by_key(conn).values():
        if metric_key(record) == wanted:
            value = record.get("value")
            unit = record.get("unit")
            shown = (f"{value}{'%' if unit == 'percent' else ' ' + (unit or '')}"
                     if value is not None else record.get("raw_text", "—"))
            return {
                "label": (f"{record['metric']}/{record['workforce_segment']} "
                          f"= {shown}".rstrip()),
                "url": record.get("source_url"),
                "source_url": record.get("source_url"),
                "retrieved_at": record.get("retrieved_at"),
            }
    return None


def _resolve_pay_row(conn: sqlite3.Connection, table: str, columns: dict,
                     parts: list[str]) -> dict | None:
    """A module-collected row with a simple natural key.

    Shared by the pay evidence tables: the key columns are declared per table,
    and the display payload is the row's own provenance, which is what makes
    the citation citable.
    """
    where = []
    params: list = []
    for column in (columns["key1"], columns.get("key2"), columns.get("key3")):
        if column is None:
            continue
        where.append(f"{column} = %s")
        params.append(parts[len(params)])
    if len(params) != len(where) or not where:
        return None
    row = conn.execute(f"SELECT * FROM {table} "
                       f"WHERE {' AND '.join(where)} LIMIT 1", params).fetchone()
    if row is None:
        return None
    row = dict(row)
    return {
        "label": _pay_label(table, row),
        "url": (row.get("written_statement_url") or row.get("advert_url")
                or row.get("source_url")),
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
    }


def _resolve_ashe(conn: sqlite3.Connection, parts: list[str]) -> dict | None:
    row = conn.execute(
        "SELECT * FROM ons_ashe_observations WHERE dataset_id = %s "
        "AND dimension_kind = %s AND dimension_code = %s AND geography_code = %s "
        "AND time = %s LIMIT 1", parts[:5]).fetchone()
    if row is None:
        return None
    row = dict(row)
    value = row["value_text"] if row["value_text"] is not None else "—"
    return {
        "label": f"{row['dimension_label']}, {row['geography_label']} "
                 f"({row['time']}): {value}",
        "url": row["source_url"],
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
    }


def _pay_label(table: str, row: dict) -> str:
    if table == "statutory_pay_rates":
        amount = row.get("value_text") or "—"
        return f"{row['period_label']} — {row['band_label']}: £{amount}"
    if table == "nhs_job_adverts":
        title = row.get("job_title") or "job advert"
        salary = row.get("salary_raw") or "salary not stated"
        return f"{title} ({salary})"
    if table == "provider_pay_mentions":
        text = row.get("mention_text") or ""
        return f"{row['provider_key']}: {text[:120]}"
    # gender_pay_gap_reports
    name = row.get("employer_name") or row.get("current_name") or row["provider_key"]
    gap = row.get("diff_mean_hourly_percent")
    gap_text = f"{gap:g}%" if gap is not None else "gap not filed"
    return f"{name} ({row['reporting_year_label']}): mean hourly {gap_text}"


# Registry: table -> spec. Table and column names are module constants, never
# request input, so interpolating them is the same trust as every other
# interpolated identifier in this codebase.
CITABLE: dict[str, dict] = {
    "cdp_documents": {
        "label": "Council / CDP strategy documents (promoted)",
        "key_columns": ("authority_ons_code", "document_url"),
        "search_columns": ("title", "document_type"),
        "resolve": lambda conn, parts: _resolve_document(
            conn, "cdp_documents",
            {"authority": "authority_ons_code", "url": "document_url"}, parts),
    },
    "committee_papers": {
        "label": "Committee papers (promoted)",
        "key_columns": ("authority_ons_code", "document_url"),
        "search_columns": ("report_title", "agenda_item_title"),
        "resolve": lambda conn, parts: _resolve_document(
            conn, "committee_papers",
            {"authority": "authority_ons_code", "url": "document_url"}, parts),
    },
    "foi_requests": {
        "label": "FOI requests (promoted)",
        "key_columns": ("ons_code", "request_url"),
        "search_columns": ("subject",),
        "resolve": lambda conn, parts: _resolve_document(
            conn, "foi_requests",
            {"authority": "ons_code", "url": "request_url"}, parts),
    },
    "workforce_census_metrics": {
        "label": "Workforce census metrics (verified)",
        # The citation key is the metric's own digest — see
        # census_verify.metric_key — which exists because this table's
        # natural key includes a whole line of PDF prose. Only verified
        # figures are citable: a claim must not rest on a parse nobody has
        # checked.
        "key_columns": ("metric_key",),
        "search_columns": ("metric", "workforce_segment"),
        "key_builder": _census_key_builder,
        "resolve": _resolve_census_metric,
    },
    "statutory_pay_rates": {
        "label": "Statutory pay rates (Module 17)",
        "key_columns": ("period_label", "band_label"),
        "search_columns": ("period_label", "band_label"),
        "resolve": lambda conn, parts: _resolve_pay_row(
            conn, "statutory_pay_rates",
            {"key1": "period_label", "key2": "band_label"}, parts),
    },
    "ons_ashe_observations": {
        "label": "ONS ASHE earnings observations (Module 21)",
        "key_columns": ("dataset_id", "dimension_kind", "dimension_code",
                         "geography_code", "time"),
        "search_columns": ("dimension_label", "geography_label"),
        "resolve": lambda conn, parts: _resolve_ashe(conn, parts),
    },
    "nhs_job_adverts": {
        "label": "NHS Jobs adverts (Module 16)",
        "key_columns": ("job_reference",),
        "search_columns": ("job_title", "employer_name_raw"),
        "resolve": lambda conn, parts: _resolve_pay_row(
            conn, "nhs_job_adverts",
            {"key1": "job_reference", "key2": None}, parts),
    },
    "provider_pay_mentions": {
        "label": "Provider pay pages — mentions (Module 22)",
        "key_columns": ("page_url", "mention_index"),
        "search_columns": ("mention_text", "provider_key"),
        "resolve": lambda conn, parts: _resolve_pay_row(
            conn, "provider_pay_mentions",
            {"key1": "page_url", "key2": "mention_index"}, parts),
    },
    "gender_pay_gap_reports": {
        "label": "Gender pay gap filings (Module 20)",
        "key_columns": ("provider_key", "reporting_year", "employer_id"),
        "search_columns": ("employer_name", "current_name"),
        "resolve": lambda conn, parts: _resolve_pay_row(
            conn, "gender_pay_gap_reports",
            {"key1": "provider_key", "key2": "reporting_year", "key3": "employer_id"},
            parts),
    },
}


def citable_tables() -> list[str]:
    """What a claim may cite, for the admin picker to build itself from."""
    return sorted(CITABLE)


def _split_key(key: str) -> list[str]:
    return (key or "").split(KEY_SEPARATOR)



def resolve_citation(conn: sqlite3.Connection, table: str,
                     key: str) -> dict | None:
    """The row a citation names, as the portal renders it, or None.

    None is the honest half: a module re-run can replace the row a citation
    names, and the portal says "no longer in the warehouse" rather than
    guessing at what the claim cited. Same shape census_verify.stale() gives
    a verification whose source moved.
    """
    spec = CITABLE.get(table)
    if spec is None:
        return None
    parts = _split_key(key)
    if len(parts) != len(spec["key_columns"]):
        return None
    try:
        return spec["resolve"](conn, parts)
    except ClaimError:
        raise
    except Exception:  # pragma: no cover - a resolver bug is a bug, not a guess
        log.exception("claims.citation_resolution_failed", table=table)
        return None


def search_citable(conn: sqlite3.Connection, table: str, term: str,
                   limit: int = 20) -> list[dict]:
    """Rows a reviewer might cite: the picker behind the Citations box.

    Searches the table's declared search columns for `term`, and returns the
    first `limit` rows as {key, label, url} candidates. A citation built from
    one of these keys is guaranteed to resolve now; `cite()` still re-checks
    when it is written, because the warehouse can move between the search and
    the click.
    """
    spec = CITABLE.get(table)
    if spec is None:
        raise ClaimError(
            f"{table!r} is not a citable evidence table. One of: "
            f"{', '.join(citable_tables())}.")
    term = (term or "").strip()
    if not term:
        return []

    searches = " OR ".join(f"{column} LIKE %s" for column in spec["search_columns"])
    params = [f"%{term}%"] * len(spec["search_columns"])
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE ({searches}) "
        f"ORDER BY {spec['search_columns'][0]} LIMIT %s",
        [*params, max(1, min(int(limit), 50))]).fetchall()

    out = []
    for row in rows:
        record = dict(row)
        builder = spec.get("key_builder")
        key = (builder(record) if builder
               else build_key(record, spec["key_columns"]))
        resolved = spec["resolve"](conn, _split_key(key))
        if resolved is None:
            continue
        out.append({"key": key, "label": resolved["label"],
                    "url": resolved["url"]})
    return out


def build_key(row: dict, key_columns: tuple[str, ...]) -> str:
    """The citation key for a row, in the table's declared column order."""
    return KEY_SEPARATOR.join(str(row[column]) for column in key_columns)


# --- writing a claim ----------------------------------------------------------


def create(conn: sqlite3.Connection, claim_text: str, created_by: str,
           caveats: str = "", note: str | None = None) -> dict:
    """Write a draft claim. Nothing else: a claim is born a draft, and every
    later status is a decision (migration 0048's INSERT trigger says so)."""
    claim_text = (claim_text or "").strip()
    if not claim_text:
        raise ClaimError("A claim needs its text — there is nothing to "
                         "review without the statement itself.")
    if len(claim_text) > MAX_TEXT_LENGTH:
        raise ClaimError(f"Claim text is too long ({MAX_TEXT_LENGTH} "
                         "characters maximum).")
    if not (created_by or "").strip():
        raise ClaimError("claims are attributed. Say who wrote this one.")
    caveats = (caveats or "").strip()
    if len(caveats) > MAX_CAVEATS_LENGTH:
        raise ClaimError(f"Caveats are too long ({MAX_CAVEATS_LENGTH} "
                         "characters maximum).")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ClaimError(f"Note is too long ({MAX_NOTE_LENGTH} characters "
                         "maximum).")

    now = _now()
    # RETURNING, not cursor.lastrowid -- the latter is a sqlite3-ism and is
    # absent on the psycopg cursor the PostgreSQL wrapper hands back.
    claim_id = int(conn.execute(
        "INSERT INTO claims (claim_text, status, caveats, created_by, "
        "created_at, note) VALUES (%s, 'draft', %s, %s, %s, %s) RETURNING id",
        (claim_text, caveats, created_by.strip(), now, note)).fetchone()["id"])
    conn.commit()
    log.info("claims.created", claim_id=claim_id, by=created_by.strip())
    return get(conn, claim_id)


def get(conn: sqlite3.Connection, claim_id: int) -> dict:
    """One claim with its citations and decisions, for the UI and the portal."""
    row = conn.execute(
        "SELECT * FROM claims WHERE id = %s", (int(claim_id),)).fetchone()
    if row is None:
        raise ClaimError(f"No claim {claim_id}.")
    return _claim_payload(conn, dict(row))


def _claim_payload(conn: sqlite3.Connection, claim: dict) -> dict:
    citations = [dict(row) for row in conn.execute(
        "SELECT * FROM claim_citations WHERE claim_id = %s ORDER BY id",
        (claim["id"],))]
    decisions = [dict(row) for row in conn.execute(
        "SELECT id, claim_id, decision, decided_by, decided_at, note "
        "FROM claim_verifications WHERE claim_id = %s ORDER BY id",
        (claim["id"],))]
    return {
        "id": claim["id"],
        "claim_text": claim["claim_text"],
        "status": claim["status"],
        "caveats": claim["caveats"],
        "created_by": claim["created_by"],
        "created_at": claim["created_at"],
        "note": claim["note"],
        "citations": citations,
        "decisions": decisions,
    }


def update_text(conn: sqlite3.Connection, claim_id: int, claim_text: str,
                caveats: str = "", note: str | None = None) -> dict:
    """Edit a draft claim's text, caveats and note.

    A decided claim is not editable: its status is the decision, and the text
    underneath it is what was reviewed. Reset it first if it needs revising —
    the decisions stay on record, the same rule census_verify.reset follows.
    """
    claim = get(conn, claim_id)
    if claim["status"] != "draft":
        raise ClaimError(
            f"This claim is {claim['status']}, which means it was reviewed. "
            "Reset it before editing — the decisions stay on record.")
    claim_text = (claim_text or "").strip()
    if not claim_text:
        raise ClaimError("A claim needs its text — there is nothing to "
                         "review without the statement itself.")
    if len(claim_text) > MAX_TEXT_LENGTH:
        raise ClaimError(f"Claim text is too long ({MAX_TEXT_LENGTH} "
                         "characters maximum).")
    caveats = (caveats or "").strip()
    if len(caveats) > MAX_CAVEATS_LENGTH:
        raise ClaimError(f"Caveats are too long ({MAX_CAVEATS_LENGTH} "
                         "characters maximum).")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ClaimError(f"Note is too long ({MAX_NOTE_LENGTH} characters "
                         "maximum).")
    conn.execute("UPDATE claims SET claim_text = %s, caveats = %s, note = %s "
                 "WHERE id = %s", (claim_text, caveats, note, claim_id))
    conn.commit()
    log.info("claims.edited", claim_id=claim_id)
    return get(conn, claim_id)


# --- citations ----------------------------------------------------------------


def cite(conn: sqlite3.Connection, claim_id: int, evidence_table: str,
         evidence_key: str, cited_by: str, note: str | None = None) -> dict:
    """Link a claim to one evidence row.

    The linkage is the judgement: who made it and when are columns here,
    never defaulted. The row must exist and be citable, and the claim must
    still be a draft — a decided claim's citations are part of what was
    reviewed.
    """
    claim = get(conn, claim_id)
    if claim["status"] != "draft":
        raise ClaimError(
            f"This claim is {claim['status']}, which means it was reviewed. "
            "Reset it before changing what supports it.")
    if not (cited_by or "").strip():
        raise ClaimError("citations are attributed. Say who is linking this "
                         "evidence to the claim.")
    spec = CITABLE.get(evidence_table)
    if spec is None:
        raise ClaimError(
            f"{evidence_table!r} is not a citable evidence table. One of: "
            f"{', '.join(citable_tables())}.")
    evidence_key = (evidence_key or "").strip()
    if not evidence_key:
        raise ClaimError("A citation needs the evidence row's key.")
    parts = _split_key(evidence_key)
    if len(parts) != len(spec["key_columns"]):
        raise ClaimError(
            f"{evidence_table} keys have {len(spec['key_columns'])} parts; "
            f"this citation has {len(parts)}.")
    if resolve_citation(conn, evidence_table, evidence_key) is None:
        raise ClaimError(
            f"No citable row {evidence_key!r} in {evidence_table}. Reload "
            "the picker — a module run can have replaced the row.")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ClaimError(f"Note is too long ({MAX_NOTE_LENGTH} characters "
                         "maximum.")

    now = _now()
    try:
        conn.execute(
            "INSERT INTO claim_citations (claim_id, evidence_table, "
            "evidence_key, cited_by, cited_at, note) VALUES (%s, %s, %s, %s, %s, %s)",
            (claim_id, evidence_table, evidence_key, cited_by.strip(), now, note))
        conn.commit()
    except db.IntegrityError:
        conn.rollback()
        raise ClaimError("That evidence row is already cited on this claim.")
    log.info("claims.cited", claim_id=claim_id, table=evidence_table, by=cited_by)
    return get(conn, claim_id)


def uncite(conn: sqlite3.Connection, claim_id: int, evidence_table: str,
           evidence_key: str) -> dict:
    """Remove one citation. Drafts only, the same rule `cite` follows."""
    claim = get(conn, claim_id)
    if claim["status"] != "draft":
        raise ClaimError(
            f"This claim is {claim['status']}, which means it was reviewed. "
            "Reset it before changing what supports it.")
    conn.execute(
        "DELETE FROM claim_citations WHERE claim_id = %s AND evidence_table = %s "
        "AND evidence_key = %s", (claim_id, evidence_table, evidence_key))
    conn.commit()
    log.info("claims.uncited", claim_id=claim_id, table=evidence_table)
    return get(conn, claim_id)


# --- deciding -----------------------------------------------------------------


def decide(conn: sqlite3.Connection, claim_id: int, decision: str,
           decided_by: str, note: str | None = None) -> dict:
    """Move a claim to a decided status, recording who did it first.

    The decision row is written before the status is moved, because the
    trigger on the status column looks for it — the same ordering 0030 and
    0033 use, and for the same reason: the audit trail is not something the
    caller is trusted to remember afterwards.

    The transition must make sense: only a draft can be published or
    rejected, and only a published claim can be retracted. The status column
    only moves when a decision row authorises the move.
    """
    if decision not in DECISIONS:
        raise ClaimError(
            f"Unknown decision {decision!r}. Use one of: {', '.join(DECISIONS)}.")
    if not (decided_by or "").strip():
        raise ClaimError("decisions are attributed. Say who is deciding this.")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ClaimError(f"Note is too long ({MAX_NOTE_LENGTH} characters "
                         "maximum.")

    claim = get(conn, claim_id)
    allowed = {
        "published": ("draft",),
        "rejected": ("draft",),
        "retracted": ("published",),
    }[decision]
    if claim["status"] not in allowed:
        raise ClaimError(
            f"A {claim['status']} claim cannot be {decision}. "
            + ("Only a draft can be decided." if claim["status"] == "draft"
               else "Reset it first if it needs revising."))

    now = _now()
    try:
        conn.execute(
            "INSERT INTO claim_verifications (claim_id, decision, decided_by, "
            "decided_at, note) VALUES (%s, %s, %s, %s, %s)",
            (claim_id, decision, decided_by.strip(), now, note))
        conn.execute(
            "UPDATE claims SET status = %s WHERE id = %s", (decision, claim_id))
        conn.commit()
    except db.IntegrityError:
        conn.rollback()
        raise
    log.info("claims.decided", claim_id=claim_id, decision=decision,
              by=decided_by.strip())
    return get(conn, claim_id)


def reset(conn: sqlite3.Connection, claim_id: int) -> dict:
    """Back to draft. The decision rows stay.

    The same rule promote.reset and census_verify.reset follow: a judgement
    that was taken was still taken, and deleting the record of it to tidy the
    status is how "who said this?" stops having an answer.
    """
    claim = get(conn, claim_id)
    if claim["status"] == "draft":
        raise ClaimError("This claim is already a draft.")
    conn.execute("UPDATE claims SET status = 'draft' WHERE id = %s", (claim_id,))
    conn.commit()
    log.info("claims.reset", claim_id=claim_id)
    return get(conn, claim_id)


# --- listing ------------------------------------------------------------------


def listing(conn: sqlite3.Connection, status: str = "all", offset: int = 0,
            limit: int = 50) -> dict:
    """One page of claims for the worklist, newest first."""
    if status not in ("all", *STATUSES):
        raise ClaimError(
            f"unknown status {status!r}; expected "
            f"{', '.join(STATUSES)} or all.")
    where, params = "", []
    if status != "all":
        where, params = " WHERE status = %s", [status]
    total = conn.execute(f"SELECT COUNT(*) AS total FROM claims{where}",
                          params).fetchone()["total"]
    limit = max(1, min(int(limit), 100))
    rows = conn.execute(
        f"SELECT id FROM claims{where} ORDER BY id DESC LIMIT %s OFFSET %s",
        [*params, limit, max(0, int(offset))])
    items = [get(conn, row["id"]) for row in rows]
    return {"status": status, "total": total, "offset": offset,
             "limit": limit, "items": items}


def counts(conn: sqlite3.Connection) -> dict:
    """How many claims are in each state.

    The number this exists to move is `draft`: claims written and not yet
    decided, which is where the review-and-decide workflow starts.
    """
    out = {status: 0 for status in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM claims "
                             "GROUP BY status"):
        out[row["status"]] = row["n"]
    return {
        **out,
        "total": sum(out.values()),
        "decisions": history(conn, limit=10),
    }


def history(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Recent claim decisions, with who made them — the audit trail."""
    rows = conn.execute(
        "SELECT v.id, v.claim_id, v.decision, v.decided_by, v.decided_at, "
        "       v.note, c.claim_text AS claim_text "
        "FROM claim_verifications v "
        "LEFT JOIN claims c ON c.id = v.claim_id "
        "ORDER BY v.id DESC LIMIT %s", (max(1, int(limit)),)).fetchall()
    return [dict(row) for row in rows]
