"""Module 14 — Provider annual report narrative.

Module 3 downloads each charity's filed accounts, which for these providers
are the annual report, and extracts the staff-costs note. This module reads
the narrative around that note: what the provider says about recruitment,
retention, restructuring, wellbeing, equality and its principal risks — the
material that never appears in statutory figures.

It re-reads the PDFs Module 3 already archived rather than fetching them
again, so it adds no traffic to the Charity Commission.

Two things it will not do:

  * Summarise. Passages are stored verbatim with their page number, exactly
    as PFD matters of concern are. The term index says where to look; a
    person decides what it means.

  * Claim an absence it cannot prove. The disclosure table records that no
    passage matched a topic's search terms, which is weaker than "the
    provider does not disclose this" — a figure in a table, or wording the
    terms do not cover, reads identically. The view carries that caveat on
    every row.

Worth knowing what the live data showed: CGL's 2025 annual report discusses
recruitment across nine pages and retention across six, and mentions
sickness absence, staff turnover and vacancy rates on none. That contrast is
the kind of thing this module exists to surface — as a prompt to look, not
as a finished finding.
"""
from __future__ import annotations

import json
import re

import structlog

from pipeline import db, pdftext, providers
from pipeline.archive import ArchiveError, get_archive
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "provider_annual_reports"

# The archive m03 wrote these PDFs into. The page-text cache is keyed by
# source system and payload hash, so m14 must look under m03's namespace
# to find what m03 already extracted.
M03_SOURCE_SYSTEM = "charity_commission_filed_accounts"

# Topic -> terms searched for.
#
# Terms are WORKFORCE-QUALIFIED, not bare words, because this is a health and
# social care charity and the same vocabulary describes service users and
# commercial activity. Live output from the first version made the cost of
# that obvious:
#
#   "sickness"  matched the charitable objects clause ("to relieve poverty
#               ... and sickness"), not staff absence at all
#   "retention" matched contract retentions — services won and kept — with
#               nothing to do with staff turnover
#
# Both produced confident, wrong topic labels. A false negative here shows up
# as a recorded gap that a human can check against the report; a false
# positive shows up as evidence that is not evidence, which is worse.
TOPICS: dict[str, list[str]] = {
    "recruitment": ["recruitment of staff", "staff recruitment", "recruiting staff",
                     "recruitment and retention", "hard to recruit", "recruitment challenges"],
    "retention": ["staff retention", "retention of staff", "employee retention",
                   "colleague retention", "recruitment and retention", "retaining staff"],
    "staff_turnover_rate": ["staff turnover", "turnover rate", "turnover of staff",
                             "attrition rate", "leaver rate"],
    "vacancy_rate": ["vacancy rate", "staff vacancies", "unfilled posts", "vacant posts",
                      "vacancies across"],
    "sickness_absence": ["sickness absence", "absence rate", "absenteeism",
                          "days lost", "staff absence"],
    "restructuring": ["restructur", "reorganisation of services", "redundan",
                       "service closure", "TUPE"],
    "pay_and_reward": ["pay award", "pay review", "real living wage", "living wage",
                        "pay scale", "reward strategy", "cost of living increase"],
    "employee_engagement": ["employee engagement", "staff engagement", "staff survey",
                             "colleague survey", "engagement survey"],
    "equality": ["gender pay", "ethnicity pay", "equality, diversity",
                  "diversity and inclusion", "equal opportunities"],
    "staff_wellbeing": ["staff wellbeing", "employee wellbeing", "colleague wellbeing",
                         "wellbeing of our staff", "wellbeing of our people", "burnout"],
    "principal_risks": ["principal risk", "strategic risk", "risk register", "key risks"],
    "executive_pay": ["key management personnel", "executive remuneration",
                       "highest paid", "senior pay", "chief executive pay"],
}

# How much of the page to keep around a match.
PASSAGE_CHARS = 700


