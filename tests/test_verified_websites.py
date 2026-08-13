"""An answer given in the review UI, written where git can see it.

On 2026-08-13 `authority_url_overrides` was emptied and 191 verified URLs went
with it. 105 were recovered — not from a backup, but because a verification
document happened to record them. The other ~86 had only ever existed in that
table and are gone.

So a resolution now writes twice: the override row, which is live and
attributed, and a tracked JSON file, which is the copy that outlives the
warehouse. These tests are about the second one existing, being read back, and
never being able to break the first.
"""
from __future__ import annotations

import json

import pytest

from pipeline import authority_websites


@pytest.fixture(autouse=True)
def _fresh_cache():
    """The loader caches on mtime, and tmp files can share one."""
    authority_websites._VERIFIED_CACHE.update(mtime=None, path=None, entries={})
    yield
    authority_websites._VERIFIED_CACHE.update(mtime=None, path=None, entries={})


def test_an_answer_is_written_to_the_tracked_file(settings):
    authority_websites.record_verified_website(
        ons_code="E10000030", name="Surrey", field="committee_url",
        url="https://democracy.surreycc.gov.uk", committee_system="moderngov",
        verified_by="Jon", verified_on="2026-08-13", settings=settings)

    written = json.loads(settings.verified_websites_path.read_text(encoding="utf-8"))
    entry = written["authorities"]["E10000030"]
    assert entry["committee_url"] == "https://democracy.surreycc.gov.uk"
    assert entry["committee_system"] == "moderngov"
    assert entry["verified_by"] == "Jon"
    assert entry["name"] == "Surrey"


def test_it_is_read_back_as_a_registry_entry(settings, monkeypatch):
    monkeypatch.setattr(authority_websites, "get_settings", lambda: settings,
                         raising=False)
    from pipeline import config
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    authority_websites.record_verified_website(
        ons_code="E10000030", name="Surrey", field="committee_url",
        url="https://democracy.surreycc.gov.uk", committee_system="moderngov",
        verified_by="Jon", verified_on="2026-08-13", settings=settings)

    found = authority_websites.verified_websites(settings)["E10000030"]
    assert found.committee_url == "https://democracy.surreycc.gov.uk"
    assert found.source == "human_verified", (
        "it is a person's answer, not the hand-written seed registry")


def test_answering_one_question_does_not_erase_the_other(settings):
    """The same rule the override row follows: base_url and committee_url are
    two questions and a reviewer may answer them on different days."""
    authority_websites.record_verified_website(
        ons_code="E10000030", name="Surrey", field="committee_url",
        url="https://democracy.surreycc.gov.uk", committee_system="moderngov",
        verified_by="Jon", verified_on="2026-08-13", settings=settings)
    authority_websites.record_verified_website(
        ons_code="E10000030", name="Surrey", field="base_url",
        url="https://www.surreycc.gov.uk", committee_system=None,
        verified_by="Sam", verified_on="2026-08-14", settings=settings)

    entry = json.loads(
        settings.verified_websites_path.read_text(encoding="utf-8"))["authorities"]["E10000030"]
    assert entry["committee_url"] == "https://democracy.surreycc.gov.uk"
    assert entry["base_url"] == "https://www.surreycc.gov.uk"
    assert entry["committee_system"] == "moderngov", "not cleared by the second answer"


def test_the_file_is_sorted_and_carries_its_own_explanation(settings):
    for code in ("E10000030", "E06000001", "E09000002"):
        authority_websites.record_verified_website(
            ons_code=code, name=code, field="base_url",
            url=f"https://{code.lower()}.example", committee_system=None,
            verified_by="Jon", verified_on="2026-08-13", settings=settings)

    raw = json.loads(settings.verified_websites_path.read_text(encoding="utf-8"))
    assert list(raw["authorities"]) == sorted(raw["authorities"]), (
        "sorted so a diff shows the answer added, not the whole file moving")
    assert "review UI" in raw["note"]


def test_a_missing_file_is_not_an_error(settings):
    assert authority_websites.verified_websites(settings) == {}


def test_a_corrupt_file_does_not_take_the_modules_down(settings):
    settings.verified_websites_path.parent.mkdir(parents=True, exist_ok=True)
    settings.verified_websites_path.write_text("{not json", encoding="utf-8")

    assert authority_websites.verified_websites(settings) == {}


def test_configured_codes_include_answers_given_in_the_ui(settings, monkeypatch):
    from pipeline import config
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    before = authority_websites.configured_ons_codes()
    authority_websites.record_verified_website(
        ons_code="E99999001", name="Somewhere", field="committee_url",
        url="https://democracy.somewhere.example", committee_system="moderngov",
        verified_by="Jon", verified_on="2026-08-13", settings=settings)

    assert "E99999001" in authority_websites.configured_ons_codes()
    assert "E99999001" not in before


def test_the_shipped_file_is_valid_if_it_exists():
    """The real one, tracked in git. It is hand-editable by design, so a
    trailing comma in it would break Modules 9 and 10 on the next run."""
    from pipeline.config import REPO_ROOT

    path = REPO_ROOT / "pipeline" / "verified_websites.json"
    if not path.exists():
        pytest.skip("nothing has been answered in the UI yet")

    raw = json.loads(path.read_text(encoding="utf-8"))
    for code, entry in raw.get("authorities", {}).items():
        assert code.startswith("E") and len(code) == 9, code
        assert entry.get("verified_on"), f"{code} does not say when"
        for field in ("base_url", "committee_url"):
            if entry.get(field):
                assert entry[field].startswith("http"), f"{code}.{field}"
