"""Registry for Module 34 — where each Integrated Care Board publishes its
Board and committee papers.

There are 42 ICBs. Each publishes governance papers on its own website with a
bespoke CMS; the path is not derivable, and an invented URL would either hit
an unrelated page or silently find nothing while looking like it had searched
(the Module 9 lesson). So m34 has two ways to a board_url, in this order:

  1. A hand-verified entry in ``VERIFIED_BOARD_URLS`` below — confirmed by an
     actual request against the exact page m34 will crawl, reviewable in a
     diff. Only one is seeded so far (the request that prompted the module).
  2. Failing that: the ICB's own link on the NHS England directory, and a
     probe of ``MEETING_PATHS`` against that link's origin. The first path
     that answers and carries governance vocabulary is taken, recorded with
     ``board_url_source = 'path_probe'`` so it is distinguishable from a
     hand-verified one.

An ICB with neither is written to ``review_queue`` as ``icb_board_url_unknown``
so the coverage gap stays countable.

To add a verified entry: open the ICB's site, find the page that lists Board
(and committee) meetings with the papers attached, confirm it loads, and add
``normalise_name(<directory name>): "<url>"`` below with the date checked.
"""
from __future__ import annotations

import re

# Likely locations for an ICB's meetings / governance landing page, relative
# to the ICB site origin. Tried in order; a 404 is expected and unremarkable,
# exactly as in m09 / m32. Covers the Board *and* the standing committees,
# because m34 captures all of them.
MEETING_PATHS: tuple[str, ...] = (
    "/",
    "/about-us/our-icb-board",
    "/about-us/our-icb-board/",
    "/about-us/icb-board",
    "/about-us/board-meetings",
    "/about-us/board-meetings-and-papers",
    "/about-us/governance/board-meetings",
    "/about-us/corporate-governance",
    "/about-us/how-we-work/governance",
    "/about-us/our-committees",
    "/about-us/committees",
    "/who-we-are/our-board",
    "/who-we-are/board-and-committees",
    "/get-involved/board-meetings",
    "/publications/board-papers",
    "/publications/governance",
    "/publications/committee-papers",
    "/board-and-committee-papers",
    "/board-meetings-and-papers",
)

# A link worth following one hop (m32's pattern, widened for committees): its
# text or URL carries a governance word but points at a page, not a document.
GOVERNANCE_VOCAB = re.compile(
    r"board[\s\-]?(?:meeting|paper|member)|committee|governance|"
    r"agenda|minutes|meeting[\s\-]?paper", re.IGNORECASE)


def normalise_name(name: str) -> str:
    """An ICB name reduced to its distinguishing words so the NHS England
    directory's rendering and a registry key resolve the same.

    'NHS Nottingham and Nottinghamshire Integrated Care Board',
    'Nottingham and Nottinghamshire ICB' and
    'Nottingham & Nottinghamshire' all key alike.
    """
    text = (name or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(
        r"\b(nhs|integrated care board|integrated care system|icb|ics)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Hand-verified meetings/governance pages, keyed by normalise_name(). Seeded
# with the one entry the module was built from; the rest come from the
# directory + path probe until a person verifies and commits them.
#
#   Nottingham and Nottinghamshire — https://notts.icb.nhs.uk/about-us/our-icb-board/
#   confirmed loading 2026-08-31 (the page in the request that prompted m34)
VERIFIED_BOARD_URLS: dict[str, str] = {
    "nottingham and nottinghamshire": "https://notts.icb.nhs.uk/about-us/our-icb-board/",
}

# NHS ODS 3-character codes, keyed by normalise_name(). Left empty rather than
# guessed: the ODS code is provenance and belongs here only once read from the
# NHS England ODS list. NULL in integrated_care_boards.ods_code until then.
ODS_CODES: dict[str, str] = {}


def board_url_for(name: str) -> str | None:
    return VERIFIED_BOARD_URLS.get(normalise_name(name))


def ods_code_for(name: str) -> str | None:
    return ODS_CODES.get(normalise_name(name))
