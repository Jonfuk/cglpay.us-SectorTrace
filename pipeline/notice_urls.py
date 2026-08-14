"""Where a procurement notice lives, as opposed to where its bytes came from.

`contracts.source_url` is provenance: the API page that produced the row, a
paginated OCDS cursor. Following it does not reach the notice. This module
holds the other address -- the notice's own page -- and the two ways of
getting it, which are deliberately not the same thing:

  * `published_notice_url()` reads it out of the release. The source said it,
    so it is a captured fact and m01 stores it in `contracts.notice_web_url`.

  * `notice_page_url()` builds it from the notice id. Nothing stores this. The
    portal computes it at read time for the rows where the release published
    no link, and labels it as constructed where it is shown, because a
    constructed URL sitting in a column next to a captured one is
    indistinguishable from it a year later.

The construction rule is not a guess. Both services were checked against
every OCDS page in `data/raw/`: of 117,365 published notice URLs, 117,317
follow the rule below exactly. Every exception is an attachment path or a
release citing a *different* notice, and both are excluded here.
"""
from __future__ import annotations

import re

# The publishing services, keyed by the `source_system` m01 records.
NOTICE_HOSTS = {
    "find_a_tender": "www.find-tender.service.gov.uk",
    "contracts_finder": "www.contractsfinder.service.gov.uk",
}

# A Contracts Finder release id is the notice GUID with a release sequence
# appended; the notice page is the GUID alone. Find a Tender's release id is
# the notice id unchanged, so it does not match this and falls through.
_CF_NOTICE_ID_RE = re.compile(
    r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-\d+$",
    re.IGNORECASE,
)


def notice_slug(notice_id: str | None) -> str | None:
    """The notice's identifier in its service's URL space."""
    if not notice_id:
        return None
    match = _CF_NOTICE_ID_RE.match(notice_id)
    return match.group(1) if match else notice_id


def notice_page_url(source_system: str | None, notice_id: str | None) -> str | None:
    """The notice page this id would have. Constructed -- never stored, and
    never shown without saying so."""
    host = NOTICE_HOSTS.get(source_system or "")
    slug = notice_slug(notice_id)
    if not host or not slug:
        return None
    return f"https://{host}/Notice/{slug}"


def published_notice_url(release: dict, source_system: str) -> str | None:
    """The address the release itself publishes for this notice, or None.

    The documents array is not a list of notice pages. It carries attachments
    (`/Notice/Attachment/...`, `/Notice/SupplierAttachment/...`), bidding
    packs on third-party portals, and occasionally a link to a different
    notice. So this does not take the first plausible link: it accepts a
    document only when it is exactly this notice's page on the publishing
    service's own host, and returns None otherwise.

    None is the ordinary outcome -- 84% of collected rows -- and it is not a
    parse failure. It means the release named no notice page, which is a fact
    about the release.
    """
    wanted = notice_page_url(source_system, release.get("id"))
    if not wanted:
        return None

    documents = []
    for section in ("contracts", "awards"):
        for entry in release.get(section) or []:
            documents.extend(entry.get("documents") or [])
    documents.extend((release.get("tender") or {}).get("documents") or [])

    for document in documents:
        if (document.get("url") or "").strip() == wanted:
            return wanted
    return None
