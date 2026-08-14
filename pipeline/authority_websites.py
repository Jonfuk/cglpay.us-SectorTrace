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

import json
import threading
from dataclasses import dataclass
from pathlib import Path


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
    # base_url's own confirmation date, when it differs from the committee
    # URL's. The two are separate questions answered on separate days, and a
    # single date would have to overstate one of them: most entries below had
    # their committee portal confirmed in August 2026 and their council domain
    # confirmed later, from a different list. `review_sweep` reads verified_on
    # as the committee URL's date, so that is what it stays.
    base_url_verified_on: str | None = None
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

    # --- from issue #1, each fetched once through the pipeline's own client ---
    #
    # 104 of the 313 URLs in the issue responded; these are those, plus
    # Herefordshire, which was found on its council's homepage instead. What
    # each of the other 209 did is in docs/verification/issue1_committee_urls.md
    # -- 138 hostnames that do not resolve, 26 refused by robots.txt, 16 403s.
    #
    # They live here rather than only in `authority_url_overrides` because the
    # table was emptied on 2026-08-13 and 191 verified URLs went with it. A
    # committed entry is diff-reviewable and survives the warehouse; an
    # override is neither.
    #
    # The issue gave committee portals only, so `base_url` was None throughout
    # this block until 2026-08-14, when a separate list of council home pages
    # was verified the same way and filled 85 of them. The ones still None are
    # the councils whose home page did not answer -- see the block at the end
    # of this dict, and docs/verification/authority_homepages.md.
    "E07000223": AuthorityWebsite(
        ons_code="E07000223",
        name="Adur",
        base_url="https://www.adur-worthing.gov.uk",
        committee_url="https://democracy.adur-worthing.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000170": AuthorityWebsite(
        ons_code="E07000170",
        name="Ashfield",
        base_url="https://www.ashfield.gov.uk",
        committee_url="https://democracy.ashfield.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000084": AuthorityWebsite(
        ons_code="E07000084",
        name="Basingstoke and Deane",
        base_url=None,
        committee_url="https://democracy.basingstoke.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000129": AuthorityWebsite(
        ons_code="E07000129",
        name="Blaby",
        base_url="https://www.blaby.gov.uk",
        committee_url="https://democracy.blaby.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000008": AuthorityWebsite(
        ons_code="E06000008",
        name="Blackburn with Darwen",
        base_url=None,
        committee_url="https://democracy.blackburn.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000058": AuthorityWebsite(
        ons_code="E06000058",
        name="Bournemouth, Christchurch and Poole",
        base_url="https://www.bcpcouncil.gov.uk",
        committee_url="https://democracy.bcpcouncil.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000143": AuthorityWebsite(
        ons_code="E07000143",
        name="Breckland",
        base_url=None,
        committee_url="https://democracy.breckland.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000005": AuthorityWebsite(
        ons_code="E09000005",
        name="Brent",
        base_url="https://www.brent.gov.uk",
        committee_url="https://democracy.brent.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000043": AuthorityWebsite(
        ons_code="E06000043",
        name="Brighton and Hove",
        base_url="https://www.brighton-hove.gov.uk",
        committee_url="https://democracy.brighton-hove.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000023": AuthorityWebsite(
        ons_code="E06000023",
        name="Bristol, City of",
        base_url="https://www.bristol.gov.uk",
        committee_url="https://democracy.bristol.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000172": AuthorityWebsite(
        ons_code="E07000172",
        name="Broxtowe",
        base_url="https://www.broxtowe.gov.uk",
        committee_url="https://democracy.broxtowe.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000008": AuthorityWebsite(
        ons_code="E07000008",
        name="Cambridge",
        base_url="https://www.cambridge.gov.uk",
        committee_url="https://democracy.cambridge.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000078": AuthorityWebsite(
        ons_code="E07000078",
        name="Cheltenham",
        base_url="https://www.cheltenham.gov.uk",
        committee_url="https://democracy.cheltenham.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000118": AuthorityWebsite(
        ons_code="E07000118",
        name="Chorley",
        base_url="https://www.chorley.gov.uk",
        committee_url="https://democracy.chorley.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000226": AuthorityWebsite(
        ons_code="E07000226",
        name="Crawley",
        base_url="https://www.crawley.gov.uk",
        committee_url="https://democracy.crawley.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000008": AuthorityWebsite(
        ons_code="E09000008",
        name="Croydon",
        base_url="https://www.croydon.gov.uk",
        committee_url="https://democracy.croydon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000015": AuthorityWebsite(
        ons_code="E06000015",
        name="Derby",
        base_url="https://www.derby.gov.uk",
        committee_url="https://www.derby.gov.uk/council-and-democracy",
        committee_system=None,
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000007": AuthorityWebsite(
        ons_code="E10000007",
        name="Derbyshire",
        base_url="https://www.derbyshire.gov.uk",
        committee_url="https://democracy.derbyshire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000008": AuthorityWebsite(
        ons_code="E10000008",
        name="Devon",
        base_url="https://www.devon.gov.uk",
        committee_url="https://democracy.devon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000027": AuthorityWebsite(
        ons_code="E08000027",
        name="Dudley",
        base_url="https://www.dudley.gov.uk",
        committee_url="https://cmis.dudley.gov.uk/cmis5",
        committee_system=None,
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000040": AuthorityWebsite(
        ons_code="E07000040",
        name="East Devon",
        base_url="https://www.eastdevon.gov.uk",
        committee_url="https://democracy.eastdevon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000242": AuthorityWebsite(
        ons_code="E07000242",
        name="East Hertfordshire",
        base_url="https://www.eastherts.gov.uk",
        committee_url="https://democracy.eastherts.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000061": AuthorityWebsite(
        ons_code="E07000061",
        name="Eastbourne",
        base_url=None,
        committee_url="https://democracy.lewes-eastbourne.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000208": AuthorityWebsite(
        ons_code="E07000208",
        name="Epsom and Ewell",
        base_url="https://www.epsom-ewell.gov.uk",
        committee_url="https://democracy.epsom-ewell.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000037": AuthorityWebsite(
        ons_code="E08000037",
        name="Gateshead",
        base_url=None,
        committee_url="https://democracy.gateshead.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000173": AuthorityWebsite(
        ons_code="E07000173",
        name="Gedling",
        base_url="https://www.gedling.gov.uk",
        committee_url="https://democracy.gedling.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000081": AuthorityWebsite(
        ons_code="E07000081",
        name="Gloucester",
        base_url="https://www.gloucester.gov.uk",
        committee_url="https://democracy.gloucester.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000013": AuthorityWebsite(
        ons_code="E10000013",
        name="Gloucestershire",
        base_url="https://www.gloucestershire.gov.uk",
        committee_url="https://glostext.gloucestershire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000088": AuthorityWebsite(
        ons_code="E07000088",
        name="Gosport",
        base_url="https://www.gosport.gov.uk",
        committee_url="https://democracy.gosport.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000209": AuthorityWebsite(
        ons_code="E07000209",
        name="Guildford",
        base_url="https://www.guildford.gov.uk",
        committee_url="https://democracy.guildford.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000013": AuthorityWebsite(
        ons_code="E09000013",
        name="Hammersmith and Fulham",
        base_url=None,
        committee_url="https://democracy.lbhf.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000014": AuthorityWebsite(
        ons_code="E10000014",
        name="Hampshire",
        base_url=None,
        committee_url="https://democracy.hants.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000016": AuthorityWebsite(
        ons_code="E09000016",
        name="Havering",
        base_url="https://www.havering.gov.uk",
        committee_url="https://democracy.havering.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000019": AuthorityWebsite(
        ons_code="E06000019",
        name="Herefordshire, County of",
        base_url="https://www.herefordshire.gov.uk",
        committee_url="https://councillors.herefordshire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000037": AuthorityWebsite(
        ons_code="E07000037",
        name="High Peak",
        base_url="https://www.highpeak.gov.uk",
        committee_url="https://democracy.highpeak.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000120": AuthorityWebsite(
        ons_code="E07000120",
        name="Hyndburn",
        base_url="https://www.hyndburnbc.gov.uk",
        committee_url="https://democracy.hyndburnbc.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000202": AuthorityWebsite(
        ons_code="E07000202",
        name="Ipswich",
        base_url="https://www.ipswich.gov.uk",
        committee_url="https://democracy.ipswich.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000019": AuthorityWebsite(
        ons_code="E09000019",
        name="Islington",
        base_url="https://www.islington.gov.uk",
        committee_url="https://democracy.islington.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000146": AuthorityWebsite(
        ons_code="E07000146",
        name="King's Lynn and West Norfolk",
        base_url="https://www.west-norfolk.gov.uk",
        committee_url="https://democracy.west-norfolk.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000021": AuthorityWebsite(
        ons_code="E09000021",
        name="Kingston upon Thames",
        base_url="https://www.kingston.gov.uk",
        committee_url="https://kingston.moderngov.co.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000017": AuthorityWebsite(
        ons_code="E10000017",
        name="Lancashire",
        base_url="https://www.lancashire.gov.uk",
        committee_url="https://council.lancashire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000018": AuthorityWebsite(
        ons_code="E10000018",
        name="Leicestershire",
        base_url=None,
        committee_url="https://politics.leics.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000063": AuthorityWebsite(
        ons_code="E07000063",
        name="Lewes",
        base_url=None,
        committee_url="https://democracy.lewes-eastbourne.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000023": AuthorityWebsite(
        ons_code="E09000023",
        name="Lewisham",
        base_url="https://www.lewisham.gov.uk",
        committee_url="https://councilmeetings.lewisham.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000194": AuthorityWebsite(
        ons_code="E07000194",
        name="Lichfield",
        base_url="https://www.lichfielddc.gov.uk",
        committee_url="https://democracy.lichfielddc.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000032": AuthorityWebsite(
        ons_code="E06000032",
        name="Luton",
        base_url="https://www.luton.gov.uk",
        committee_url="https://democracy.luton.gov.uk/cmis5public",
        committee_system=None,
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000110": AuthorityWebsite(
        ons_code="E07000110",
        name="Maidstone",
        base_url=None,
        committee_url="https://meetings.maidstone.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000074": AuthorityWebsite(
        ons_code="E07000074",
        name="Maldon",
        base_url="https://www.maldon.gov.uk",
        committee_url="https://democracy.maldon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000003": AuthorityWebsite(
        ons_code="E08000003",
        name="Manchester",
        base_url=None,
        committee_url="https://democracy.manchester.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000035": AuthorityWebsite(
        ons_code="E06000035",
        name="Medway",
        base_url="https://www.medway.gov.uk",
        committee_url="https://democracy.medway.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000133": AuthorityWebsite(
        ons_code="E07000133",
        name="Melton",
        base_url="https://www.melton.gov.uk",
        committee_url="https://democracy.melton.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000024": AuthorityWebsite(
        ons_code="E09000024",
        name="Merton",
        base_url="https://www.merton.gov.uk",
        committee_url="https://democracy.merton.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000042": AuthorityWebsite(
        ons_code="E07000042",
        name="Mid Devon",
        base_url="https://www.middevon.gov.uk",
        committee_url="https://democracy.middevon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000175": AuthorityWebsite(
        ons_code="E07000175",
        name="Newark and Sherwood",
        base_url="https://www.newark-sherwooddc.gov.uk",
        committee_url="https://democracy.newark-sherwooddc.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000099": AuthorityWebsite(
        ons_code="E07000099",
        name="North Hertfordshire",
        base_url="https://www.north-herts.gov.uk",
        committee_url="https://democracy.north-herts.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000013": AuthorityWebsite(
        ons_code="E06000013",
        name="North Lincolnshire",
        base_url=None,
        committee_url="https://democracy.northlincs.gov.uk",
        committee_system=None,
        verified_on="2026-08-13",
    ),
    "E08000022": AuthorityWebsite(
        ons_code="E08000022",
        name="North Tyneside",
        base_url="https://www.northtyneside.gov.uk",
        committee_url="https://democracy.northtyneside.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000065": AuthorityWebsite(
        ons_code="E06000065",
        name="North Yorkshire",
        base_url="https://www.northyorks.gov.uk",
        committee_url="https://edemocracy.northyorks.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000018": AuthorityWebsite(
        ons_code="E06000018",
        name="Nottingham",
        base_url="https://www.nottinghamcity.gov.uk",
        committee_url="https://committee.nottinghamcity.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000178": AuthorityWebsite(
        ons_code="E07000178",
        name="Oxford",
        base_url="https://www.oxford.gov.uk",
        committee_url="https://mycouncil.oxford.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000025": AuthorityWebsite(
        ons_code="E10000025",
        name="Oxfordshire",
        base_url="https://www.oxfordshire.gov.uk",
        committee_url="https://mycouncil.oxfordshire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000031": AuthorityWebsite(
        ons_code="E06000031",
        name="Peterborough",
        base_url="https://www.peterborough.gov.uk",
        committee_url="https://democracy.peterborough.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000044": AuthorityWebsite(
        ons_code="E06000044",
        name="Portsmouth",
        base_url="https://www.portsmouth.gov.uk",
        committee_url="https://democracy.portsmouth.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000038": AuthorityWebsite(
        ons_code="E06000038",
        name="Reading",
        base_url="https://www.reading.gov.uk",
        committee_url="https://democracy.reading.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000124": AuthorityWebsite(
        ons_code="E07000124",
        name="Ribble Valley",
        base_url="https://www.ribblevalley.gov.uk",
        committee_url="https://democracy.ribblevalley.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000005": AuthorityWebsite(
        ons_code="E08000005",
        name="Rochdale",
        base_url="https://www.rochdale.gov.uk",
        committee_url="https://democracy.rochdale.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000018": AuthorityWebsite(
        ons_code="E08000018",
        name="Rotherham",
        base_url="https://www.rotherham.gov.uk",
        committee_url="https://moderngov.rotherham.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000212": AuthorityWebsite(
        ons_code="E07000212",
        name="Runnymede",
        base_url="https://www.runnymede.gov.uk",
        committee_url="https://democracy.runnymede.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000176": AuthorityWebsite(
        ons_code="E07000176",
        name="Rushcliffe",
        base_url="https://www.rushcliffe.gov.uk",
        committee_url="https://democracy.rushcliffe.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000092": AuthorityWebsite(
        ons_code="E07000092",
        name="Rushmoor",
        base_url="https://www.rushmoor.gov.uk",
        committee_url="https://democracy.rushmoor.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000039": AuthorityWebsite(
        ons_code="E08000039",
        name="Sheffield",
        base_url="https://www.sheffield.gov.uk",
        committee_url="https://democracy.sheffield.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000039": AuthorityWebsite(
        ons_code="E06000039",
        name="Slough",
        base_url="https://www.slough.gov.uk",
        committee_url="https://democracy.slough.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000029": AuthorityWebsite(
        ons_code="E08000029",
        name="Solihull",
        base_url="https://www.solihull.gov.uk",
        committee_url="https://democracy.solihull.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000066": AuthorityWebsite(
        ons_code="E06000066",
        name="Somerset",
        base_url="https://www.somerset.gov.uk",
        committee_url="https://democracy.somerset.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000149": AuthorityWebsite(
        ons_code="E07000149",
        name="South Norfolk",
        base_url=None,
        committee_url="https://democracy.southnorfolkandbroadland.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000179": AuthorityWebsite(
        ons_code="E07000179",
        name="South Oxfordshire",
        base_url="https://www.southoxon.gov.uk",
        committee_url="https://democratic.southoxon.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000033": AuthorityWebsite(
        ons_code="E06000033",
        name="Southend-on-Sea",
        base_url="https://www.southend.gov.uk",
        committee_url="https://democracy.southend.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000213": AuthorityWebsite(
        ons_code="E07000213",
        name="Spelthorne",
        base_url="https://www.spelthorne.gov.uk",
        committee_url="https://democracy.spelthorne.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000198": AuthorityWebsite(
        ons_code="E07000198",
        name="Staffordshire Moorlands",
        base_url=None,
        committee_url="https://democracy.staffsmoorlands.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000243": AuthorityWebsite(
        ons_code="E07000243",
        name="Stevenage",
        base_url="https://www.stevenage.gov.uk",
        committee_url="https://democracy.stevenage.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000029": AuthorityWebsite(
        ons_code="E10000029",
        name="Suffolk",
        base_url="https://www.suffolk.gov.uk",
        committee_url="https://committeeminutes.suffolk.gov.uk",
        committee_system=None,
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000030": AuthorityWebsite(
        ons_code="E10000030",
        name="Surrey",
        base_url="https://www.surreycc.gov.uk",
        committee_url="https://mycouncil.surreycc.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000029": AuthorityWebsite(
        ons_code="E09000029",
        name="Sutton",
        base_url="https://www.sutton.gov.uk",
        committee_url="https://moderngov.sutton.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000045": AuthorityWebsite(
        ons_code="E07000045",
        name="Teignbridge",
        base_url=None,
        committee_url="https://democracy.teignbridge.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000020": AuthorityWebsite(
        ons_code="E06000020",
        name="Telford and Wrekin",
        base_url="https://www.telford.gov.uk",
        committee_url="https://democracy.telford.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000093": AuthorityWebsite(
        ons_code="E07000093",
        name="Test Valley",
        base_url="https://www.testvalley.gov.uk",
        committee_url="https://democracy.testvalley.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000114": AuthorityWebsite(
        ons_code="E07000114",
        name="Thanet",
        base_url="https://www.thanet.gov.uk",
        committee_url="https://democracy.thanet.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000034": AuthorityWebsite(
        ons_code="E06000034",
        name="Thurrock",
        base_url="https://www.thurrock.gov.uk",
        committee_url="https://democracy.thurrock.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000030": AuthorityWebsite(
        ons_code="E09000030",
        name="Tower Hamlets",
        base_url="https://www.towerhamlets.gov.uk",
        committee_url="https://democracy.towerhamlets.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000116": AuthorityWebsite(
        ons_code="E07000116",
        name="Tunbridge Wells",
        base_url=None,
        committee_url="https://democracy.tunbridgewells.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000180": AuthorityWebsite(
        ons_code="E07000180",
        name="Vale of White Horse",
        base_url="https://www.whitehorsedc.gov.uk",
        committee_url="https://democratic.whitehorsedc.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000030": AuthorityWebsite(
        ons_code="E08000030",
        name="Walsall",
        base_url="https://www.walsall.gov.uk",
        committee_url="https://cmispublic.walsall.gov.uk/cmis",
        committee_system=None,
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E10000031": AuthorityWebsite(
        ons_code="E10000031",
        name="Warwickshire",
        base_url="https://www.warwickshire.gov.uk",
        committee_url="https://democracy.warwickshire.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000037": AuthorityWebsite(
        ons_code="E06000037",
        name="West Berkshire",
        base_url=None,
        committee_url="https://decisionmaking.westberks.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000127": AuthorityWebsite(
        ons_code="E07000127",
        name="West Lancashire",
        base_url="https://www.westlancs.gov.uk",
        committee_url="https://democracy.westlancs.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000142": AuthorityWebsite(
        ons_code="E07000142",
        name="West Lindsey",
        base_url="https://www.west-lindsey.gov.uk",
        committee_url="https://democracy.west-lindsey.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E09000033": AuthorityWebsite(
        ons_code="E09000033",
        name="Westminster",
        base_url="https://www.westminster.gov.uk",
        committee_url="https://committees.westminster.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000010": AuthorityWebsite(
        ons_code="E08000010",
        name="Wigan",
        base_url="https://www.wigan.gov.uk",
        committee_url="https://democracy.wigan.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000094": AuthorityWebsite(
        ons_code="E07000094",
        name="Winchester",
        base_url="https://www.winchester.gov.uk",
        committee_url="https://democracy.winchester.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E08000015": AuthorityWebsite(
        ons_code="E08000015",
        name="Wirral",
        base_url="https://www.wirral.gov.uk",
        committee_url="https://democracy.wirral.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E07000229": AuthorityWebsite(
        ons_code="E07000229",
        name="Worthing",
        base_url="https://www.adur-worthing.gov.uk",
        committee_url="https://democracy.adur-worthing.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),
    "E06000014": AuthorityWebsite(
        ons_code="E06000014",
        name="York",
        base_url="https://www.york.gov.uk",
        committee_url="https://democracy.york.gov.uk",
        committee_system="moderngov",
        base_url_verified_on="2026-08-14",
        verified_on="2026-08-13",
    ),

    # --- council home pages, verified 2026-08-14 ---
    #
    # 317 candidate URLs -- every principal English authority -- fetched once
    # through the pipeline's own client. 268 answered with a council's home
    # page and are here; docs/verification/authority_homepages.md says what
    # each of the other 49 did.
    #
    # A 200 was not enough on its own. Four authorities answered 200 with a bot
    # challenge (Incapsula, a reCAPTCHA wall), and storing those would have had
    # Module 9 search an interstitial for documents and record the council as
    # publishing none -- the silent failure this file exists to prevent. So the
    # test was on content, not status.
    #
    # `committee_url` is None throughout this block: a home page is not an
    # answer to the committee question, and Module 10 keeps raising
    # `committee_url_unknown` for these until somebody answers that one too.
    "E07000032": AuthorityWebsite(
        ons_code="E07000032",
        name="Amber Valley",
        base_url="https://www.ambervalley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000224": AuthorityWebsite(
        ons_code="E07000224",
        name="Arun",
        base_url="https://www.arun.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000105": AuthorityWebsite(
        ons_code="E07000105",
        name="Ashford",
        base_url="https://www.ashford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000200": AuthorityWebsite(
        ons_code="E07000200",
        name="Babergh",
        base_url="https://www.babergh.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000002": AuthorityWebsite(
        ons_code="E09000002",
        name="Barking and Dagenham",
        base_url="https://www.lbbd.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000038": AuthorityWebsite(
        ons_code="E08000038",
        name="Barnsley",
        base_url="https://www.barnsley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000171": AuthorityWebsite(
        ons_code="E07000171",
        name="Bassetlaw",
        base_url="https://www.bassetlaw.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000022": AuthorityWebsite(
        ons_code="E06000022",
        name="Bath and North East Somerset",
        base_url="https://www.bathnes.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000055": AuthorityWebsite(
        ons_code="E06000055",
        name="Bedford",
        base_url="https://www.bedford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000004": AuthorityWebsite(
        ons_code="E09000004",
        name="Bexley",
        base_url="https://www.bexley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000025": AuthorityWebsite(
        ons_code="E08000025",
        name="Birmingham",
        base_url="https://www.birmingham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000009": AuthorityWebsite(
        ons_code="E06000009",
        name="Blackpool",
        base_url="https://www.blackpool.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000033": AuthorityWebsite(
        ons_code="E07000033",
        name="Bolsover",
        base_url="https://www.bolsover.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000001": AuthorityWebsite(
        ons_code="E08000001",
        name="Bolton",
        base_url="https://www.bolton.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000036": AuthorityWebsite(
        ons_code="E06000036",
        name="Bracknell Forest",
        base_url="https://www.bracknell-forest.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000032": AuthorityWebsite(
        ons_code="E08000032",
        name="Bradford",
        base_url="https://www.bradford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000067": AuthorityWebsite(
        ons_code="E07000067",
        name="Braintree",
        base_url="https://www.braintree.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000068": AuthorityWebsite(
        ons_code="E07000068",
        name="Brentwood",
        base_url="https://www.brentwood.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000006": AuthorityWebsite(
        ons_code="E09000006",
        name="Bromley",
        base_url="https://www.bromley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000234": AuthorityWebsite(
        ons_code="E07000234",
        name="Bromsgrove",
        base_url="https://www.bromsgrove.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000095": AuthorityWebsite(
        ons_code="E07000095",
        name="Broxbourne",
        base_url="https://www.broxbourne.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000060": AuthorityWebsite(
        ons_code="E06000060",
        name="Buckinghamshire",
        base_url="https://www.buckinghamshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000117": AuthorityWebsite(
        ons_code="E07000117",
        name="Burnley",
        base_url="https://www.burnley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000002": AuthorityWebsite(
        ons_code="E08000002",
        name="Bury",
        base_url="https://www.bury.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000033": AuthorityWebsite(
        ons_code="E08000033",
        name="Calderdale",
        base_url="https://www.calderdale.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000003": AuthorityWebsite(
        ons_code="E10000003",
        name="Cambridgeshire",
        base_url="https://www.cambridgeshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000192": AuthorityWebsite(
        ons_code="E07000192",
        name="Cannock Chase",
        base_url="https://www.cannockchasedc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000106": AuthorityWebsite(
        ons_code="E07000106",
        name="Canterbury",
        base_url="https://www.canterbury.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000069": AuthorityWebsite(
        ons_code="E07000069",
        name="Castle Point",
        base_url="https://www.castlepoint.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000056": AuthorityWebsite(
        ons_code="E06000056",
        name="Central Bedfordshire",
        base_url="https://www.centralbedfordshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000130": AuthorityWebsite(
        ons_code="E07000130",
        name="Charnwood",
        base_url="https://www.charnwood.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000070": AuthorityWebsite(
        ons_code="E07000070",
        name="Chelmsford",
        base_url="https://www.chelmsford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000177": AuthorityWebsite(
        ons_code="E07000177",
        name="Cherwell",
        base_url="https://www.cherwell.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000049": AuthorityWebsite(
        ons_code="E06000049",
        name="Cheshire East",
        base_url="https://www.cheshireeast.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000050": AuthorityWebsite(
        ons_code="E06000050",
        name="Cheshire West and Chester",
        base_url="https://www.cheshirewestandchester.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000034": AuthorityWebsite(
        ons_code="E07000034",
        name="Chesterfield",
        base_url="https://www.chesterfield.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000001": AuthorityWebsite(
        ons_code="E09000001",
        name="City of London",
        base_url="https://www.cityoflondon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000071": AuthorityWebsite(
        ons_code="E07000071",
        name="Colchester",
        base_url="https://www.colchester.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000052": AuthorityWebsite(
        ons_code="E06000052",
        name="Cornwall",
        base_url="https://www.cornwall.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000079": AuthorityWebsite(
        ons_code="E07000079",
        name="Cotswold",
        base_url="https://www.cotswold.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000047": AuthorityWebsite(
        ons_code="E06000047",
        name="County Durham",
        base_url="https://www.durham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000026": AuthorityWebsite(
        ons_code="E08000026",
        name="Coventry",
        base_url="https://www.coventry.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000063": AuthorityWebsite(
        ons_code="E06000063",
        name="Cumberland",
        base_url="https://www.cumberland.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000096": AuthorityWebsite(
        ons_code="E07000096",
        name="Dacorum",
        base_url="https://www.dacorum.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000107": AuthorityWebsite(
        ons_code="E07000107",
        name="Dartford",
        base_url="https://www.dartford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000035": AuthorityWebsite(
        ons_code="E07000035",
        name="Derbyshire Dales",
        base_url="https://www.derbyshiredales.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000017": AuthorityWebsite(
        ons_code="E08000017",
        name="Doncaster",
        base_url="https://www.doncaster.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000059": AuthorityWebsite(
        ons_code="E06000059",
        name="Dorset",
        base_url="https://www.dorsetcouncil.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000108": AuthorityWebsite(
        ons_code="E07000108",
        name="Dover",
        base_url="https://www.dover.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000009": AuthorityWebsite(
        ons_code="E09000009",
        name="Ealing",
        base_url="https://www.ealing.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000009": AuthorityWebsite(
        ons_code="E07000009",
        name="East Cambridgeshire",
        base_url="https://www.eastcambs.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000085": AuthorityWebsite(
        ons_code="E07000085",
        name="East Hampshire",
        base_url="https://www.easthants.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000011": AuthorityWebsite(
        ons_code="E06000011",
        name="East Riding of Yorkshire",
        base_url="https://www.eastriding.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000193": AuthorityWebsite(
        ons_code="E07000193",
        name="East Staffordshire",
        base_url="https://www.eaststaffsbc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000244": AuthorityWebsite(
        ons_code="E07000244",
        name="East Suffolk",
        base_url="https://www.eastsuffolk.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000011": AuthorityWebsite(
        ons_code="E10000011",
        name="East Sussex",
        base_url="https://www.eastsussex.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000207": AuthorityWebsite(
        ons_code="E07000207",
        name="Elmbridge",
        base_url="https://www.elmbridge.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000072": AuthorityWebsite(
        ons_code="E07000072",
        name="Epping Forest",
        base_url="https://www.eppingforestdc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000036": AuthorityWebsite(
        ons_code="E07000036",
        name="Erewash",
        base_url="https://www.erewash.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000012": AuthorityWebsite(
        ons_code="E10000012",
        name="Essex",
        base_url="https://www.essex.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000041": AuthorityWebsite(
        ons_code="E07000041",
        name="Exeter",
        base_url="https://www.exeter.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000087": AuthorityWebsite(
        ons_code="E07000087",
        name="Fareham",
        base_url="https://www.fareham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000112": AuthorityWebsite(
        ons_code="E07000112",
        name="Folkestone and Hythe",
        base_url="https://www.folkestone-hythe.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000080": AuthorityWebsite(
        ons_code="E07000080",
        name="Forest of Dean",
        base_url="https://www.fdean.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000119": AuthorityWebsite(
        ons_code="E07000119",
        name="Fylde",
        base_url="https://www.fylde.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000109": AuthorityWebsite(
        ons_code="E07000109",
        name="Gravesham",
        base_url="https://www.gravesham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000011": AuthorityWebsite(
        ons_code="E09000011",
        name="Greenwich",
        base_url="https://www.royalgreenwich.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000012": AuthorityWebsite(
        ons_code="E09000012",
        name="Hackney",
        base_url="https://www.hackney.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000131": AuthorityWebsite(
        ons_code="E07000131",
        name="Harborough",
        base_url="https://www.harborough.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000014": AuthorityWebsite(
        ons_code="E09000014",
        name="Haringey",
        base_url="https://www.haringey.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000073": AuthorityWebsite(
        ons_code="E07000073",
        name="Harlow",
        base_url="https://www.harlow.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000015": AuthorityWebsite(
        ons_code="E09000015",
        name="Harrow",
        base_url="https://www.harrow.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000089": AuthorityWebsite(
        ons_code="E07000089",
        name="Hart",
        base_url="https://www.hart.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000001": AuthorityWebsite(
        ons_code="E06000001",
        name="Hartlepool",
        base_url="https://www.hartlepool.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000062": AuthorityWebsite(
        ons_code="E07000062",
        name="Hastings",
        base_url="https://www.hastings.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000090": AuthorityWebsite(
        ons_code="E07000090",
        name="Havant",
        base_url="https://www.havant.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000015": AuthorityWebsite(
        ons_code="E10000015",
        name="Hertfordshire",
        base_url="https://www.hertfordshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000098": AuthorityWebsite(
        ons_code="E07000098",
        name="Hertsmere",
        base_url="https://www.hertsmere.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000017": AuthorityWebsite(
        ons_code="E09000017",
        name="Hillingdon",
        base_url="https://www.hillingdon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000132": AuthorityWebsite(
        ons_code="E07000132",
        name="Hinckley and Bosworth",
        base_url="https://www.hinckley-bosworth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000018": AuthorityWebsite(
        ons_code="E09000018",
        name="Hounslow",
        base_url="https://www.hounslow.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000011": AuthorityWebsite(
        ons_code="E07000011",
        name="Huntingdonshire",
        base_url="https://www.huntingdonshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000053": AuthorityWebsite(
        ons_code="E06000053",
        name="Isles of Scilly",
        base_url="https://www.scilly.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000020": AuthorityWebsite(
        ons_code="E09000020",
        name="Kensington and Chelsea",
        base_url="https://www.rbkc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000010": AuthorityWebsite(
        ons_code="E06000010",
        name="Kingston upon Hull, City of",
        base_url="https://www.hull.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000011": AuthorityWebsite(
        ons_code="E08000011",
        name="Knowsley",
        base_url="https://www.knowsley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000022": AuthorityWebsite(
        ons_code="E09000022",
        name="Lambeth",
        base_url="https://www.lambeth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000121": AuthorityWebsite(
        ons_code="E07000121",
        name="Lancaster",
        base_url="https://www.lancaster.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000035": AuthorityWebsite(
        ons_code="E08000035",
        name="Leeds",
        base_url="https://www.leeds.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000016": AuthorityWebsite(
        ons_code="E06000016",
        name="Leicester",
        base_url="https://www.leicester.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000138": AuthorityWebsite(
        ons_code="E07000138",
        name="Lincoln",
        base_url="https://www.lincoln.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000019": AuthorityWebsite(
        ons_code="E10000019",
        name="Lincolnshire",
        base_url="https://www.lincolnshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000235": AuthorityWebsite(
        ons_code="E07000235",
        name="Malvern Hills",
        base_url="https://www.malvernhills.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000174": AuthorityWebsite(
        ons_code="E07000174",
        name="Mansfield",
        base_url="https://www.mansfield.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000203": AuthorityWebsite(
        ons_code="E07000203",
        name="Mid Suffolk",
        base_url="https://www.midsuffolk.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000228": AuthorityWebsite(
        ons_code="E07000228",
        name="Mid Sussex",
        base_url="https://www.midsussex.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000042": AuthorityWebsite(
        ons_code="E06000042",
        name="Milton Keynes",
        base_url="https://www.milton-keynes.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000210": AuthorityWebsite(
        ons_code="E07000210",
        name="Mole Valley",
        base_url="https://www.molevalley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000021": AuthorityWebsite(
        ons_code="E08000021",
        name="Newcastle upon Tyne",
        base_url="https://www.newcastle.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000195": AuthorityWebsite(
        ons_code="E07000195",
        name="Newcastle-under-Lyme",
        base_url="https://www.newcastle-staffs.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000025": AuthorityWebsite(
        ons_code="E09000025",
        name="Newham",
        base_url="https://www.newham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000043": AuthorityWebsite(
        ons_code="E07000043",
        name="North Devon",
        base_url="https://www.northdevon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000012": AuthorityWebsite(
        ons_code="E06000012",
        name="North East Lincolnshire",
        base_url="https://www.nelincs.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000139": AuthorityWebsite(
        ons_code="E07000139",
        name="North Kesteven",
        base_url="https://www.n-kesteven.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000147": AuthorityWebsite(
        ons_code="E07000147",
        name="North Norfolk",
        base_url="https://www.north-norfolk.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000061": AuthorityWebsite(
        ons_code="E06000061",
        name="North Northamptonshire",
        base_url="https://www.northnorthants.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000024": AuthorityWebsite(
        ons_code="E06000024",
        name="North Somerset",
        base_url="https://www.n-somerset.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000218": AuthorityWebsite(
        ons_code="E07000218",
        name="North Warwickshire",
        base_url="https://www.northwarks.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000134": AuthorityWebsite(
        ons_code="E07000134",
        name="North West Leicestershire",
        base_url="https://www.nwleics.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000148": AuthorityWebsite(
        ons_code="E07000148",
        name="Norwich",
        base_url="https://www.norwich.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000024": AuthorityWebsite(
        ons_code="E10000024",
        name="Nottinghamshire",
        base_url="https://www.nottinghamshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000219": AuthorityWebsite(
        ons_code="E07000219",
        name="Nuneaton and Bedworth",
        base_url="https://www.nuneatonandbedworth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000135": AuthorityWebsite(
        ons_code="E07000135",
        name="Oadby and Wigston",
        base_url="https://www.oadby-wigston.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000004": AuthorityWebsite(
        ons_code="E08000004",
        name="Oldham",
        base_url="https://www.oldham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000122": AuthorityWebsite(
        ons_code="E07000122",
        name="Pendle",
        base_url="https://www.pendle.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000026": AuthorityWebsite(
        ons_code="E06000026",
        name="Plymouth",
        base_url="https://www.plymouth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000026": AuthorityWebsite(
        ons_code="E09000026",
        name="Redbridge",
        base_url="https://www.redbridge.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000003": AuthorityWebsite(
        ons_code="E06000003",
        name="Redcar and Cleveland",
        base_url="https://www.redcar-cleveland.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000236": AuthorityWebsite(
        ons_code="E07000236",
        name="Redditch",
        base_url="https://www.redditchbc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000211": AuthorityWebsite(
        ons_code="E07000211",
        name="Reigate and Banstead",
        base_url="https://www.reigate-banstead.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000027": AuthorityWebsite(
        ons_code="E09000027",
        name="Richmond upon Thames",
        base_url="https://www.richmond.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000075": AuthorityWebsite(
        ons_code="E07000075",
        name="Rochford",
        base_url="https://www.rochford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000125": AuthorityWebsite(
        ons_code="E07000125",
        name="Rossendale",
        base_url="https://www.rossendale.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000064": AuthorityWebsite(
        ons_code="E07000064",
        name="Rother",
        base_url="https://www.rother.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000220": AuthorityWebsite(
        ons_code="E07000220",
        name="Rugby",
        base_url="https://www.rugby.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000017": AuthorityWebsite(
        ons_code="E06000017",
        name="Rutland",
        base_url="https://www.rutland.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000006": AuthorityWebsite(
        ons_code="E08000006",
        name="Salford",
        base_url="https://www.salford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000028": AuthorityWebsite(
        ons_code="E08000028",
        name="Sandwell",
        base_url="https://www.sandwell.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000014": AuthorityWebsite(
        ons_code="E08000014",
        name="Sefton",
        base_url="https://www.sefton.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000111": AuthorityWebsite(
        ons_code="E07000111",
        name="Sevenoaks",
        base_url="https://www.sevenoaks.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000051": AuthorityWebsite(
        ons_code="E06000051",
        name="Shropshire",
        base_url="https://www.shropshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000012": AuthorityWebsite(
        ons_code="E07000012",
        name="South Cambridgeshire",
        base_url="https://www.scambs.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000039": AuthorityWebsite(
        ons_code="E07000039",
        name="South Derbyshire",
        base_url="https://www.southderbyshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000025": AuthorityWebsite(
        ons_code="E06000025",
        name="South Gloucestershire",
        base_url="https://www.southglos.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000044": AuthorityWebsite(
        ons_code="E07000044",
        name="South Hams",
        base_url="https://www.southhams.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000141": AuthorityWebsite(
        ons_code="E07000141",
        name="South Kesteven",
        base_url="https://www.southkesteven.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000126": AuthorityWebsite(
        ons_code="E07000126",
        name="South Ribble",
        base_url="https://www.southribble.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000196": AuthorityWebsite(
        ons_code="E07000196",
        name="South Staffordshire",
        base_url="https://www.sstaffs.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000028": AuthorityWebsite(
        ons_code="E09000028",
        name="Southwark",
        base_url="https://www.southwark.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000240": AuthorityWebsite(
        ons_code="E07000240",
        name="St Albans",
        base_url="https://www.stalbans.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000013": AuthorityWebsite(
        ons_code="E08000013",
        name="St. Helens",
        base_url="https://www.sthelens.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000197": AuthorityWebsite(
        ons_code="E07000197",
        name="Stafford",
        base_url="https://www.staffordbc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000028": AuthorityWebsite(
        ons_code="E10000028",
        name="Staffordshire",
        base_url="https://www.staffordshire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000007": AuthorityWebsite(
        ons_code="E08000007",
        name="Stockport",
        base_url="https://www.stockport.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000021": AuthorityWebsite(
        ons_code="E06000021",
        name="Stoke-on-Trent",
        base_url="https://www.stoke.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000221": AuthorityWebsite(
        ons_code="E07000221",
        name="Stratford-on-Avon",
        base_url="https://www.stratford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000082": AuthorityWebsite(
        ons_code="E07000082",
        name="Stroud",
        base_url="https://www.stroud.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000214": AuthorityWebsite(
        ons_code="E07000214",
        name="Surrey Heath",
        base_url="https://www.surreyheath.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000030": AuthorityWebsite(
        ons_code="E06000030",
        name="Swindon",
        base_url="https://www.swindon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000008": AuthorityWebsite(
        ons_code="E08000008",
        name="Tameside",
        base_url="https://www.tameside.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000199": AuthorityWebsite(
        ons_code="E07000199",
        name="Tamworth",
        base_url="https://www.tamworth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000215": AuthorityWebsite(
        ons_code="E07000215",
        name="Tandridge",
        base_url="https://www.tandridge.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000076": AuthorityWebsite(
        ons_code="E07000076",
        name="Tendring",
        base_url="https://www.tendringdc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000083": AuthorityWebsite(
        ons_code="E07000083",
        name="Tewkesbury",
        base_url="https://www.tewkesbury.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000102": AuthorityWebsite(
        ons_code="E07000102",
        name="Three Rivers",
        base_url="https://www.threerivers.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000115": AuthorityWebsite(
        ons_code="E07000115",
        name="Tonbridge and Malling",
        base_url="https://www.tmbc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000027": AuthorityWebsite(
        ons_code="E06000027",
        name="Torbay",
        base_url="https://www.torbay.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000046": AuthorityWebsite(
        ons_code="E07000046",
        name="Torridge",
        base_url="https://www.torridge.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000009": AuthorityWebsite(
        ons_code="E08000009",
        name="Trafford",
        base_url="https://www.trafford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000036": AuthorityWebsite(
        ons_code="E08000036",
        name="Wakefield",
        base_url="https://www.wakefield.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000031": AuthorityWebsite(
        ons_code="E09000031",
        name="Waltham Forest",
        base_url="https://www.walthamforest.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E09000032": AuthorityWebsite(
        ons_code="E09000032",
        name="Wandsworth",
        base_url="https://www.wandsworth.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000007": AuthorityWebsite(
        ons_code="E06000007",
        name="Warrington",
        base_url="https://www.warrington.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000222": AuthorityWebsite(
        ons_code="E07000222",
        name="Warwick",
        base_url="https://www.warwickdc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000103": AuthorityWebsite(
        ons_code="E07000103",
        name="Watford",
        base_url="https://www.watford.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000216": AuthorityWebsite(
        ons_code="E07000216",
        name="Waverley",
        base_url="https://www.waverley.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000065": AuthorityWebsite(
        ons_code="E07000065",
        name="Wealden",
        base_url="https://www.wealden.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000241": AuthorityWebsite(
        ons_code="E07000241",
        name="Welwyn Hatfield",
        base_url="https://www.welhat.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000047": AuthorityWebsite(
        ons_code="E07000047",
        name="West Devon",
        base_url="https://www.westdevon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000062": AuthorityWebsite(
        ons_code="E06000062",
        name="West Northamptonshire",
        base_url="https://www.westnorthants.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000181": AuthorityWebsite(
        ons_code="E07000181",
        name="West Oxfordshire",
        base_url="https://www.westoxon.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000245": AuthorityWebsite(
        ons_code="E07000245",
        name="West Suffolk",
        base_url="https://www.westsuffolk.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000032": AuthorityWebsite(
        ons_code="E10000032",
        name="West Sussex",
        base_url="https://www.westsussex.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000064": AuthorityWebsite(
        ons_code="E06000064",
        name="Westmorland and Furness",
        base_url="https://www.westmorlandandfurness.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000040": AuthorityWebsite(
        ons_code="E06000040",
        name="Windsor and Maidenhead",
        base_url="https://www.rbwm.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000217": AuthorityWebsite(
        ons_code="E07000217",
        name="Woking",
        base_url="https://www.woking.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E06000041": AuthorityWebsite(
        ons_code="E06000041",
        name="Wokingham",
        base_url="https://www.wokingham.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E08000031": AuthorityWebsite(
        ons_code="E08000031",
        name="Wolverhampton",
        base_url="https://www.wolverhampton.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E10000034": AuthorityWebsite(
        ons_code="E10000034",
        name="Worcestershire",
        base_url="https://www.worcestershire.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000128": AuthorityWebsite(
        ons_code="E07000128",
        name="Wyre",
        base_url="https://www.wyre.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
    ),
    "E07000239": AuthorityWebsite(
        ons_code="E07000239",
        name="Wyre Forest",
        base_url="https://www.wyreforestdc.gov.uk",
        committee_url=None,
        committee_system=None,
        verified_on="2026-08-14",
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


# --- answers given in the review UI, kept where the warehouse cannot lose them -

_VERIFIED_LOCK = threading.Lock()
_VERIFIED_CACHE: dict = {"mtime": None, "path": None, "entries": {}}


def verified_websites(settings=None) -> dict[str, AuthorityWebsite]:
    """URLs a reviewer answered in the UI, read from the tracked JSON file.

    The same evidence as an entry below — the server confirmed the URL
    responded before it was stored — written somewhere git can see it. The
    override table remains the live record; this is the copy that survives it.
    On 2026-08-13 that table was emptied and 191 verified URLs went with it,
    of which only the ones a document happened to record were recoverable.

    Cached on the file's mtime, because Modules 9 and 10 ask once per
    authority and there are 347 of them.
    """
    from pipeline.config import get_settings

    path = Path((settings or get_settings()).verified_websites_path)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return {}

    with _VERIFIED_LOCK:
        if _VERIFIED_CACHE["mtime"] == mtime and _VERIFIED_CACHE["path"] == path:
            return _VERIFIED_CACHE["entries"]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A malformed file must not take the modules down: the registry
            # below and the override table still answer.
            return {}
        entries = {
            code: AuthorityWebsite(
                ons_code=code,
                name=item.get("name") or code,
                base_url=item.get("base_url"),
                committee_url=item.get("committee_url"),
                committee_system=item.get("committee_system"),
                verified_on=item.get("verified_on"),
                source="human_verified",
            )
            for code, item in sorted(raw.get("authorities", {}).items())
        }
        _VERIFIED_CACHE.update(mtime=mtime, path=path, entries=entries)
        return entries


def record_verified_website(ons_code: str, name: str | None, field: str, url: str,
                             committee_system: str | None, verified_by: str,
                             verified_on: str, settings=None) -> None:
    """Write one answer into the tracked file, merging with what is there.

    Read-modify-write under a lock. Two reviewers answering at once is not a
    scenario this project has, and the file is a few hundred short entries.

    Never raises at the caller. A resolution that succeeded must not be
    reported as failed because a file could not be written — the override is
    already stored, and the warning says what to do about it.
    """
    from pipeline.config import get_settings

    path = Path((settings or get_settings()).verified_websites_path)
    try:
        with _VERIFIED_LOCK:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            authorities = raw.setdefault("authorities", {})
            entry = authorities.setdefault(ons_code, {})
            # Answering one question must not erase the answer to the other,
            # the same rule the override row follows.
            entry["name"] = name or entry.get("name") or ons_code
            entry[field] = url
            if committee_system:
                entry["committee_system"] = committee_system
            entry["verified_on"] = verified_on
            entry["verified_by"] = verified_by
            raw["note"] = (
                "Written by the review UI when a reviewer answers where a "
                "council publishes, after the server has confirmed the URL "
                "responds. Tracked in git so an answer outlives the "
                "warehouse -- see pipeline/authority_websites.py. Safe to "
                "hand-edit; entries here are read by website_for().")
            raw["authorities"] = dict(sorted(authorities.items()))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw, indent=2, sort_keys=False) + "\n",
                             encoding="utf-8")
            _VERIFIED_CACHE.update(mtime=None, path=None, entries={})
    except OSError as exc:  # pragma: no cover - depends on the filesystem
        import structlog

        structlog.get_logger().warning(
            "authority_websites.record_failed", ons_code=ons_code,
            path=str(path), error=str(exc),
            note="the override was stored; this answer is not in git")


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

    # The reviewer's own answer, from the tracked file, before the seed
    # registry: it is more specific and more recent, and it is the same class
    # of evidence recorded in the same place.
    answered = verified_websites().get(ons_code)
    if answered:
        return answered

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
    """Every authority answered in git — the seed registry plus the file the
    review UI writes. Both are committed, so both count as configured."""
    return set(AUTHORITY_WEBSITES) | set(verified_websites())
