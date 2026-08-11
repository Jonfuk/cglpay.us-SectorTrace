from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import alaveteli

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def request_detail() -> dict:
    return json.loads((FIXTURES / "wdtk_request_detail.json").read_text(encoding="utf-8"))


@pytest.fixture
def feed_page() -> list:
    """A slice of a real /feed/search/ response, captured 2026-08-11."""
    return json.loads((FIXTURES / "wdtk_feed_search.json").read_text(encoding="utf-8"))


# --- the happy path -------------------------------------------------------------

def test_parse_info_request_from_fixture(request_detail):
    outcome = alaveteli.parse_info_request(request_detail)
    assert outcome.failures == []
    rec = outcome.record

    assert rec["external_id"] == "884213"
    assert rec["request_slug"] == "substance_misuse_service_budget_2"
    assert rec["request_url"] == (
        "https://www.whatdotheyknow.com/request/substance_misuse_service_budget_2")
    assert rec["subject"].startswith("Substance misuse service budget")
    assert rec["authority_name"] == "Liverpool City Council"
    assert rec["authority_slug"] == "liverpool_city_council"
    assert rec["status"] == "partially_successful"
    assert rec["disclosed"] is True
    assert rec["description"].startswith("Please provide the total commissioned spend")


def test_response_text_takes_responses_only_not_our_own_messages(request_detail):
    """`sent`, `followup_sent` and `comment` events share the timeline with
    responses. Including them would file the requester's own words as the
    authority's answer.
    """
    texts = alaveteli.extract_response_texts(request_detail)
    assert len(texts) == 2
    assert texts[0].startswith("Total commissioned spend")
    assert "section 43(2)" in texts[1]
    joined = alaveteli.parse_info_request(request_detail).record["response_text"]
    assert joined == "\n\n---\n\n".join(texts)
    assert "another user" not in joined


def test_trailing_z_timestamp_is_parsed_not_failed(request_detail):
    """updated_at in the fixture ends in 'Z', which 3.10's fromisoformat
    rejects outright.
    """
    rec = alaveteli.parse_info_request(request_detail).record
    assert rec["request_date"].startswith("2026-03-24T09:12:44")
    assert rec["last_updated"].startswith("2026-05-02T14:38:01")


# --- the pipeline's NULL-not-default rule ----------------------------------------

def test_missing_fields_are_none_never_empty_string():
    outcome = alaveteli.parse_info_request({"info_request": {"id": 1, "title": "  "}})
    rec = outcome.record
    assert rec["subject"] is None
    assert rec["authority_name"] is None
    assert rec["description"] is None
    assert rec["status"] is None
    assert "" not in rec.values()


def test_unknown_described_state_is_nulled_and_logged():
    """The vocabulary is observed, not exhaustive. An unrecognised state must
    surface in parse_failures rather than flow into a campaign figure.
    """
    outcome = alaveteli.parse_info_request(
        {"info_request": {"id": 2, "url_title": "x", "described_state": "escalated_to_regulator"}})
    assert outcome.record["status"] is None
    assert outcome.record["disclosed"] is None
    assert [f.field_name for f in outcome.failures] == ["described_state"]
    assert "escalated_to_regulator" in outcome.failures[0].raw_fragment


def test_display_status_is_never_used_as_a_fallback_for_status():
    """display_status is humanised prose. Falling back to it would put
    "Awaiting response" in a column the rest of the pipeline matches against
    machine values.
    """
    outcome = alaveteli.parse_info_request(
        {"info_request": {"id": 3, "url_title": "y", "display_status": "Awaiting response"}})
    assert outcome.record["status"] is None
    assert outcome.failures == []


def test_bad_timestamp_is_recorded_as_a_failure():
    outcome = alaveteli.parse_info_request(
        {"info_request": {"id": 4, "url_title": "z", "created_at": "24th March 2026"}})
    assert outcome.record["request_date"] is None
    assert [f.field_name for f in outcome.failures] == ["created_at"]


def test_listing_entry_without_events_distinguishes_unknown_from_zero():
    """A listing entry has no events. response_count must be None ("not
    fetched") rather than 0 ("fetched, no response").
    """
    listing = alaveteli.parse_info_request({"info_request": {"id": 5, "url_title": "a"}}).record
    assert listing["response_count"] is None
    assert listing["response_text"] is None

    fetched = alaveteli.parse_info_request(
        {"info_request": {"id": 6, "url_title": "b",
                          "info_request_events": [{"event_type": "sent"}]}}).record
    assert fetched["response_count"] == 0


# --- Alaveteli's inconsistent wrapping -------------------------------------------

def test_bare_and_wrapped_objects_parse_identically():
    inner = {"id": 7, "url_title": "c", "title": "T", "described_state": "successful"}
    assert (alaveteli.parse_info_request(inner).record
            == alaveteli.parse_info_request({"info_request": inner}).record)


def test_flat_public_body_name_is_accepted():
    outcome = alaveteli.parse_info_request(
        {"info_request": {"id": 8, "url_title": "d", "public_body_name": "Kent County Council"}})
    assert outcome.record["authority_name"] == "Kent County Council"
    assert outcome.record["authority_slug"] is None


def test_unidentifiable_object_yields_no_record():
    outcome = alaveteli.parse_info_request({"something_else": {"foo": 1}})
    assert outcome.record is None
    assert outcome.failures[0].field_name == "info_request"


# --- authorities ------------------------------------------------------------------

