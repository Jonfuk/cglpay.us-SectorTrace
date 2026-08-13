"""Turning a candidate into evidence, once a person has decided it is.

Three modules discover candidates and none of them promotes one. That is
deliberate and it stays: `confidence` counts matching signals and
`match_quality` is ModernGov's own textual ranking, so neither is a judgement
that a document is what its link text claims. An "excellent match" for
`public health grant` is frequently a COVID grant report.

What was missing is the other half — a way for the person who *has* looked to
say so, that leaves a record. Without it the only route across was hand-written
SQL, and 1,941 candidates sat outside the evidence base.

Three rules hold here, and the first is the one that shapes the code:

  * **The evidence row's provenance is a fetch of the document.** A
    candidate's `payload_sha256` is the hash of the *listing page the link was
    found on*. Copying it onto an evidence row would claim the document had
    been retrieved when it had not. So promoting fetches the document, through
    the same client the modules use — robots respected, rate limit shared,
    bytes archived — and the evidence row carries that fetch.

  * **A document that does not answer is not promoted.** The same rule the URL
    resolver already applies. A dead link stored as evidence is worse than a
    candidate: it looks citable and is not.

  * **The promotion is recorded before the evidence exists**, and a database
    trigger refuses the evidence row without it (migration 0030). The audit
    trail is not something the caller is trusted to remember.

Promotion is per row and per person. There is no bulk promote, and that is a
decision rather than an omission: the point of the act is that somebody opened
the document. Bulk *rejection* is fine and cheap — see `reject()`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import structlog

from pipeline import db
from pipeline.config import Settings, get_settings
from pipeline.http import PipelineHTTPClient, RobotsDisallowed

log = structlog.get_logger()


class PromotionError(RuntimeError):
    """A candidate that cannot be promoted, and why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Everything that differs between the three kinds, in one place. Adding a
# fourth candidate type is filling in a row here, not writing a fourth
# promotion path with its own subtly different audit behaviour.
KINDS: dict[str, dict] = {
    "cdp_document": {
        "candidate_table": "cdp_document_candidates",
        "target_table": "cdp_documents",
        "authority_column": "authority_ons_code",
        "candidate_url_column": "candidate_url",
        "target_url_column": "document_url",
        "source_system": "cdp_document_promotion",
        # document_type is NOT NULL on the target and the candidate only has a
        # guess. The reviewer confirms it; the schema comment says "confirmed,
        # not guessed" and this is what makes that true.
        "requires": ("document_type",),
        "title_column": "title",
    },
    "committee_paper": {
        "candidate_table": "committee_paper_candidates",
        "target_table": "committee_papers",
        "authority_column": "authority_ons_code",
        "candidate_url_column": "document_url",
        "target_url_column": "document_url",
        "source_system": "committee_paper_promotion",
        "requires": (),
        "title_column": "report_title",
    },
    "foi_request": {
        "candidate_table": "foi_request_candidates",
        "target_table": "foi_requests",
        "authority_column": "ons_code",
        "candidate_url_column": "candidate_url",
        "target_url_column": "request_url",
        "source_system": "foi_request_promotion",
        "requires": (),
        "title_column": "title",
    },
}


def kinds() -> dict[str, dict]:
    """What can be promoted, for the UI to build itself from."""
    return {name: {"candidate_table": spec["candidate_table"],
                    "target_table": spec["target_table"],
                    "requires": list(spec["requires"])}
             for name, spec in KINDS.items()}


def _spec(kind: str) -> dict:
    if kind not in KINDS:
        raise PromotionError(
            f"unknown candidate kind {kind!r}; expected one of "
            f"{', '.join(sorted(KINDS))}.")
    return KINDS[kind]


def candidate(conn: sqlite3.Connection, kind: str, url: str) -> dict | None:
    spec = _spec(kind)
    row = conn.execute(
        f"SELECT * FROM {spec['candidate_table']} "
        f"WHERE {spec['candidate_url_column']} = ?", (url,)).fetchone()
    return dict(row) if row else None


