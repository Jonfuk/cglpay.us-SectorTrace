"""Keyword, CPV code and supplier-alias config used by modules 1 and 2.

Kept as plain data here (not inline in module code) so the corpus can be
re-filtered without re-fetching, per the brief's Module 1 approach.
"""
from __future__ import annotations

# CPV prefixes relevant to health and social work procurement.
RELEVANT_CPV_PREFIXES: list[str] = [
    "85",  # Health and social work services
    "853",  # Social work and related services
]

# Free-text keywords to filter release titles/descriptions locally.
SUBSTANCE_MISUSE_KEYWORDS: list[str] = [
    "drug",
    "alcohol",
    "substance misuse",
    "substance use",
    "treatment and recovery",
    "harm reduction",
    "needle exchange",
    "detoxification",
    "recovery service",
]

# Name variants for the target provider and comparators. These are indexed
# as-is; matching to a canonical supplier_id happens via the
# supplier_aliases table (explicit review step), never fuzzy matching.
SUPPLIER_NAME_VARIANTS: dict[str, list[str]] = {
    "change_grow_live": [
        "Change Grow Live",
        "Change, Grow, Live",
        "Change Grow Live Service Limited",
        "Change Grow Live Services Ltd",
        "CGL",
    ],
    "turning_point": ["Turning Point"],
    "with_you": ["With You"],
    "addaction": ["Addaction"],
    "waythrough": ["Waythrough"],
    "humankind": ["Humankind"],
    "richmond_fellowship": ["Richmond Fellowship"],
    "via": ["Via"],
    "westminster_drug_project": ["Westminster Drug Project"],
    "forward_trust": ["Forward Trust"],
    "phoenix_futures": ["Phoenix Futures"],
    "delphi_medical": ["Delphi Medical"],
    "inclusion": ["Inclusion"],
}

# Search terms for tribunal judgments (Module 2) — respondent name variants
# to query, since the comma-separated form appears in real judgments.
TRIBUNAL_RESPONDENT_VARIANTS: list[str] = SUPPLIER_NAME_VARIANTS["change_grow_live"]

# Search terms for council committee papers (Module 10).
#
# Two groups. The first is the subject: papers about the services themselves.
# The second is audit and assurance — internal audit reports, external audit
# findings and Public Interest Reports go to the same committees and are
# indexed by the same ModernGov search, so they cost new search terms rather
# than a new module.
#
# Audit terms are deliberately paired with a subject word where the bare term
# would match everything a council does ("internal audit" alone returns the
# audit committee's entire history). The same lesson as m14 and m15: a bare
# term that matches thousands of irrelevant papers produces a review worklist
# nobody can triage, which is worse than not searching.
#
# Every term costs 300 councils x up to 3 result pages, so this list is not
# free to extend — see MAX_RESULT_PAGES in m10.
COMMITTEE_SEARCH_TERMS: list[str] = [
    "drug and alcohol",
    "substance misuse",
    "recommissioning",
    "TUPE",
    "public health grant",
    "treatment and recovery",
    # Audit and assurance. A Public Interest Report is rare and always
    # serious — the auditor is formally telling the council something the
    # public needs to know — so it is worth searching unqualified.
    "public interest report",
    "internal audit public health",
    "audit substance misuse",
]

# PFD report categories of interest (Module 8).
PFD_CATEGORIES: list[str] = [
    "Alcohol, drug and medication related deaths",
    "Mental health related deaths",
    "Community health care and emergency services related deaths",
]

# Terms indexed within a PFD report's MATTERS OF CONCERN section (Module 8).
PFD_CONCERN_INDEX_TERMS: list[str] = [
    "staffing",
    "caseload",
    "capacity",
    "vacancy",
    "recruitment",
    "retention",
    "workload",
    "waiting",
]