def test_parse_authority(request_detail):
    body = {"public_body": request_detail["info_request"]["public_body"]}
    rec = alaveteli.parse_authority(body).record
    assert rec["wdtk_body_slug"] == "liverpool_city_council"
    assert rec["authority_name"] == "Liverpool City Council"
    assert rec["request_count"] == 4127


def test_parse_authority_rejects_non_integer_count():
    outcome = alaveteli.parse_authority(
        {"public_body": {"url_name": "x", "name": "X", "info_requests_count": "lots"}})
    assert outcome.record["request_count"] is None
    assert [f.field_name for f in outcome.failures] == ["info_requests_count"]


def test_disclosing_states_are_a_subset_of_the_known_vocabulary():
    assert alaveteli.DISCLOSING_STATES <= alaveteli.KNOWN_DESCRIBED_STATES


# --- the /feed/search/ shape -------------------------------------------------------

def test_parse_feed_page_reads_every_event(feed_page):
    records, failures = alaveteli.parse_feed_page(feed_page)
    assert len(records) == len(feed_page)
    assert failures == []


def test_feed_event_takes_the_requests_state_not_the_events(feed_page):
    """On a search result the event's own described_state is null and the
    nested request's is populated. Reading the event's would null every row.
    """
    surrey = next(r for r in alaveteli.parse_feed_page(feed_page)[0]
                  if r["authority_slug"] == "surrey_county_council")
    assert surrey["status"] == "waiting_response"
    assert surrey["disclosed"] is False
    assert surrey["ons_code"] == "E10000030"
    assert surrey["request_url"].startswith("https://www.whatdotheyknow.com/request/")
    assert surrey["request_url"].endswith(surrey["request_slug"])


def test_feed_event_never_yields_response_text(feed_page):
    """The feed carries a truncated snippet, not a message body. A record
    that offered `response_text` would let a fragment become quotable.
    """
    for rec in alaveteli.parse_feed_page(feed_page)[0]:
        assert "response_text" not in rec
    assert any(r["snippet"] for r in alaveteli.parse_feed_page(feed_page)[0])


def test_snippet_highlight_markup_is_stripped(feed_page):
    records, _ = alaveteli.parse_feed_page(feed_page)
    joined = " ".join(r["snippet"] or "" for r in records)
    assert "<span" not in joined and "</span>" not in joined
    assert "highlight" not in joined


def test_gss_comes_from_the_tag_pairs_not_a_tag_string():
    """The feed's tags are [key, value] pairs, unlike the authority CSV's
    single tag string. Sharing one accessor would hide a change to either.
    """
    assert alaveteli.gss_from_tags([["gss", "E08000019"]]) == "E08000019"
    assert alaveteli.gss_from_tags([["statistical_geography", "E06000046"]]) == "E06000046"
    assert alaveteli.gss_from_tags([["nhs", None], ["wikidata", "Q1"]]) is None
    assert alaveteli.gss_from_tags("gss:E08000019") is None
    assert alaveteli.gss_from_tags(None) is None


def test_body_without_a_gss_tag_yields_no_ons_code(feed_page):
    """NHS trusts and police forces appear in results. They have no GSS code,
    so they must not join to an authority.
    """
    trust = next(r for r in alaveteli.parse_feed_page(feed_page)[0]
                 if r["authority_slug"] == "north_east_ambulance_service_nhs_foundation_trust")
    assert trust["ons_code"] is None
    assert trust["authority_name"] == "North East Ambulance Service NHS Foundation Trust"


def test_non_response_event_types_are_kept_and_labelled(feed_page):
    """A search matches outgoing messages too. They are real discoveries, so
    they are kept — but the event type must be recorded so the caller can
    tell an authority's reply from the requester's own words.
    """
    varieties = {r["event_type"] for r in alaveteli.parse_feed_page(feed_page)[0]}
    assert "sent" in varieties
    assert "response" in varieties


def test_attention_requested_is_now_a_known_state(feed_page):
    """Observed live on 2026-08-11. It was previously this module's example
    of a state that should fail, which is why it is asserted explicitly.
    """
    assert "attention_requested" in alaveteli.KNOWN_DESCRIBED_STATES
    rec = next(r for r in alaveteli.parse_feed_page(feed_page)[0]
               if r["authority_slug"] == "scottish_government")
    assert rec["status"] == "attention_requested"
    assert rec["disclosed"] is False


@pytest.mark.parametrize("state", ["attention_requested", "user_withdrawn"])
def test_states_observed_in_the_first_live_run_are_known(state):
    """Both were admitted only after appearing in parse_failures from a real
    fetch, which is the rule this vocabulary documents. Neither means the
    authority released anything.
    """
    assert state in alaveteli.KNOWN_DESCRIBED_STATES
    assert state not in alaveteli.DISCLOSING_STATES
    outcome = alaveteli.parse_info_request(
        {"info_request": {"id": 1, "url_title": "x", "described_state": state}})
    assert outcome.failures == []
    assert outcome.record["status"] == state
    assert outcome.record["disclosed"] is False


def test_feed_event_without_a_request_yields_no_record():
    outcome = alaveteli.parse_feed_event({"id": 1, "event_type": "response"})
    assert outcome.record is None
    assert outcome.failures[0].field_name == "info_request"


def test_one_malformed_event_does_not_discard_the_page(feed_page):
    records, failures = alaveteli.parse_feed_page([*feed_page, {"id": 9, "event_type": "response"}])
    assert len(records) == len(feed_page)
    assert [f.field_name for f in failures] == ["info_request"]


def test_feed_page_must_be_an_array():
    records, failures = alaveteli.parse_feed_page({"events": []})
    assert records == []
    assert failures[0].field_name == "feed_page"
