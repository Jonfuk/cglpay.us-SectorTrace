"""Deliberately modest deterministic classification and topic tagging."""
from __future__ import annotations

import re

TOPICS = {
    "WORKFORCE": ("workforce", "vacancy", "vacancies", "recruitment", "retention", "turnover",
                  "agency staff", "staffing", "caseload", "workload", "sickness", "absence"),
    "CONTRACT_PERFORMANCE": ("contract", "performance", "kpi", "mobilisation", "variation", "extension",
                             "procurement", "award"),
    "SERVICE_PRESSURE": ("waiting list", "waiting time", "capacity", "demand", "referrals", "caseload"),
    "FINANCE": ("funding", "budget", "cost pressure", "public health grant", "uplift", "inflation"),
}


def classify(source_system: str, title: str | None, filename: str | None) -> tuple[str, str, float]:
    haystack = " ".join((source_system, title or "", filename or "")).lower()
    rules = (("COMMITTEE_PAPER", ("committee", "moderngov", "agenda")),
             ("ANNUAL_REPORT", ("annual report", "annual-report")),
             ("FOI_RESPONSE", ("foi", "freedom of information")),
             ("PROCUREMENT_DOCUMENT", ("procurement", "tender", "contract")),
             ("PFD_REPORT", ("prevention of future deaths", "pfd")))
    for document_type, terms in rules:
        if any(term in haystack for term in terms):
            return document_type, "source_metadata_keyword", 0.7
    return "UNKNOWN", "no_deterministic_match", 0.0


def topic_matches(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {topic: sum(len(re.findall(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lowered))
            for term in terms)
            for topic, terms in TOPICS.items()
            if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lowered) for term in terms)}
