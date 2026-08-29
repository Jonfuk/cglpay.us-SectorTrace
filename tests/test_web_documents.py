"""Document search (BETA-022): the public route over the document-analysis
pipeline's already-parsed, already-searchable text (docs/document-analysis.md).

The one thing this file exists to pin down: `document_search()` reads from an
explicit source-system allowlist, not "everything in document_records" —
`_public()` alone would not catch a future source sharing this schema that
does carry restricted personal data (PFD report bodies, tribunal judgment
text), because `document_records`/`document_elements` are not
`restricted_`-prefixed tables. A document from an unlisted source system must
never be returned here, even when its text matches the query exactly.
"""
from __future__ import annotations

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.web import public_queries
from pipeline.web.queries import QueryError


def _reference(evidence_id: str, source_system: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-19T00:00:00+00:00", http_status=200,
        payload_sha256="a" * 64,
        raw_object_path=f"data/raw/{source_system}/" + "a" * 64 + ".pdf",
        mime_type="application/pdf",
    )


def _seed_document(conn, settings, *, evidence_id: str, source_system: str,
                    document_type: str, text: str, title: str | None = None) -> None:
    reference = _reference(evidence_id, source_system)
    repository.upsert_evidence(conn, reference)
    document_id = repository.upsert_document(
        conn, reference, document_type, "fixture", 1.0, "report.pdf",
        "application/pdf", 1, title)
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("PARAGRAPH", 1, text=text, page_number=1),
    ])
    repository.persist_parse(
        conn, document_id, parsed, "config", None, "GOOD", {}, [], settings)


def test_document_search_finds_committee_paper_text(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-committee", source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Substance misuse recruitment vacancies rose in Q3.",
        title="Cabinet committee minutes")

    result = public_queries.document_search(conn, query="recruitment")

    assert result["query"] == "recruitment"
    assert result["caveat"]
    assert len(result["results"]) == 1
    row = result["results"][0]
    assert row["document_type"] == "COMMITTEE_PAPER"
    assert row["title"] == "Cabinet committee minutes"
    assert row["page_number"] == 1
    assert "recruitment" in row["text"].lower()
    assert row["source_url"] == "https://example.test/ev-committee"


def test_document_search_finds_cdp_document_text(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-cdp", source_system="cdp_document_promotion",
        document_type="UNKNOWN", text="Partnership board reviewed naloxone distribution figures.")

    result = public_queries.document_search(conn, query="naloxone")

    assert len(result["results"]) == 1
    assert result["results"][0]["document_id"]


