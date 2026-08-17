"""What each source's material may be reused under.

Reuse — and defending reuse — starts with the licence. The portal's footer
said "public-domain source" and no figure, drawer or export named terms a
researcher could state, which makes every citation off this corpus an
unfinished one. Fingertips prints its OGL v3 terms and a citation format with
every indicator; this is the same obligation, met once.

One table, two consumers. The export layer writes `# licence:` lines into
every CSV header and a `licence` key into the JSON and the `X-Provenance`
response header; the portal's provenance drawer names the same licence beside
the figure. `tests/test_licences.py` holds the drawer's copy to this one, so
they cannot drift.

Three rules this file is written to:

  * **Per module, because a licence is a property of the source, not of a
    table.** `docs/SOURCES.md` records the terms one module at a time and is
    the document these entries are read from; a change there is a change here.
  * **Not everything is OGL.** Most of it is, and the two places that are not
    are the two most quotable: the workforce census is NHS Benchmarking
    material with its own terms, and council documents vary by council. An
    export that flattened those into "OGL v3.0" would be asserting a
    permission nobody granted.
  * **An endpoint names every licence its rows can be under, deduplicated.**
    Guessing the one that applies to a particular row would need per-row
    attribution the payloads do not carry, and being over-inclusive here is
    the conservative half of the mistake.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Licence:
    id: str
    name: str
    url: str | None
    # What a reuser has to do. Attribution is a condition of OGL v3, so it is
    # part of the licence statement rather than a footnote to it.
    attribution: str
    # Present only where the terms are not simply "reuse under this licence",
    # and printed with the licence wherever it appears.
    caution: str = ""


OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

LICENCES: dict[str, Licence] = {
    "ogl_v3": Licence(
        id="ogl_v3",
        name="Open Government Licence v3.0",
        url=OGL_URL,
        attribution="Contains public sector information licensed under the Open "
                    "Government Licence v3.0.",
    ),
    "ogl_v3_os": Licence(
        id="ogl_v3_os",
        name="Open Government Licence v3.0 (contains OS data)",
        url=OGL_URL,
        attribution="Contains public sector information licensed under the Open "
                    "Government Licence v3.0. Contains OS data © Crown copyright "
                    "and database right.",
    ),
    "nhs_benchmarking": Licence(
        id="nhs_benchmarking",
        name="NHS England / NHS Benchmarking Network — not OGL",
        url=None,
        attribution="NHS England / NHS Benchmarking Network content.",
        caution="Not open-licensed. Check the publisher's terms before "
                "republishing any figure from it.",
    ),
    "authority_varies": Licence(
        id="authority_varies",
        name="Varies by authority",
        url=None,
        attribution="Local authority publications; the publishing authority holds "
                    "the rights.",
        caution="Most councils publish under OGL v3.0 and none of them is "
                "guaranteed to. Check the individual document before "
                "republishing it.",
    ),
    "charity_own": Licence(
        id="charity_own",
        name="The charity's own copyright",
        url=None,
        attribution="Filed accounts from the public register of charities.",
        caution="A public record, not an open licence. Passages are held as "
                "evidence rather than republished wholesale.",
    ),
    "mysociety_mixed": Licence(
        id="mysociety_mixed",
        name="CC BY-SA (mySociety) with OGL v3.0 responses",
        url="https://creativecommons.org/licenses/by-sa/4.0/",
        attribution="Authority register and search data from mySociety "
                    "(WhatDoTheyKnow) under CC BY-SA; FOI responses generally OGL v3.0.",
        caution="Share-alike applies to the mySociety half. Council disclosure "
                "logs carry their own terms.",
    ),
    "nhs_jobs": Licence(
        id="nhs_jobs",
        name="Crown copyright, advert content the employer's",
        url=None,
        attribution="NHS Jobs service, Crown copyright.",
        caution="The text of each advert belongs to the employer that placed it.",
    ),
    "lwf_own": Licence(
        id="lwf_own",
        name="Living Wage Foundation — charity-published register",
        url=None,
        attribution="Accredited employer list published by the Living Wage "
                    "Foundation (a Citizens UK initiative).",
        caution="Not open-licensed. The list is factual data about which "
                "employers are accredited; check the foundation's terms "
                "before republishing it in bulk.",
    ),
    "provider_own": Licence(
        id="provider_own",
        name="The provider's own copyright",
        url=None,
        attribution="Pages published on the provider's own website.",
        caution="A public website, not an open licence. Passages are held as "
                "evidence rather than republished wholesale.",
    ),
    "skills_for_care": Licence(
        id="skills_for_care",
        name="OGL v3.0 (ASC-WDS data, per the data.gov.uk catalogue)",
        url=OGL_URL,
        attribution="Adult Social Care Workforce Data Set (ASC-WDS) workforce "
                    "estimates, published by Skills for Care.",
        caution="The data.gov.uk catalogue entry for ASC-WDS states OGL v3.0; "
                "the publisher's own pages carry a site-wide copyright line. "
                "Official statistics under the Code of Practice for "
                "Statistics; check the publisher's terms before republishing.",
    ),
}

# Read from docs/SOURCES.md, one row per module. A new module belongs here on
# the day it is written -- tests/test_licences.py fails for any registered
# module this does not name, because a source collected under terms nobody
# recorded is a source nothing may be published from.
MODULE_LICENCES: dict[str, str] = {
    "m00_geography": "ogl_v3_os",
    "m01_procurement": "ogl_v3",
    "m02_tribunals": "ogl_v3",
    "m03_charity_finance": "ogl_v3",
    "m04_companies": "ogl_v3",
    "m05_cqc": "ogl_v3",
    "m06_workforce_census": "nhs_benchmarking",
    "m07_ndtms": "ogl_v3",
    "m08_pfd_reports": "ogl_v3",
    "m09_cdp_documents": "authority_varies",
    "m10_committee_papers": "authority_varies",
    "m11_public_health_grant": "ogl_v3",
    "m12_fingertips": "ogl_v3",
    "m13_la_budgets": "ogl_v3",
    "m14_annual_reports": "charity_own",
    "m15_foi": "mysociety_mixed",
    "m16_nhs_jobs": "nhs_jobs",
    "m17_statutory_pay_rates": "ogl_v3",
    "m18_living_wage": "lwf_own",
    "m19_data_gov_uk": "ogl_v3",
    "m20_gender_pay_gap": "ogl_v3",
    "m21_ons_ashe": "ogl_v3",
    "m22_provider_pay_pages": "provider_own",
    "m23_sector_universe": "ogl_v3",
    "m24_council_spend": "authority_varies",
    "m25_skills_for_care": "skills_for_care",
}

# Which modules' material an exported endpoint can contain. Over-inclusive by
# design: `geography` draws a different metric from a different module on each
# request, and naming the four licences its rows can be under is defensible
# where naming the wrong one is not.
ENDPOINT_MODULES: dict[str, tuple[str, ...]] = {
    "summary": ("m00_geography", "m01_procurement", "m11_public_health_grant",
                 "m12_fingertips", "m06_workforce_census"),
    "providers": ("m01_procurement", "m02_tribunals", "m03_charity_finance",
                   "m05_cqc", "m16_nhs_jobs"),
    "authorities": ("m00_geography",),
    "contracts": ("m01_procurement",),
    "pay": ("m03_charity_finance",),
    "geography": ("m00_geography", "m01_procurement", "m11_public_health_grant",
                   "m12_fingertips", "m13_la_budgets"),
    "fingertips": ("m12_fingertips",),
    "ndtms": ("m07_ndtms",),
}


def for_module(module: str) -> Licence | None:
    key = MODULE_LICENCES.get(module)
    return LICENCES[key] if key else None


def for_endpoint(endpoint: str) -> list[Licence]:
    """Every licence an endpoint's rows can be under, in a stable order."""
    seen: dict[str, Licence] = {}
    for module in ENDPOINT_MODULES.get(endpoint.strip("/"), ()):
        licence = for_module(module)
        if licence:
            seen.setdefault(licence.id, licence)
    return list(seen.values())


def statement(licence: Licence) -> str:
    """One line, with the caution attached where there is one.

    The caution travels with the name rather than under it: a licence line
    reading "Varies by authority" on its own invites the reader to assume OGL,
    which is the assumption it exists to prevent.
    """
    parts = [licence.name]
    if licence.url:
        parts.append(f"<{licence.url}>")
    parts.append(licence.attribution)
    if licence.caution:
        parts.append(licence.caution)
    return " ".join(parts)
