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
COMMITTEE_SEARCH_TERMS: list[str] = [
    "drug and alcohol",
    "substance misuse",
    "recommissioning",
    "TUPE",
    "public health grant",
    "treatment and recovery",
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
