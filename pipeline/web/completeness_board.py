"""The coverage completion action board (BETA-059).

`pipeline/completeness.py` scores the *campaign*'s coverage against a
denominator. This is a different question: for each dataset the portal
catalogues (`pipeline/web/datasets.py`), why is it not further along, and
what is the one permitted next step?

Every row carries exactly one reason code and one non-destructive
destination. Nothing here runs a module, decides a review item, or deletes
anything — the destinations are links a person follows.

Reason codes, in precedence order:
  * ``run_needed``     — the dataset has no rows; the module has not been run
    here. Next step: run it (from the Pipeline tab).
  * ``review_needed``  — the module has pending `review_queue` items. Next
    step: work that filter in the Review tab.
  * ``source_blocked`` — a documented gap on the source's side (robots, an
    unvalidated parser, a licence hold). Next step: read the note.
  * ``not_published``  — the dataset is collected but has no dedicated public
    route beyond its catalogue entry. Next step: the catalogue entry.
  * ``complete``       — collected, reviewed, published.
"""
from __future__ import annotations

from pipeline import catalog
from pipeline.web import datasets

REASONS = ("run_needed", "review_needed", "source_blocked", "not_published",
            "complete")

# Modules with a dedicated public route beyond the catalogue count. A module
# absent here whose dataset has rows is `not_published`. Curated, not derived:
# the routes are hand-maintained and this is the list a person would check.
_PUBLICLY_ROUTED: frozenset[str] = frozenset({
    "m00_geography", "m01_procurement", "m02_tribunals", "m03_charity_finance",
    "m05_cqc", "m06_workforce_census", "m07_ndtms", "m08_pfd_reports",
    "m09_cdp_documents", "m10_committee_papers", "m11_public_health_grant",
    "m12_fingertips", "m13_la_budgets", "m14_annual_reports", "m16_nhs_jobs",
    "m17_statutory_pay_rates", "m18_living_wage", "m20_gender_pay_gap",
    "m21_ons_ashe", "m22_provider_pay_pages", "m24_council_spend",
    "m25_skills_for_care", "m27_ndtms_monthly", "m28_sar_reports",
    "m29_rough_sleeping", "m30_statutory_homelessness",
    "m31_temporary_accommodation", "m32_sab_site_reviews", "m33_hse_notices",
})

# A documented gap on the source's side, module -> the note a person needs.
# Curated from docs/CAVEATS.md and docs/SOURCES.md; kept short deliberately.
_SOURCE_BLOCKED: dict[str, str] = {
    "m33_hse_notices": "The live-fetch parser has not yet been validated "
                        "against real HSE HTML — first run to be watched by a "
                        "person (docs/SOURCES.md, Module 33).",
    "m15_foi": "A robots.txt exception for the WhatDoTheyKnow feed is time-"
                "limited; see the caveat before treating FOI coverage as "
                "stable.",
}


def _pending_by_module(conn) -> dict[str, int]:
    if not catalog.object_type(conn, "review_queue"):
        return {}
    return {row["module"]: row["count"] for row in conn.execute(
        "SELECT module, COUNT(*) AS count FROM review_queue WHERE status = 'pending' "
        "AND module IS NOT NULL GROUP BY module")}


def board(conn) -> dict:
    """One action row per catalogued dataset."""
    pending = _pending_by_module(conn)

    rows: list[dict] = []
    for ds in datasets.DATASETS:
        counts = catalog.row_counts(conn, ds.public_tables)
        total = sum(counts.values())
        n_pending = pending.get(ds.module, 0)

        if total == 0:
            reason = "run_needed"
            action = {"kind": "run", "label": f"Run {ds.module}",
                       "target": ds.module}
        elif n_pending:
            reason = "review_needed"
            action = {"kind": "review",
                       "label": f"{n_pending} pending review item(s)",
                       "target": ds.module}
        elif ds.module in _SOURCE_BLOCKED:
            reason = "source_blocked"
            action = {"kind": "dataset", "label": "Read the source note",
                       "target": ds.dataset_id}
        elif ds.module not in _PUBLICLY_ROUTED:
            reason = "not_published"
            action = {"kind": "dataset", "label": "Catalogued only — no route",
                       "target": ds.dataset_id}
        else:
            reason = "complete"
            action = {"kind": "dataset", "label": "Catalogue entry",
                       "target": ds.dataset_id}

        rows.append({
            "dataset_id": ds.dataset_id,
            "module": ds.module,
            "title": ds.title,
            "evidence_layer": ds.evidence_layer,
            "row_count": total,
            "pending_review": n_pending,
            "reason": reason,
            "reason_note": _SOURCE_BLOCKED.get(ds.module),
            "action": action,
        })

    by_reason = {reason: sum(1 for r in rows if r["reason"] == reason)
                  for reason in REASONS}
    return {
        "datasets": rows,
        "by_reason": by_reason,
        "reasons": list(REASONS),
        "caveat": (
            "Each dataset has one reason it is not further along and one "
            "permitted next step. Nothing on this board runs a module, "
            "decides a review item, or deletes anything — the actions are "
            "links a person follows."),
    }
