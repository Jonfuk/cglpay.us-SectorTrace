"""Hand-verified registry of provider pay-relevant web pages, for Module 22.

The D-05 lesson applied to providers: an answer about where an organisation
publishes is registry-quality only when someone verified it, and it belongs
in a committed file — not in a database table the pipeline reads its own
guesses back from, and not in a session note that evaporates.

Every entry here was fetched and answered at verification time (2026-08-15)
by a human; the note records what was verified. The module treats a page
that stops answering as `pay_page_unavailable`, never as silence.

Mergers matter here, and are stated in the notes rather than smoothed over:
Richmond Fellowship's domain now serves Waythrough (it merged into
Waythrough in October 2024), Humankind merged the same way, and WDP's
domain now serves Via (the two merged in 2020). Each provider's careers
half is the merged organisation's, with the note saying which.

The entry point for each provider is deliberately small: the crawl in m22
follows same-host links whose anchor or URL carries the pay vocabulary, so
the registry names the pages that were verified and the crawl finds the
rest of the provider's own site.
"""
from __future__ import annotations

# provider_key -> [(page_url, verification note), ...] in crawl order.
PROVIDER_PAY_PAGES: dict[str, list[tuple[str, str]]] = {
    "change_grow_live": [
        ("https://www.changegrowlive.org/", "site root answered; the site 403s "
         "automated clients and its jobs board is a separate host "
         "(careers.changegrowlive.org) — the crawl records the block"),
    ],
    "turning_point": [
        ("https://www.turning-point.co.uk/careers/", "careers hub answered, "
         "linking Benefits and What to expect"),
    ],
    "with_you": [
        ("https://www.wearewithyou.org.uk/careers/", "careers hub answered, "
         "linking the vacancies portal and a benefits page"),
    ],
    "waythrough": [
        ("https://www.waythrough.org.uk/careers/", "careers hub answered, "
         "linking Explore our vacancies"),
    ],
    "humankind": [
        ("https://www.waythrough.org.uk/careers/", "Humankind merged into "
         "Waythrough in October 2024; its careers are Waythrough's"),
    ],
    "richmond_fellowship": [
        ("https://www.waythrough.org.uk/careers/", "the richmondfellowship.org.uk "
         "domain now serves the Waythrough site; merged into Waythrough in "
         "October 2024"),
    ],
    "via": [
        ("https://www.viaorg.uk/work-at-via/", "work-at-via hub answered, "
         "linking Current vacancies, Benefits and Career paths"),
    ],
    "westminster_drug_project": [
        ("https://www.viaorg.uk/work-at-via/", "wdp.org.uk now serves the Via "
         "site — WDP merged into Via in 2020; the careers half is Via's"),
    ],
    "forward_trust": [
        ("https://www.forwardtrust.org.uk/careers/", "careers page answered, "
         "linking Recruitment, Volunteering and Leadership"),
    ],
    "phoenix_futures": [
        ("https://www.phoenix-futures.org.uk/", "site root answered; the "
         "careers-section URLs (Current vacancies, Working at Phoenix) were "
         "not verified at registry time and are left for the crawl to find"),
    ],
    "delphi_medical": [
        ("https://www.delphimedical.co.uk/", "site root answered; the nav "
         "carries Careers > Vacancies"),
    ],
    "inclusion": [
        ("https://www.mpft.nhs.uk/", "Inclusion is part of Midlands Partnership "
         "University NHS Foundation Trust; inclusion-group.co.uk was "
         "unreachable at verification, and the Trust's Working here section "
         "is the entry point"),
    ],
}