def promoted_urls(conn: sqlite3.Connection, kind: str) -> set[str]:
    """Candidates already promoted, so a list can say so."""
    spec = _spec(kind)
    return {row[0] for row in conn.execute(
        "SELECT candidate_url FROM evidence_promotions WHERE candidate_table = ?",
        (spec["candidate_table"],))}


def _fetch_document(url: str, spec: dict, settings: Settings,
                     conn: sqlite3.Connection, resolver=None):
    """The document itself, archived, or a refusal explaining which failure.

    Destination-guarded. The URL comes from a candidate table rather than
    straight off a form, but a candidate is a link this pipeline copied off a
    council's web page — so it is attacker-influenceable by anyone who can
    publish on a site m09 or m10 reads, and this is the request that turns one
    into a fetch from inside the operator's network.
    """
    from pipeline.netguard import BlockedAddress

    try:
        with PipelineHTTPClient(spec["source_system"], settings=settings,
                                 conn=conn, guard_destination=True,
                                 resolver=resolver) as client:
            result = client.get(url)
    except BlockedAddress as exc:
        raise PromotionError(str(exc)) from exc
    except RobotsDisallowed as exc:
        raise PromotionError(
            f"robots.txt refuses this document ({exc}). It is not promoted: "
            "the pipeline does not hold bytes it was asked not to fetch.") from exc
    except Exception as exc:
        raise PromotionError(f"could not fetch {url}: {exc}") from exc

    if not result.ok:
        raise PromotionError(
            f"{url} answered {result.status_code}. A dead link stored as "
            "evidence looks citable and is not, so it is refused rather than "
            "saved.")
    return result


def promote(conn: sqlite3.Connection, kind: str, url: str, promoted_by: str,
             fields: dict | None = None, note: str | None = None,
             settings: Settings | None = None, resolver=None) -> dict:
    """Promote one candidate. Fetches the document; writes two rows or none."""
    settings = settings or get_settings()
    spec = _spec(kind)
    fields = dict(fields or {})

    if not (promoted_by or "").strip():
        raise PromotionError(
            "promotions are attributed. Say who is promoting this.")

    found = candidate(conn, kind, url)
    if found is None:
        raise PromotionError(f"no {kind} candidate with url {url!r}.")
    if found.get("rejected"):
        raise PromotionError(
            f"{url} was rejected. Reset it before promoting it.")

    missing = [name for name in spec["requires"]
                if not (fields.get(name) or "").strip()]
    if missing:
        raise PromotionError(
            f"{', '.join(missing)} must be confirmed by the person promoting "
            "this — the candidate only carries a guess.")

    authority = found[spec["authority_column"]]
    if authority is None:
        raise PromotionError(
            f"{url} has no authority code, so it cannot join to anything.")

    # Fetched before either row is written. A failed fetch must leave nothing
    # behind, and this is also the slow part -- doing it inside the write
    # transaction would hold the warehouse's single write slot across a network
    # round trip, which is the mistake the run loop had to be fixed for.
    result = _fetch_document(url, spec, settings, conn, resolver)

    target_key = f"{authority}|{url}"
    promoted_at = _now()
    try:
        conn.execute(
            "INSERT INTO evidence_promotions "
            "(candidate_table, candidate_url, target_table, target_key, "
            " promoted_by, promoted_at, note, candidate_context_json, "
            " fetched_url, http_status, payload_sha256, archived_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (spec["candidate_table"], url, spec["target_table"], target_key,
             promoted_by.strip(), promoted_at, note,
             json.dumps(found, default=str), result.url, result.status_code,
             result.payload_sha256,
             str(result.archived_path) if result.archived_path else None))

        row = {
            spec["authority_column"]: authority,
            spec["target_url_column"]: url,
            "archived_path": str(result.archived_path) if result.archived_path else None,
            # Text extraction is not promotion's job. The bytes are archived
            # and hashed, which is what makes the row citable; m14 is where
            # reading documents lives.
            "source_url": result.url,
            "retrieved_at": result.retrieved_at.isoformat(),
            "http_status": result.status_code,
            "source_system": spec["source_system"],
            "payload_sha256": result.payload_sha256,
        }
        row.update(_target_fields(kind, found, fields))
        db.upsert(conn, spec["target_table"], row,
                   natural_key=[spec["authority_column"], spec["target_url_column"]])

        conn.execute(
            f"UPDATE {spec['candidate_table']} SET verified = 1, verified_at = ? "
            f"WHERE {spec['candidate_url_column']} = ?", (promoted_at, url))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("promote.promoted", kind=kind, url=url, by=promoted_by,
              target=spec["target_table"], sha256=result.payload_sha256)
    return {"kind": kind, "url": url, "target_table": spec["target_table"],
             "target_key": target_key, "promoted_by": promoted_by.strip(),
             "promoted_at": promoted_at, "payload_sha256": result.payload_sha256,
             "http_status": result.status_code}


