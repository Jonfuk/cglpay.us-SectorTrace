"""Module 33 — HSE enforcement notices (Health and Safety Executive).

The public HSE Notices register lists improvement and prohibition notices
served under the Health and Safety at Work etc. Act 1974. It is
organisation-level attributed safety evidence: "HSE served an improvement
notice on <organisation> on <date>, regarding <contravention>". This module
collects those notices and keeps only the ones whose recipient name exactly
matches a tracked provider.

Three limits, and each is a caveat that travels with any figure built from
this (`docs/CAVEATS.md`):

  * **Individuals are excluded, at parse time.** The register also lists
    notices served on named people (directors, sole traders). A row whose
    recipient reads as a personal name and carries no organisation token, and
    does not exactly match a tracked provider, is dropped before anything is
    written. This module publishes organisation evidence only.
  * **Exact name match only, same discipline as Modules 4 and 18.** A notice
    is attributed to a provider (`provider_key` set) solely on an exact
    normalised match of the register's spelling against a tracked name
    variant. A near-miss is a `review_queue` item, never a stored
    attribution. `provider_key IS NULL` rows are collected but not published.
  * **A notice is not a settled outcome.** `result` is stored verbatim —
    "Complied", "Withdrawn", "Under appeal", "Appeal — notice affirmed /
    cancelled / modified". A notice can be appealed and cancelled after
    issue. This module never infers compliance, and the portal shows the
    published `result` beside every notice with the appeal/withdrawal caveat.

**Live-fetch path not yet validated against the real register.** The result
parser is written to HSE's documented notice-list structure and is exercised
by a representative fixture; the first real run should be watched by a
person, per the project's reduced-testing policy for a new source.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "hse_enforcement_notices"

# The register's organisation-name search. `EO=LIKE` / `SF=CN` is a
# contains-match on the company-name column; `SN=F` returns the full list.
SEARCH_URL = "https://resources.hse.gov.uk/notices/notices/notice_list.asp"


def _search_params(name: str) -> dict:
    return {"ST": "N", "SN": "F", "EO": "LIKE", "SF": "CN", "SV": name, "rdoName": "S"}


# Tokens that mark a recipient as an organisation rather than a person.
_ORG_TOKENS = re.compile(
    r"\b(ltd|limited|llp|plc|cic|c\.i\.c|inc|incorporated|company|co|"
    r"council|borough|county|district|nhs|trust|foundation|partnership|"
    r"group|holdings|services?|solutions?|care|housing|association|"
    r"charity|university|college|school|academy|hospital|clinic|centre|"
    r"authority|board|society|federation|network)\b",
    re.IGNORECASE)
_PERSONAL_PREFIX = re.compile(r"^\s*(mr|mrs|ms|miss|dr|prof|sir|dame|rev)\b\.?\s",
                              re.IGNORECASE)


def _normalise_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic|the)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_matches(register_name: str, tracked_variant: str) -> bool:
    """Exact normalised match of the register's spelling against a tracked
    name variant. Deterministic only — see the module docstring."""
    left = _normalise_name(register_name)
    return bool(left) and left == _normalise_name(tracked_variant)


def is_organisation(name: str, *, tracked_variants: set[str]) -> bool:
    """True if the recipient reads as an organisation. A recipient that
    exactly matches a tracked provider is always an organisation; otherwise
    it needs an org token and no personal-name prefix."""
    if any(name_matches(name, variant) for variant in tracked_variants):
        return True
    if _PERSONAL_PREFIX.search(name or ""):
        return False
    return bool(_ORG_TOKENS.search(name or ""))


class _NoticeListParser(HTMLParser):
    """One `<table>` of notice rows. Columns are read by their `<th>` header
    text (case-folded, spaces collapsed) rather than by position, so a
    reordering of the register's columns is a NULL, not a mis-stored value.
    """

    _HEADER_MAP = {
        "name": "recipient_name",
        "defendant": "recipient_name",
        "companyname": "recipient_name",
        "noticetype": "notice_type",
        "type": "notice_type",
        "noticenumber": "notice_number",
        "number": "notice_number",
        "issuingauthority": "issuing_body",
        "issuedby": "issuing_body",
        "dateofissue": "issue_date",
        "issuedate": "issue_date",
        "compliancedate": "compliance_date",
        "revisedcompliancedate": "revised_compliance_date",
        "result": "result",
        "status": "result",
        "industry": "industry",
        "mainactivity": "industry",
        "legislation": "legislation",
        "localauthority": "local_authority",
        "description": "contravention_text",
        "contravention": "contravention_text",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._headers: list[str] = []
        self._in_thead = False
        self._in_row = False
        self._in_cell = False
        self._is_header_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []
        self._detail_href: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
            self._detail_href = None
        elif tag in ("td", "th"):
            self._in_cell = True
            self._is_header_cell = tag == "th"
            self._cell_parts = []
        elif tag == "a" and self._in_cell and a.get("href"):
            self._detail_href = a["href"]

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_thead = False
        elif tag in ("td", "th"):
            text = re.sub(r"\s+", " ", "".join(self._cell_parts)).strip()
            if self._is_header_cell:
                key = re.sub(r"[^a-z]", "", text.lower())
                self._headers.append(self._HEADER_MAP.get(key, ""))
            else:
                self._row_cells.append(text)
            self._in_cell = False
        elif tag == "tr":
            self._in_row = False
            if self._row_cells and self._headers and not self._in_thead:
                row: dict = {}
                for header, value in zip(self._headers, self._row_cells):
                    if header and value:
                        row[header] = value
                if self._detail_href:
                    row["_detail_href"] = self._detail_href
                if row.get("notice_number"):
                    self.rows.append(row)


def parse_notice_list(html: str) -> list[dict]:
    parser = _NoticeListParser()
    parser.feed(html or "")
    return parser.rows


@register_module(
    "m33_hse_notices",
    supports_since=False,
    since_note="the register is a static list of served notices; a run "
               "collects every current match rather than a dated window",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m33_hse_notices"
    conn = ctx.conn

    written = 0
    attributed = 0
    dropped_individuals = 0
    near_misses = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for provider_key, variants in ctx.track(
                SUPPLIER_NAME_VARIANTS.items(), "providers"):
            tracked = set(variants)

            # Search under every name variant, then reconcile once: a notice
            # returned by more than one variant's search is one notice, and a
            # near-miss is judged against the whole variant set, not against
            # whichever search happened to return it.
            merged: dict[str, tuple[dict, object]] = {}
            for searched in variants:
                result = client.get(SEARCH_URL, params=_search_params(searched))
                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "hse_search_failed",
                        f"{provider_key} {searched}",
                        json.dumps({"status": result.status_code}))
                    continue
                for row in parse_notice_list(
                        result.body.decode("utf-8", "replace")):
                    merged.setdefault(row["notice_number"], (row, result))

            notice_rows: list[dict] = []
            for row, result in merged.values():
                recipient = row.get("recipient_name", "")
                if not is_organisation(recipient, tracked_variants=tracked):
                    dropped_individuals += 1
                    continue
                if not any(name_matches(recipient, v) for v in variants):
                    # A same-ish organisation name that is not an exact match
                    # to any tracked variant: a lead for a person, never a
                    # stored attribution (module docstring). One review item
                    # per notice, keyed so a re-run upserts rather than
                    # duplicates.
                    db.record_review_item(
                        conn, module_name, "hse_name_near_miss",
                        f"{provider_key} {row['notice_number']}",
                        json.dumps({"variants": list(variants),
                                    "register_name": recipient,
                                    "notice_number": row["notice_number"]}))
                    near_misses += 1
                    continue

                notice_rows.append({
                    "notice_number": row["notice_number"],
                    "recipient_name": recipient,
                    "provider_key": provider_key,
                    "notice_type": row.get("notice_type") or "unknown",
                    "issuing_body": row.get("issuing_body"),
                    "issue_date": row.get("issue_date"),
                    "compliance_date": row.get("compliance_date"),
                    "revised_compliance_date": row.get("revised_compliance_date"),
                    "result": row.get("result"),
                    "industry": row.get("industry"),
                    "legislation": row.get("legislation"),
                    "contravention_text": row.get("contravention_text"),
                    "local_authority": row.get("local_authority"),
                    "source_url": result.url,
                    "retrieved_at": result.retrieved_at.isoformat(),
                    "http_status": result.status_code,
                    "source_system": SOURCE_SYSTEM,
                    "payload_sha256": result.payload_sha256,
                })
                written += 1
                attributed += 1

            db.upsert_many(
                conn, "hse_enforcement_notices", notice_rows,
                natural_key=["notice_number"],
            )
            # One commit per provider — a unit of work — so the write slot is
            # released as each provider's notices land rather than held for
            # the whole run (CLAUDE.md settled decision 10).
            if not ctx.dry_run:
                conn.commit()

    log.info("m33.done", written=written, attributed=attributed,
             dropped_individuals=dropped_individuals, near_misses=near_misses)