def test_document_search_excludes_source_systems_outside_the_allowlist(conn, settings):
    """A document from any source not in DOCUMENT_SEARCH_SOURCES must never
    surface here, even on an exact text match. This is the actual safety
    boundary for the route (see public_queries.py's own comment on why
    `_public()` alone is not enough)."""
    _seed_document(
        conn, settings, evidence_id="ev-restricted-shaped", source_system="pfd_report_promotion",
        document_type="PFD_REPORT", text="A very distinctive unique search phrase xyzzyplugh.")
    _seed_document(
        conn, settings, evidence_id="ev-committee-2", source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Nothing to do with the other phrase.")

    result = public_queries.document_search(conn, query="xyzzyplugh")

    assert result["results"] == []


def test_document_search_requires_a_query(conn):
    with pytest.raises(QueryError):
        public_queries.document_search(conn, query="")
    with pytest.raises(QueryError):
        public_queries.document_search(conn, query="   ")


def test_document_search_limit_is_clamped(conn, settings):
    for i in range(3):
        _seed_document(
            conn, settings, evidence_id=f"ev-limit-{i}", source_system="committee_paper_promotion",
            document_type="COMMITTEE_PAPER", text="Budget pressures continue across the service.")

    result = public_queries.document_search(conn, query="budget", limit=1)
    assert len(result["results"]) == 1

    # A limit above the route's own ceiling is clamped, not honoured verbatim —
    # the same discipline as every other public route with a limit parameter.
    result = public_queries.document_search(conn, query="budget", limit=10_000)
    assert len(result["results"]) == 3


def test_document_search_reports_total_beyond_the_limit(conn, settings):
    """`total` counts every matching page, not just the page of results sent —
    the portal says "showing N of M" rather than letting a cut-off list read
    as complete."""
    for i in range(3):
        _seed_document(
            conn, settings, evidence_id=f"ev-total-{i}",
            source_system="committee_paper_promotion",
            document_type="COMMITTEE_PAPER",
            text="Budget pressures continue across the service.")

    result = public_queries.document_search(conn, query="budget", limit=1)

    assert len(result["results"]) == 1
    assert result["total"] == 3

    result = public_queries.document_search(conn, query="budget")
    assert result["total"] == len(result["results"])


def test_document_search_total_respects_the_allowlist(conn, settings):
    """The safety boundary applies to the count too: pages outside the source
    allowlist are invisible to `total`, not merely filtered from the rows."""
    _seed_document(
        conn, settings, evidence_id="ev-count-allowlisted",
        source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="The phrase xyzzyplugh appears here.")
    _seed_document(
        conn, settings, evidence_id="ev-count-excluded",
        source_system="pfd_report_promotion",
        document_type="PFD_REPORT", text="The phrase xyzzyplugh appears there too.")

    result = public_queries.document_search(conn, query="xyzzyplugh")

    assert result["total"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["source_url"] == "https://example.test/ev-count-allowlisted"


def test_document_search_snippet_is_centred_on_the_match(conn, settings):
    """A mid-page match must be visible from the snippet alone. Before this,
    the portal truncated from character 0, so a reader could be shown a page
    whose reason for matching was nowhere in what they could see."""
    # Distinct numbered padding, so an assertion can prove the snippet's
    # window opens near the match rather than anywhere in a repeated phrase.
    padding = "".join(
        f"Sentence {i:02d} records routine committee business. "
        for i in range(1, 17))
    closing = " Further routine matters were recorded for the minute." * 4
    text = padding + "The recruitment freeze begins in April." + closing
    assert len(text) > 320
    _seed_document(
        conn, settings, evidence_id="ev-snippet",
        source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text=text, title="Long minutes")

    row = public_queries.document_search(conn, query="recruitment")["results"][0]

    assert "recruitment" in row["snippet"].lower()
    assert len(row["snippet"]) <= 321
    assert row["snippet"].startswith("…")
    assert "Sentence 01" not in row["snippet"]
    # The full page text still ships alongside it — the snippet is a window,
    # not a replacement, and exports/other consumers keep getting everything.
    assert row["text"] == text


def test_document_search_short_text_is_returned_whole(conn, settings):
    """A page shorter than the snippet window needs no windowing — and no
    ellipsis pretending something was cut."""
    _seed_document(
        conn, settings, evidence_id="ev-short",
        source_system="cdp_document_promotion",
        document_type="UNKNOWN", text="Naloxone provision expanded.")

    row = public_queries.document_search(conn, query="naloxone")["results"][0]

    assert row["snippet"] == "Naloxone provision expanded."
    assert "…" not in row["snippet"]


def test_document_search_offset_pages_through_the_ranked_list(conn, settings):
    """Offset windows tile the ranked list without overlap, while `total`
    stays the size of the whole match set — the contract the portal's
    "show more" button is built on."""
    for i in range(5):
        _seed_document(
            conn, settings, evidence_id=f"ev-page-{i}",
            source_system="committee_paper_promotion",
            document_type="COMMITTEE_PAPER",
            text=f"Budget pressures continue across service area {i}.")

    pages = [
        public_queries.document_search(conn, query="budget", limit=2, offset=o)
        for o in (0, 2, 4)
    ]

    ids = [[row["document_id"] for row in page["results"]] for page in pages]
    flattened = [doc_id for page in ids for doc_id in page]
    assert len(flattened) == len(set(flattened)), "windows overlapped"

    # The three windows tile exactly the same match set an unpaged query sees.
    reference = public_queries.document_search(conn, query="budget", limit=50)
    assert sorted(flattened) == sorted(
        row["document_id"] for row in reference["results"])

    for page in pages:
        assert page["total"] == 5


def test_document_search_offset_past_the_end_is_empty_not_an_error(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-tail",
        source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Budget pressures continue.")

    result = public_queries.document_search(conn, query="budget", limit=2, offset=5)

    assert result["results"] == []
    assert result["total"] == 1


def test_document_search_negative_offset_clamps_to_zero(conn, settings):
    """PostgreSQL raises on a negative OFFSET and SQLite walks off the front
    of its ranked list silently; neither is a behaviour worth preserving."""
    _seed_document(
        conn, settings, evidence_id="ev-clamp",
        source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Budget pressures continue.")

    clamped = public_queries.document_search(conn, query="budget", limit=2, offset=-9)
    plain = public_queries.document_search(conn, query="budget", limit=2)

    assert clamped["offset"] == 0
    assert ([r["document_id"] for r in clamped["results"]]
            == [r["document_id"] for r in plain["results"]])


def test_document_search_quoted_phrase_anchors_the_snippet(conn, settings):
    """A quoted phrase is matched by the index as a unit, so the snippet
    window should be anchored on the phrase itself — not on whichever of its
    words happens to appear earliest."""
    padding = "".join(
        f"Sentence {i:02d} records routine committee business. "
        for i in range(1, 17))
    # "sleeping" alone appears early; the phrase appears late, with more than
    # a full snippet-radius (_SNIPPET_RADIUS = 140) of filler between them, so
    # an anchored window cannot hold both.
    text = (padding + "A sleeping brief was mentioned once. "
            + "Interim procedural business was recorded while the board "
            + "considered the papers, and the interval was used for further "
            + "routine administration of the agenda. "
            + "The rough sleeping duty was then discussed. " + "More notes. " * 6)
    _seed_document(
        conn, settings, evidence_id="ev-phrase",
        source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text=text, title="Phrase minutes")

    row = public_queries.document_search(conn, query='"sleeping duty"')["results"][0]

    assert "sleeping duty" in row["snippet"]
    assert "sleeping brief" not in row["snippet"]


# --- BETA-041: facets, filters and ranked, stable pagination ---------------


def _publish(conn, evidence_id: str, published_at: str) -> None:
    conn.execute("UPDATE document_records SET published_at = ? WHERE evidence_id = ?",
                 (published_at, evidence_id))
    conn.commit()


def _facet_scene(conn, settings) -> None:
    """Four committee papers and two CDP documents, all matching "budget"."""
    for i in range(4):
        _seed_document(
            conn, settings, evidence_id=f"ev-cp-{i}",
            source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
            text=f"Budget pressures continue across service area {i}.")
        _publish(conn, f"ev-cp-{i}", f"202{i}-05-01")
    for i in range(2):
        _seed_document(
            conn, settings, evidence_id=f"ev-cdp-{i}",
            source_system="cdp_document_promotion", document_type="PARTNERSHIP_MINUTES",
            text=f"Budget allocation for the partnership, note {i}.")
        _publish(conn, f"ev-cdp-{i}", "2025-05-01")


def test_document_search_reports_facet_counts(conn, settings):
    _facet_scene(conn, settings)

    result = public_queries.document_search(conn, query="budget")

    by_source = {row["value"]: row["count"] for row in result["facets"]["source_system"]}
    assert by_source == {"committee_paper_promotion": 4, "cdp_document_promotion": 2}
    by_type = {row["value"]: row["count"] for row in result["facets"]["document_type"]}
    assert by_type == {"COMMITTEE_PAPER": 4, "PARTNERSHIP_MINUTES": 2}


def test_document_search_source_system_facet_filters_results(conn, settings):
    _facet_scene(conn, settings)

    result = public_queries.document_search(
        conn, query="budget", source_system="cdp_document_promotion")

    assert result["total"] == 2
    assert {r["source_system"] for r in result["results"]} == {"cdp_document_promotion"}
    # The facet lists still show every bucket, so the reader can switch back.
    by_source = {row["value"]: row["count"] for row in result["facets"]["source_system"]}
    assert by_source == {"committee_paper_promotion": 4, "cdp_document_promotion": 2}
    assert result["filters"]["source_system"] == "cdp_document_promotion"


def test_document_search_document_type_filters_results_but_not_facets(conn, settings):
    _facet_scene(conn, settings)

    result = public_queries.document_search(
        conn, query="budget", document_type="COMMITTEE_PAPER")

    assert result["total"] == 4
    assert {r["document_type"] for r in result["results"]} == {"COMMITTEE_PAPER"}
    by_type = {row["value"]: row["count"] for row in result["facets"]["document_type"]}
    assert by_type == {"COMMITTEE_PAPER": 4, "PARTNERSHIP_MINUTES": 2}


def test_document_search_rejects_a_source_system_outside_the_allowlist(conn, settings):
    _facet_scene(conn, settings)
    with pytest.raises(QueryError):
        public_queries.document_search(
            conn, query="budget", source_system="pfd_report_promotion")


def test_document_search_year_bounds_filter_on_published_at(conn, settings):
    _facet_scene(conn, settings)

    result = public_queries.document_search(
        conn, query="budget", year_from="2021", year_to="2023")

    # ev-cp-1 (2021), ev-cp-2 (2022), ev-cp-3 (2023); ev-cp-0 is 2020 and the
    # CDP pair is 2025.
    assert result["total"] == 3
    assert result["filters"]["year_from"] == "2021"
    assert result["filters"]["year_to"] == "2023"


def test_document_search_year_bound_excludes_pages_with_no_published_date(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-dated",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        text="Budget report for the year.")
    _publish(conn, "ev-dated", "2024-01-01")
    _seed_document(
        conn, settings, evidence_id="ev-undated",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        text="Budget report with no publication date recorded.")

    result = public_queries.document_search(conn, query="budget", year_from="2024")

    assert result["total"] == 1
    assert result["results"][0]["source_url"] == "https://example.test/ev-dated"


def test_document_search_since_retrieved_at_filters_on_collection_time(conn, settings):
    # _reference() stamps retrieved_at at 2026-08-19; move one earlier.
    _seed_document(
        conn, settings, evidence_id="ev-fresh",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        text="Budget matters, freshly collected.")
    _seed_document(
        conn, settings, evidence_id="ev-stale",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        text="Budget matters, collected long ago.")
    conn.execute("UPDATE evidence_records SET retrieved_at = ? WHERE evidence_id = ?",
                 ("2026-01-01T00:00:00+00:00", "ev-stale"))
    conn.commit()

    result = public_queries.document_search(
        conn, query="budget", since_retrieved_at="2026-06-01T00:00:00+00:00")

    assert result["total"] == 1
    assert result["results"][0]["source_url"] == "https://example.test/ev-fresh"


def test_document_search_pagination_is_stable_across_calls(conn, settings):
    _facet_scene(conn, settings)

    first = [public_queries.document_search(conn, query="budget", limit=2, offset=o)
             for o in (0, 2, 4)]
    again = [public_queries.document_search(conn, query="budget", limit=2, offset=o)
             for o in (0, 2, 4)]

    order_one = [r["document_id"] for page in first for r in page["results"]]
    order_two = [r["document_id"] for page in again for r in page["results"]]
    assert order_one == order_two
    assert len(set(order_one)) == 6  # every match seen once, no overlap


# --- BETA-042: bounded evidence-context view ------------------------------


def _seed_multi_element(conn, settings, *, evidence_id, source_system, document_type,
                        texts, title=None):
    """A document whose active parse has one element per string in `texts`."""
    reference = _reference(evidence_id, source_system)
    repository.upsert_evidence(conn, reference)
    document_id = repository.upsert_document(
        conn, reference, document_type, "fixture", 1.0, "report.pdf",
        "application/pdf", 1, title)
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("PARAGRAPH", i + 1, text=t, page_number=1 + i // 3)
        for i, t in enumerate(texts)
    ])
    repository.persist_parse(
        conn, document_id, parsed, "config", None, "GOOD", {}, [], settings)
    conn.commit()
    return document_id


def _elements(conn, document_id):
    return [dict(r) for r in conn.execute(
        "SELECT de.document_element_id, de.sequence, de.text "
        "FROM document_elements de "
        "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
        "WHERE dv.document_id = ? AND dv.is_active = 1 ORDER BY de.sequence",
        (document_id,))]


def test_document_context_windows_around_the_anchor(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx", source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER",
        texts=[f"Paragraph number {i}." for i in range(10)], title="Ten paragraphs")
    elements = _elements(conn, document_id)
    anchor = elements[5]

    result = public_queries.document_context(
        conn, document_id, element_id=anchor["document_element_id"], context=2)

    seqs = [e["sequence"] for e in result["elements"]]
    assert seqs == [4, 5, 6, 7, 8]  # sequence is 1-based; anchor is index 5
    assert [e["is_anchor"] for e in result["elements"]] == [False, False, True, False, False]
    assert result["has_more_before"] is True
    assert result["has_more_after"] is True
    assert result["anchor_element_id"] == anchor["document_element_id"]
    assert result["title"] == "Ten paragraphs"
    assert result["source_url"] == "https://example.test/ev-ctx"


def test_document_context_clamps_the_window_at_the_edges(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-edge",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        texts=[f"Line {i}." for i in range(4)])
    elements = _elements(conn, document_id)

    result = public_queries.document_context(
        conn, document_id, element_id=elements[0]["document_element_id"], context=3)

    assert [e["sequence"] for e in result["elements"]] == [1, 2, 3, 4]
    assert result["has_more_before"] is False
    assert result["has_more_after"] is False


def test_document_context_caps_the_context_parameter_at_three(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-cap",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        texts=[f"Row {i}." for i in range(30)])
    elements = _elements(conn, document_id)

    result = public_queries.document_context(
        conn, document_id, element_id=elements[15]["document_element_id"], context=99)

    assert result["context"] == 3
    assert len(result["elements"]) == 7  # 3 + anchor + 3


def test_document_context_without_an_anchor_returns_the_head(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-head",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        texts=[f"Head {i}." for i in range(20)])

    result = public_queries.document_context(conn, document_id, context=3)

    assert [e["sequence"] for e in result["elements"]] == [1, 2, 3, 4, 5, 6, 7]
    assert all(e["is_anchor"] is False for e in result["elements"])


def test_document_context_refuses_a_document_outside_the_allowlist(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-restricted",
        source_system="pfd_report_promotion", document_type="PFD_REPORT",
        texts=["Confidential paragraph one.", "Confidential paragraph two."])

    with pytest.raises(QueryError):
        public_queries.document_context(conn, document_id)


def test_document_context_refuses_an_unknown_document(conn):
    with pytest.raises(QueryError):
        public_queries.document_context(conn, "document-does-not-exist")


def test_document_context_refuses_an_element_from_a_superseded_version(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-reparse",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        texts=["Original paragraph A.", "Original paragraph B."])
    stale_element = _elements(conn, document_id)[0]["document_element_id"]

    # A second parse becomes the active version; the first is superseded.
    reparsed = ParsedDocument("fixture", "2", [
        ParsedElement("PARAGRAPH", 1, text="Reparsed paragraph A.", page_number=1),
        ParsedElement("PARAGRAPH", 2, text="Reparsed paragraph B.", page_number=1),
    ])
    repository.persist_parse(
        conn, document_id, reparsed, "config-2", None, "GOOD", {}, [], settings)
    conn.commit()

    # The active window still works…
    fresh = public_queries.document_context(conn, document_id)
    assert "Reparsed paragraph A." in fresh["elements"][0]["text"]

    # …but the element id from the old version is refused, not silently mapped.
    with pytest.raises(QueryError):
        public_queries.document_context(
            conn, document_id, element_id=stale_element)


def test_document_context_id_matches_the_search_result(conn, settings):
    document_id = _seed_multi_element(
        conn, settings, evidence_id="ev-ctx-search",
        source_system="committee_paper_promotion", document_type="COMMITTEE_PAPER",
        texts=["Nothing here.", "The naloxone budget was raised in Q2.", "Nor here."])

    hit = public_queries.document_search(conn, query="naloxone")["results"][0]
    assert hit["document_id"] == document_id
    assert hit["document_element_id"]

    ctx = public_queries.document_context(
        conn, hit["document_id"], element_id=hit["document_element_id"], context=1)
    anchor = [e for e in ctx["elements"] if e["is_anchor"]]
    assert len(anchor) == 1
    assert "naloxone" in anchor[0]["text"].lower()