def _target_fields(kind: str, found: dict, fields: dict) -> dict:
    """The columns that differ per kind, from the candidate and the reviewer.

    Candidate values are carried across where they describe the document
    (a committee name, a meeting date) and dropped where they describe the
    *search* that found it (`matched_terms`, `match_quality`, `confidence`):
    those are properties of the discovery, and the evidence table deliberately
    has nowhere to put them.
    """
    if kind == "cdp_document":
        return {"title": found.get("title"),
                 "document_type": fields["document_type"].strip(),
                 "published_date": (fields.get("published_date") or "").strip() or None}
    if kind == "committee_paper":
        return {"committee_name": found.get("committee_name"),
                 "meeting_date": found.get("meeting_date"),
                 "agenda_item_title": found.get("agenda_item_title"),
                 "report_title": found.get("report_title")}
    return {"subject": found.get("title"),
             "request_date": found.get("request_date"),
             "status": found.get("wdtk_status"),
             "topic": found.get("topic")}


def reject(conn: sqlite3.Connection, kind: str, urls: list[str],
            rejected_by: str, note: str | None = None) -> int:
    """Mark candidates as not evidence.

    Bulk, unlike promotion. Rejecting is a statement that a link is not what it
    looked like, which a person can reach from the listing — and the cost of
    being wrong is a candidate that stays a candidate.
    """
    _spec(kind)
    spec = KINDS[kind]
    if not (rejected_by or "").strip():
        raise PromotionError("rejections are attributed. Say who is rejecting.")
    if not urls:
        return 0

    marks = ", ".join("?" for _ in urls)
    cursor = conn.execute(
        f"UPDATE {spec['candidate_table']} SET rejected = 1, verified = 0 "
        f"WHERE {spec['candidate_url_column']} IN ({marks}) AND rejected = 0",
        urls)
    conn.commit()
    log.info("promote.rejected", kind=kind, count=cursor.rowcount,
              by=rejected_by, note=note)
    return cursor.rowcount


def reset(conn: sqlite3.Connection, kind: str, url: str) -> None:
    """Back to undecided. Does not remove evidence already promoted — that row
    has its own provenance and its own promotion record, and deleting evidence
    is not something this does quietly."""
    spec = _spec(kind)
    conn.execute(
        f"UPDATE {spec['candidate_table']} SET rejected = 0, verified = 0, "
        f"verified_at = NULL WHERE {spec['candidate_url_column']} = ?", (url,))
    conn.commit()


def history(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT id, candidate_table, candidate_url, target_table, promoted_by, "
        "       promoted_at, note, http_status, payload_sha256 "
        "FROM evidence_promotions ORDER BY id DESC LIMIT ?", (limit,))]
