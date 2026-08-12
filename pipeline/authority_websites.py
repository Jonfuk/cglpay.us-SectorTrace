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

There are now two ways in, and `website_for()` prefers the other one. A
reviewer answering an `authority_website_unknown` or `committee_url_unknown`
item in the web UI writes to `authority_url_overrides`, and the server
confirms the URL responds before storing it — the same standard this file
sets, applied at the point the answer is given rather than at the point
someone gets round to a commit. That table leads because it is specific,
current and attributed; this file remains the seed, the answer for anything
nobody has been asked about, and the version-controlled record. An entry
added here is reviewable in a diff, which an override is not, so a URL worth
keeping long-term still belongs below.

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
    # Main council domain, for site-scoped document search. Optional because a
    # reviewer can answer the committee question without answering this one —
    # callers that need it must check, as Module 9 and 10 both do.
    name: str
    base_url: str | None
    committee_url: str | None = None   # committee system root, if different
    committee_system: str | None = None
    verified_on: str | None = None     # ISO date the URLs were last confirmed to load
    # Where this answer came from, so a module can record it rather than
    # calling everything it was handed 'registry'. One of:
    #   'registry'       — the hand-verified table below, committed to git
    #   'human_verified' — a reviewer answered it in the UI and the server
    #                      confirmed the URL responded before storing it
    #   'foi_profile'    — mySociety's authority register, via Module 15
    source: str = "registry"


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


def detect_committee_system(probe) -> tuple[str, str | None]:
    """(system, signature_path). `probe` is called with a path and returns
    True if it exists. Returns ('unknown', None) when nothing matches — a
    recorded answer, not a fallback guess.

    Lives here rather than in Module 10 because the reviewer UI has to
    identify a system the same way when a human supplies a URL. Two copies of
    this would let the two disagree about what a council is running.
    """
    for system, paths in SYSTEM_SIGNATURES.items():
        for path in paths:
            if probe(path):
                return system, path
    return "unknown", None


def website_for(ons_code: str, conn=None) -> AuthorityWebsite | None:
    """The authority's website: a reviewer's answer first, then the
    hand-verified registry, then mySociety.

    `authority_url_overrides` leads because it is the only source that is both
    specific to these modules' needs and current — a person resolved a queue
    item for this authority, and the server confirmed the URL responded before
    storing it. The registry below is the same class of evidence recorded in
    git; it stays as the seed and as the answer for anything nobody has been
    asked about.

    `authority_foi_profiles` is last. Module 15 populates it from mySociety's
    published authority register, which is a citable source rather than a
    guess — it carries provenance and covers all 317 English authorities — but
    it is a home page, not a confirmation that these modules' specific paths
    answer there.
    """
    override = _override_for(ons_code, conn)
    if override:
        return override

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
        source="foi_profile",
    )


def _override_for(ons_code: str, conn) -> AuthorityWebsite | None:
    """A reviewer's answer from `authority_url_overrides`, if there is one.

    Tolerates the table being absent so that a warehouse built before
    migration 0027 still runs — these modules predate the reviewer, and a
    missing table is "nobody has answered", not an error.

    An override may name only one of the two URLs, since the two queue item
    types ask for different things. base_url falls back to the registry entry
    when a reviewer answered only the committee question, so answering one
    never removes an answer that already existed for the other.
    """
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM authority_url_overrides WHERE ons_code = ?", (ons_code,)
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None

    seed = AUTHORITY_WEBSITES.get(ons_code)
    # No falling back to the committee URL. They are different hosts doing
    # different jobs: Module 9 searches document paths under the council's own
    # domain, and running that search against a committee portal returns
    # nothing while looking like it worked — a council that publishes plenty
    # recorded as one that publishes none. An answer to the committee question
    # is not an answer to the website question, so base_url stays empty and
    # Module 9 keeps raising `authority_website_unknown` until someone answers
    # that one too.
    base_url = row["base_url"] or (seed.base_url if seed else None)

    return AuthorityWebsite(
        ons_code=ons_code,
        name=(seed.name if seed else ons_code),
        base_url=base_url,
        committee_url=row["committee_url"] or (seed.committee_url if seed else None),
        committee_system=row["committee_system"] or (seed.committee_system if seed else None),
        verified_on=(row["checked_at"] or row["verified_at"] or "")[:10] or None,
        source="human_verified",
    )


def configured_ons_codes() -> set[str]:
    return set(AUTHORITY_WEBSITES)
