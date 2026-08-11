"""Registry of authority websites and committee systems, for Modules 9 and 10.

These modules are semi-automated by design: they discover candidate
documents, and a human confirms them before anything is promoted. Both need
to know where each authority publishes, and that cannot be derived.

This file is seeded ONLY with entries verified by an actual request. It is
not populated from general knowledge: council hostnames are genuinely
unpredictable (democracy.kent.gov.uk works; the same pattern applied to five
other authorities resolved to nothing), and a wrong base URL would either
send requests to an unrelated site or silently produce no candidates while
looking like it had searched.

Authorities absent from here are written to review_queue by both modules, so
the coverage gap is always countable. To add one: find the authority's
committee/democracy site, confirm it loads, and add an entry below.

committee_system values:
  'moderngov' — ModernGov, recognisable by /mgWhatsNew.aspx and /ieDocHome.aspx
  'cmis'      — CMIS, recognisable by /CMIS5/ or /cmis5/ paths
  'democracy' — Democracy/other .NET committee systems
  None        — unknown; Module 10 routes these to its null adapter
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthorityWebsite:
    ons_code: str
    name: str
    base_url: str            # main council domain, for site-scoped document search
    committee_url: str | None = None   # committee system root, if different
    committee_system: str | None = None
    verified_on: str | None = None     # ISO date the URLs were last confirmed to load


# Verified by request. Extend deliberately; see module docstring.
AUTHORITY_WEBSITES: dict[str, AuthorityWebsite] = {
    "E10000016": AuthorityWebsite(
        ons_code="E10000016",
        name="Kent",
        base_url="https://www.kent.gov.uk",
        committee_url="https://democracy.kent.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-11",
    ),
}

# Path signatures used to identify a committee system from its root URL.
SYSTEM_SIGNATURES: dict[str, list[str]] = {
    "moderngov": ["/mgWhatsNew.aspx", "/ieDocHome.aspx"],
    "cmis": ["/CMIS5/Meetings.aspx", "/cmis5/Meetings.aspx"],
}


def website_for(ons_code: str) -> AuthorityWebsite | None:
    return AUTHORITY_WEBSITES.get(ons_code)


def configured_ons_codes() -> set[str]:
    return set(AUTHORITY_WEBSITES)
