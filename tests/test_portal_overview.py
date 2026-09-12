"""The homepage does not over-fetch to draw its charts.

`overview.js`'s "largest notices in the corpus" section draws a 10-bar chart
and a 5-row table. Everything it renders — `value_concentration`,
`largest_matched_to_provider`, the corpus-wide concentration line — is
computed server-side over the whole corpus and does not depend on the
`contracts` route's `limit`. The one limit-bound field it reads is `notices`,
and only for provenance (deduped, at most six URLs shown) and its latest
retrieval date. Requesting 500 notices to use ten of them made the homepage's
single biggest transfer ~98% waste.

Pinned against the source, this suite's offline style.
"""
from __future__ import annotations

import re
from pathlib import Path

OVERVIEW = (Path(__file__).resolve().parent.parent
            / "pipeline" / "web" / "static" / "public" / "js" / "pages" / "overview.js")


def test_top_contracts_requests_a_bounded_notice_window():
    source = OVERVIEW.read_text(encoding="utf-8")
    match = re.search(r"fetchJSON\('contracts', \{ limit: (\d+) \}\)", source)
    assert match, "overview.js no longer fetches the contracts route with an explicit limit"
    assert int(match.group(1)) <= 25, (
        "the overview's top-contracts section is fetching a wide notice window "
        f"({match.group(1)}) again — it only reads value_concentration, "
        "largest_matched_to_provider and up to six provenance URLs")