def find_passages(page_text: str, page_number: int) -> list[dict]:
    """Topic matches on one page, each with a verbatim excerpt.

    One row per (topic, term) so the evidence trail records which wording
    actually appeared, not just that the topic did.
    """
    text = page_text or ""
    lowered = text.lower()
    found: list[dict] = []

    for topic, terms in TOPICS.items():
        for term in terms:
            index = lowered.find(term.lower())
            if index == -1:
                continue
            start = max(0, index - PASSAGE_CHARS // 3)
            excerpt = re.sub(r"\s+", " ", text[start:start + PASSAGE_CHARS]).strip()
            found.append({
                "topic": topic,
                "page_number": page_number,
                "matched_term": term,
                "passage_text": excerpt,
            })
            break  # first matching term per topic per page is enough
    return found


def summarise_disclosure(passages: list[dict]) -> dict[str, dict]:
    """Per topic: whether anything matched and on how many pages.

    Every configured topic appears, including the ones with no match — the
    absence is the point.
    """
    out: dict[str, dict] = {}
    for topic, terms in TOPICS.items():
        pages = {p["page_number"] for p in passages if p["topic"] == topic}
        out[topic] = {
            "matched": 1 if pages else 0,
            "pages_matched": len(pages),
            "search_terms": ", ".join(terms),
        }
    return out


def _provenance(row) -> dict:
    """Provenance is inherited from the Module 3 fetch that archived the PDF —
    this module reads a local copy and must not invent a new retrieval.
    """
    return {
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
        "http_status": row["http_status"],
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": row["payload_sha256"],
    }


def _archived_reports(conn) -> list:
    return conn.execute("""
        SELECT d.charity_number, d.financial_year_end, d.document_url, d.archived_path,
               d.page_count, d.source_url, d.retrieved_at, d.http_status, d.payload_sha256,
               i.provider_key
          FROM charity_accounts_documents d
          LEFT JOIN provider_identifiers i
                 ON i.scheme = 'charity_number' AND i.identifier = d.charity_number
         ORDER BY d.charity_number, d.financial_year_end
    """).fetchall()


@register_module(
    "m14_annual_reports", supports_since=True,
    depends_on=("m03_charity_finance",),
    depends_note="reads the accounts PDFs m03 downloads and archives",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m14_annual_reports"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    reports = _archived_reports(conn)
    if not reports:
        log.info("annual_reports.none_archived",
                  note="run m03_charity_finance first — this module reads the PDFs it archives")
        return

    if ctx.limit:
        reports = reports[:ctx.limit]

    reports_read = 0
    passages_written = 0
    gaps_recorded = 0
    archive = get_archive(ctx.settings)

    for row in ctx.track(reports, "annual reports"):
        if ctx.is_before_since(row["financial_year_end"]):
            continue

        provider_key = row["provider_key"]
        if not provider_key:
            db.record_review_item(
                conn, module_name, "annual_report_unlinked_charity", row["charity_number"],
                json.dumps({"financial_year_end": row["financial_year_end"],
                             "note": "no provider_identifiers row maps this charity number to a "
                                      "provider; the report cannot be attributed"}))
            continue

        archived = row["archived_path"]
        try:
            archived_bytes = archive.read(archived) if archived else None
        except (ArchiveError, OSError, FileNotFoundError, ValueError):
            archived_bytes = None
        if archived_bytes is None:
            db.record_review_item(
                conn, module_name, "annual_report_archive_missing", row["document_url"],
                json.dumps({"provider_key": provider_key,
                             "financial_year_end": row["financial_year_end"],
                             "note": "re-run m03_charity_finance to restore the archived PDF"}))
            continue

        try:
            # m03 already extracted this exact file to find the staff-costs
            # note. Keyed on the payload hash it recorded, so a hit is
            # provably the same bytes rather than probably the same file.
            pages = pdftext.numbered_pages(
                ctx.settings, M03_SOURCE_SYSTEM, row["payload_sha256"], archived_bytes)
        except Exception as exc:
            db.record_review_item(
                conn, module_name, "annual_report_unreadable", row["document_url"],
                json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            continue

        provenance = _provenance(row)
        db.upsert(conn, "provider_annual_reports", {
            "provider_key": provider_key,
            "financial_year_end": row["financial_year_end"],
            "charity_number": row["charity_number"],
            "document_url": row["document_url"],
            "archived_path": archived,
            "page_count": len(pages),
            **provenance,
        }, natural_key=["provider_key", "financial_year_end"])
        reports_read += 1

        all_passages: list[dict] = []
        passage_rows: list[dict] = []
        for page_number, page_text in pages:
            for passage in find_passages(page_text, page_number):
                passage_rows.append({
                    "provider_key": provider_key,
                    "financial_year_end": row["financial_year_end"],
                    **passage,
                    **provenance,
                })
                all_passages.append(passage)
                passages_written += 1

        db.upsert_many(
            conn, "provider_report_passages", passage_rows,
            natural_key=["provider_key", "financial_year_end", "topic",
                         "page_number", "matched_term"],
        )

        for topic, summary in summarise_disclosure(all_passages).items():
            db.upsert(conn, "provider_report_disclosure", {
                "provider_key": provider_key,
                "financial_year_end": row["financial_year_end"],
                "topic": topic,
                **summary,
                **provenance,
            }, natural_key=["provider_key", "financial_year_end", "topic"])
            if not summary["matched"]:
                gaps_recorded += 1

        log.info("annual_reports.report_read", provider_key=provider_key,
                  year=row["financial_year_end"], pages=len(pages),
                  passages=len(all_passages))

        if not ctx.dry_run:
            conn.commit()

    log.info("annual_reports.run_complete", reports=reports_read,
              passages=passages_written, disclosure_gaps=gaps_recorded)
