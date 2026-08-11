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
    "E08000034": AuthorityWebsite(
        ons_code="E08000034",
        name="Kirklees",
        base_url="https://www.kirklees.gov.uk",
        committee_url="https://democracy.kirklees.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-11",
    ),
    "E06000005": AuthorityWebsite(
        ons_code="E06000005",
        name="Darlington",
        base_url="https://www.darlington.gov.uk",
        committee_url="https://democracy.darlington.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-11",
    ),
}

# Path signatures used to identify a committee system from its root URL.
SYSTEM_SIGNATURES: dict[str, list[str]] = {
    "moderngov": ["/mgWhatsNew.aspx", "/ieDocHome.aspx"],
    "cmis": ["/CMIS5/Meetings.aspx", "/cmis5/Meetings.aspx"],
}

# Paths that only a committee system serves, used to recognise one in a link
# published on a council's own home page. Matching a link is not enough on its
# own — Module 10 then probes SYSTEM_SIGNATURES against the host it points at,
# so a URL is only accepted when the council links it *and* it answers.
COMMITTEE_LINK_SIGNATURES: tuple[str, ...] = (
    "mgwhatsnew.aspx",
    "iedochome.aspx",
    "ielistmeetings.aspx",
    "iedocsearch.aspx",
    "mglistcommittees.aspx",
    "mgcommitteedetails.aspx",
    "mgcalendarmonthview.aspx",
    "/cmis5/",
)


def website_for(ons_code: str, conn=None) -> AuthorityWebsite | None:
    """The authority's website, preferring the hand-verified entry above.

    Falls back to `authority_foi_profiles`, which Module 15 populates from
    mySociety's published authority register. That is a citable source rather
    than a guess — it carries provenance and covers all 317 English
    authorities — but it is second in precedence because the entries here were
    confirmed by an actual request against the specific paths these modules
    use.
    """
    configured = AUTHORITY_WEBSITES.get(ons_code)
    if configured or conn is None:
        return configured

    try:
        row = conn.execute(
            "SELECT authority_name, home_page_url FROM authority_foi_profiles "
            "WHERE ons_code = ? AND home_page_url IS NOT NULL", (ons_code,)).fetchone()
    except Exception:
        return None
    if not row or not row["home_page_url"]:
        return None

    return AuthorityWebsite(
        ons_code=ons_code,
        name=row["authority_name"],
        base_url=row["home_page_url"].rstrip("/"),
        # No committee URL: mySociety's register does not record one, and
        # guessing it is what this file exists to avoid.
        committee_url=None,
        committee_system=None,
        verified_on=None,
    )


def configured_ons_codes() -> set[str]:
    return set(AUTHORITY_WEBSITES)
