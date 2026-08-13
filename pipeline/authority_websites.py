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
    # override is neither. `base_url` is None throughout: the issue gave
    # committee portals, and nobody has confirmed a council's main domain for
    # these, so the field stays empty rather than guessed.
    "E07000223": AuthorityWebsite(
        ons_code="E07000223",
        name="Adur",
        base_url=None,
        committee_url="https://democracy.adur-worthing.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000170": AuthorityWebsite(
        ons_code="E07000170",
        name="Ashfield",
        base_url=None,
        committee_url="https://democracy.ashfield.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.blaby.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.bcpcouncil.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.brent.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000043": AuthorityWebsite(
        ons_code="E06000043",
        name="Brighton and Hove",
        base_url=None,
        committee_url="https://democracy.brighton-hove.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000023": AuthorityWebsite(
        ons_code="E06000023",
        name="Bristol, City of",
        base_url=None,
        committee_url="https://democracy.bristol.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000172": AuthorityWebsite(
        ons_code="E07000172",
        name="Broxtowe",
        base_url=None,
        committee_url="https://democracy.broxtowe.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000008": AuthorityWebsite(
        ons_code="E07000008",
        name="Cambridge",
        base_url=None,
        committee_url="https://democracy.cambridge.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000078": AuthorityWebsite(
        ons_code="E07000078",
        name="Cheltenham",
        base_url=None,
        committee_url="https://democracy.cheltenham.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000118": AuthorityWebsite(
        ons_code="E07000118",
        name="Chorley",
        base_url=None,
        committee_url="https://democracy.chorley.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000226": AuthorityWebsite(
        ons_code="E07000226",
        name="Crawley",
        base_url=None,
        committee_url="https://democracy.crawley.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000008": AuthorityWebsite(
        ons_code="E09000008",
        name="Croydon",
        base_url=None,
        committee_url="https://democracy.croydon.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000015": AuthorityWebsite(
        ons_code="E06000015",
        name="Derby",
        base_url=None,
        committee_url="https://www.derby.gov.uk/council-and-democracy",
        committee_system=None,
        verified_on="2026-08-13",
    ),
    "E10000007": AuthorityWebsite(
        ons_code="E10000007",
        name="Derbyshire",
        base_url=None,
        committee_url="https://democracy.derbyshire.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000008": AuthorityWebsite(
        ons_code="E10000008",
        name="Devon",
        base_url=None,
        committee_url="https://democracy.devon.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000027": AuthorityWebsite(
        ons_code="E08000027",
        name="Dudley",
        base_url=None,
        committee_url="https://cmis.dudley.gov.uk/cmis5",
        committee_system=None,
        verified_on="2026-08-13",
    ),
    "E07000040": AuthorityWebsite(
        ons_code="E07000040",
        name="East Devon",
        base_url=None,
        committee_url="https://democracy.eastdevon.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000242": AuthorityWebsite(
        ons_code="E07000242",
        name="East Hertfordshire",
        base_url=None,
        committee_url="https://democracy.eastherts.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.epsom-ewell.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.gedling.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000081": AuthorityWebsite(
        ons_code="E07000081",
        name="Gloucester",
        base_url=None,
        committee_url="https://democracy.gloucester.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000013": AuthorityWebsite(
        ons_code="E10000013",
        name="Gloucestershire",
        base_url=None,
        committee_url="https://glostext.gloucestershire.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000088": AuthorityWebsite(
        ons_code="E07000088",
        name="Gosport",
        base_url=None,
        committee_url="https://democracy.gosport.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000209": AuthorityWebsite(
        ons_code="E07000209",
        name="Guildford",
        base_url=None,
        committee_url="https://democracy.guildford.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.havering.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000019": AuthorityWebsite(
        ons_code="E06000019",
        name="Herefordshire, County of",
        base_url=None,
        committee_url="https://councillors.herefordshire.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000037": AuthorityWebsite(
        ons_code="E07000037",
        name="High Peak",
        base_url=None,
        committee_url="https://democracy.highpeak.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000120": AuthorityWebsite(
        ons_code="E07000120",
        name="Hyndburn",
        base_url=None,
        committee_url="https://democracy.hyndburnbc.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000202": AuthorityWebsite(
        ons_code="E07000202",
        name="Ipswich",
        base_url=None,
        committee_url="https://democracy.ipswich.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000019": AuthorityWebsite(
        ons_code="E09000019",
        name="Islington",
        base_url=None,
        committee_url="https://democracy.islington.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000146": AuthorityWebsite(
        ons_code="E07000146",
        name="King's Lynn and West Norfolk",
        base_url=None,
        committee_url="https://democracy.west-norfolk.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000021": AuthorityWebsite(
        ons_code="E09000021",
        name="Kingston upon Thames",
        base_url=None,
        committee_url="https://kingston.moderngov.co.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000017": AuthorityWebsite(
        ons_code="E10000017",
        name="Lancashire",
        base_url=None,
        committee_url="https://council.lancashire.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://councilmeetings.lewisham.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000194": AuthorityWebsite(
        ons_code="E07000194",
        name="Lichfield",
        base_url=None,
        committee_url="https://democracy.lichfielddc.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000032": AuthorityWebsite(
        ons_code="E06000032",
        name="Luton",
        base_url=None,
        committee_url="https://democracy.luton.gov.uk/cmis5public",
        committee_system=None,
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
        base_url=None,
        committee_url="https://democracy.maldon.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.medway.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000133": AuthorityWebsite(
        ons_code="E07000133",
        name="Melton",
        base_url=None,
        committee_url="https://democracy.melton.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000024": AuthorityWebsite(
        ons_code="E09000024",
        name="Merton",
        base_url=None,
        committee_url="https://democracy.merton.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000042": AuthorityWebsite(
        ons_code="E07000042",
        name="Mid Devon",
        base_url=None,
        committee_url="https://democracy.middevon.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000175": AuthorityWebsite(
        ons_code="E07000175",
        name="Newark and Sherwood",
        base_url=None,
        committee_url="https://democracy.newark-sherwooddc.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000099": AuthorityWebsite(
        ons_code="E07000099",
        name="North Hertfordshire",
        base_url=None,
        committee_url="https://democracy.north-herts.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.northtyneside.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000065": AuthorityWebsite(
        ons_code="E06000065",
        name="North Yorkshire",
        base_url=None,
        committee_url="https://edemocracy.northyorks.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000018": AuthorityWebsite(
        ons_code="E06000018",
        name="Nottingham",
        base_url=None,
        committee_url="https://committee.nottinghamcity.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000178": AuthorityWebsite(
        ons_code="E07000178",
        name="Oxford",
        base_url=None,
        committee_url="https://mycouncil.oxford.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000025": AuthorityWebsite(
        ons_code="E10000025",
        name="Oxfordshire",
        base_url=None,
        committee_url="https://mycouncil.oxfordshire.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000031": AuthorityWebsite(
        ons_code="E06000031",
        name="Peterborough",
        base_url=None,
        committee_url="https://democracy.peterborough.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000044": AuthorityWebsite(
        ons_code="E06000044",
        name="Portsmouth",
        base_url=None,
        committee_url="https://democracy.portsmouth.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000038": AuthorityWebsite(
        ons_code="E06000038",
        name="Reading",
        base_url=None,
        committee_url="https://democracy.reading.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000124": AuthorityWebsite(
        ons_code="E07000124",
        name="Ribble Valley",
        base_url=None,
        committee_url="https://democracy.ribblevalley.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000005": AuthorityWebsite(
        ons_code="E08000005",
        name="Rochdale",
        base_url=None,
        committee_url="https://democracy.rochdale.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000018": AuthorityWebsite(
        ons_code="E08000018",
        name="Rotherham",
        base_url=None,
        committee_url="https://moderngov.rotherham.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000212": AuthorityWebsite(
        ons_code="E07000212",
        name="Runnymede",
        base_url=None,
        committee_url="https://democracy.runnymede.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000176": AuthorityWebsite(
        ons_code="E07000176",
        name="Rushcliffe",
        base_url=None,
        committee_url="https://democracy.rushcliffe.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000092": AuthorityWebsite(
        ons_code="E07000092",
        name="Rushmoor",
        base_url=None,
        committee_url="https://democracy.rushmoor.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000039": AuthorityWebsite(
        ons_code="E08000039",
        name="Sheffield",
        base_url=None,
        committee_url="https://democracy.sheffield.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000039": AuthorityWebsite(
        ons_code="E06000039",
        name="Slough",
        base_url=None,
        committee_url="https://democracy.slough.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000029": AuthorityWebsite(
        ons_code="E08000029",
        name="Solihull",
        base_url=None,
        committee_url="https://democracy.solihull.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000066": AuthorityWebsite(
        ons_code="E06000066",
        name="Somerset",
        base_url=None,
        committee_url="https://democracy.somerset.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democratic.southoxon.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000033": AuthorityWebsite(
        ons_code="E06000033",
        name="Southend-on-Sea",
        base_url=None,
        committee_url="https://democracy.southend.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000213": AuthorityWebsite(
        ons_code="E07000213",
        name="Spelthorne",
        base_url=None,
        committee_url="https://democracy.spelthorne.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.stevenage.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E10000029": AuthorityWebsite(
        ons_code="E10000029",
        name="Suffolk",
        base_url=None,
        committee_url="https://committeeminutes.suffolk.gov.uk",
        committee_system=None,
        verified_on="2026-08-13",
    ),
    "E10000030": AuthorityWebsite(
        ons_code="E10000030",
        name="Surrey",
        base_url=None,
        committee_url="https://mycouncil.surreycc.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000029": AuthorityWebsite(
        ons_code="E09000029",
        name="Sutton",
        base_url=None,
        committee_url="https://moderngov.sutton.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.telford.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000093": AuthorityWebsite(
        ons_code="E07000093",
        name="Test Valley",
        base_url=None,
        committee_url="https://democracy.testvalley.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000114": AuthorityWebsite(
        ons_code="E07000114",
        name="Thanet",
        base_url=None,
        committee_url="https://democracy.thanet.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000034": AuthorityWebsite(
        ons_code="E06000034",
        name="Thurrock",
        base_url=None,
        committee_url="https://democracy.thurrock.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000030": AuthorityWebsite(
        ons_code="E09000030",
        name="Tower Hamlets",
        base_url=None,
        committee_url="https://democracy.towerhamlets.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democratic.whitehorsedc.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000030": AuthorityWebsite(
        ons_code="E08000030",
        name="Walsall",
        base_url=None,
        committee_url="https://cmispublic.walsall.gov.uk/cmis",
        committee_system=None,
        verified_on="2026-08-13",
    ),
    "E10000031": AuthorityWebsite(
        ons_code="E10000031",
        name="Warwickshire",
        base_url=None,
        committee_url="https://democracy.warwickshire.gov.uk",
        committee_system="moderngov",
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
        base_url=None,
        committee_url="https://democracy.westlancs.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000142": AuthorityWebsite(
        ons_code="E07000142",
        name="West Lindsey",
        base_url=None,
        committee_url="https://democracy.west-lindsey.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E09000033": AuthorityWebsite(
        ons_code="E09000033",
        name="Westminster",
        base_url=None,
        committee_url="https://committees.westminster.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000010": AuthorityWebsite(
        ons_code="E08000010",
        name="Wigan",
        base_url=None,
        committee_url="https://democracy.wigan.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000094": AuthorityWebsite(
        ons_code="E07000094",
        name="Winchester",
        base_url=None,
        committee_url="https://democracy.winchester.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E08000015": AuthorityWebsite(
        ons_code="E08000015",
        name="Wirral",
        base_url=None,
        committee_url="https://democracy.wirral.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E07000229": AuthorityWebsite(
        ons_code="E07000229",
        name="Worthing",
        base_url=None,
        committee_url="https://democracy.adur-worthing.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
    ),
    "E06000014": AuthorityWebsite(
        ons_code="E06000014",
        name="York",
        base_url=None,
        committee_url="https://democracy.york.gov.uk",
        committee_system="moderngov",
        verified_on="2026-08-13",
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
