"""Module 36: 360Giving grants (received and made) for tracked providers.

Feasibility: docs/m36-360giving-grantnav-feasibility.md. The fixtures below
are shaped from real, live-verified api.threesixtygiving.org responses
(Change Grow Live's own grants), not invented ones -- including the two
findings that matter for parsing: the same organisation is filed under a
GB-CHC id on one grant and a GB-COH id on another, and award dates arrive in
two different formats from two different publishers.
"""
from __future__ import annotations

import json

import pytest

from pipeline import providers
from pipeline.modules import m36_360giving as tsg
from pipeline.registry import ModuleContext

API = "https://api.threesixtygiving.org/api/v1"


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://api.threesixtygiving.org/robots.txt",
        status_code=404, text="Not Found", is_reusable=True)


def _grant(grant_id: str, *, funder: dict, recipient: dict,
           award_date: str, amount: float = 1000.0,
           licence_name: str = "Creative Commons Attribution 4.0 International (CC BY 4.0)",
           licence_url: str = "https://creativecommons.org/licenses/by/4.0/",
           date_modified: str | None = None) -> dict:
    data = {
        "id": grant_id,
        "title": "A grant",
        "description": "A grant for a good cause.",
        "currency": "GBP",
        "awardDate": award_date,
        "amountAwarded": amount,
        "fundingOrganization": [funder],
        "recipientOrganization": [recipient],
        "grantProgramme": [{"title": "Open Programme"}],
    }
    if date_modified:
        data["dateModified"] = date_modified
    return {
        "grant_id": grant_id,
        "data": data,
        "data_license": {"url": licence_url, "name": licence_name},
    }


def _page(results: list[dict], next_url: str | None = None) -> dict:
    return {"count": len(results), "next": next_url, "previous": None, "results": results}


@pytest.fixture
def target_provider(conn):
    """Change Grow Live, seeded with both a charity and a company number --
    the real shape confirmed live, where the same provider is filed under
    either scheme depending on the grant.
    """
    providers.seed_providers(conn)
    return "change_grow_live"


@pytest.fixture(autouse=True)
def _only_walk_target(monkeypatch, target_provider):
    """Mirrors m04's `_only_walk_seed_companies`: control exactly which
    identifiers a run walks rather than mocking every tracked provider.
    """
    identifiers = [
        (target_provider, "charity_number", "1079327"),
        (target_provider, "company_number", "3861209"),
    ]
    monkeypatch.setattr(tsg, "_target_identifiers", lambda conn: list(identifiers))
    return identifiers


# --- pure helpers --------------------------------------------------------


@pytest.mark.parametrize("scheme,identifier,expected", [
    ("charity_number", "1079327", "GB-CHC-1079327"),
    ("company_number", "3861209", "GB-COH-03861209"),  # normalised, zero-padded
    ("company_number", "03861209", "GB-COH-03861209"),
])
def test_org_id_uses_the_right_prefix_per_scheme(scheme, identifier, expected):
    assert tsg._org_id(scheme, identifier) == expected


def test_org_id_rejects_an_unknown_scheme():
    with pytest.raises(ValueError):
        tsg._org_id("cqc_provider_id", "1-000000001")


@pytest.mark.parametrize("raw,expected", [
    ("2023-03-22", "2023-03-22"),
    ("2020-05-29T00:00:00+00:00", "2020-05-29"),  # real second-publisher shape
    ("2026-02-23T00:00:00Z", "2026-02-23"),
    ("not-a-date", None),
    (None, None),
    ("", None),
])
def test_normalise_date_tolerates_bare_and_full_iso_formats(raw, expected):
    assert tsg._normalise_date(raw) == expected


def test_grant_row_returns_none_without_a_grant_id():
    assert tsg._grant_row({"data": {}}, direction="received", provider_key="x",
                           scheme="charity_number", identifier="1", result=None) is None


def test_grant_row_picks_funder_as_counterparty_when_received():
    entry = _grant("g1", funder={"id": "GB-CHC-1", "name": "A Trust"},
                    recipient={"id": "GB-CHC-2", "name": "Someone Else"},
                    award_date="2023-01-01")
    row = tsg._grant_row(entry, direction="received", provider_key="p",
                          scheme="charity_number", identifier="2", result=_FakeResult())
    assert row["counterparty_org_id"] == "GB-CHC-1"
    assert row["counterparty_name"] == "A Trust"


def test_grant_row_picks_recipient_as_counterparty_when_made():
    entry = _grant("g1", funder={"id": "GB-CHC-1", "name": "A Trust"},
                    recipient={"id": "GB-CHC-2", "name": "Someone Else"},
                    award_date="2023-01-01")
    row = tsg._grant_row(entry, direction="made", provider_key="p",
                          scheme="charity_number", identifier="1", result=_FakeResult())
    assert row["counterparty_org_id"] == "GB-CHC-2"
    assert row["counterparty_name"] == "Someone Else"


class _FakeResult:
    url = "https://api.threesixtygiving.org/api/v1/org/x/grants_received/"
    status_code = 200
    payload_sha256 = "abc123"

    class _Retrieved:
        @staticmethod
        def isoformat():
            return "2026-09-12T00:00:00+00:00"

    retrieved_at = _Retrieved()


# --- end-to-end ------------------------------------------------------------


def test_run_reconciles_by_both_identifier_schemes_and_paginates(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)

    # charity_number org id: two grants received across two pages, exactly
    # the pagination shape the live API uses (a `next` URL carrying its own
    # query string).
    grant_a = _grant("360G-BarnwoodTrust-GF103354",
                      funder={"id": "GB-CHC-1162855", "name": "Barnwood Trust"},
                      recipient={"id": "GB-CHC-1079327", "name": "Change Grow Live"},
                      award_date="2023-03-22", amount=1500.0,
                      licence_name="Creative Commons Public Domain Dedication 1.0 Universal",
                      licence_url="https://creativecommons.org/publicdomain/zero/1.0/",
                      date_modified="2024-02-07T00:00:00Z")
    grant_b = _grant("360G-cabinetoffice-G2-GA-202106432507-20-21",
                      funder={"id": "GB-GOR-D5", "name": "Department for Digital, Culture, Media & Sport"},
                      recipient={"id": "GB-COH-03861209", "name": "CHANGE GROW LIVE"},
                      award_date="2020-05-29T00:00:00+00:00", amount=923.0,
                      licence_name="Open Government Licence 3.0 (United Kingdom)",
                      licence_url="http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")

    next_url = f"{API}/org/GB-CHC-1079327/grants_received/?limit=100&offset=100"
    httpx_mock.add_response(
        url=f"{API}/org/GB-CHC-1079327/grants_received/?limit=100",
        json=_page([grant_a], next_url=next_url))
    httpx_mock.add_response(url=next_url, json=_page([grant_b]))

    # charity_number org id: no grants made (the real, verified result for
    # this organisation).
    httpx_mock.add_response(
        url=f"{API}/org/GB-CHC-1079327/grants_made/?limit=100",
        json=_page([]))

    # company_number org id: this identifier is not known to 360Giving at
    # all for either direction -- a 404, the expected outcome, not a fault.
    httpx_mock.add_response(
        url=f"{API}/org/GB-COH-03861209/grants_received/?limit=100",
        status_code=404, json={"detail": "Not found."})
    httpx_mock.add_response(
        url=f"{API}/org/GB-COH-03861209/grants_made/?limit=100",
        status_code=404, json={"detail": "Not found."})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    tsg.run(ctx)

    rows = conn.execute(
        "SELECT * FROM three_sixty_giving_grants ORDER BY grant_id").fetchall()
    assert len(rows) == 2

    barnwood = next(r for r in rows if r["grant_id"] == "360G-BarnwoodTrust-GF103354")
    assert barnwood["direction"] == "received"
    assert barnwood["provider_key"] == "change_grow_live"
    assert barnwood["matched_scheme"] == "charity_number"
    assert barnwood["matched_identifier"] == "1079327"
    assert barnwood["counterparty_name"] == "Barnwood Trust"
    assert barnwood["amount_awarded"] == 1500.0
    assert barnwood["award_date_raw"] == "2023-03-22"
    assert barnwood["award_date"] == "2023-03-22"
    assert barnwood["date_modified"] == "2024-02-07T00:00:00Z"
    assert barnwood["data_license_name"] == "Creative Commons Public Domain Dedication 1.0 Universal"

    cabinet = next(r for r in rows if "cabinetoffice" in r["grant_id"])
    assert cabinet["award_date_raw"] == "2020-05-29T00:00:00+00:00"
    assert cabinet["award_date"] == "2020-05-29"  # tolerant of the full timestamp
    assert cabinet["date_modified"] is None  # not every grant carries one
    assert cabinet["data_license_name"] == "Open Government Licence 3.0 (United Kingdom)"

    # The 404s on the company-number org id must not become review items --
    # that is the expected outcome for an identifier 360Giving has never
    # seen, not a fault.
    review_items = conn.execute(
        "SELECT * FROM review_queue WHERE module = 'm36_360giving'").fetchall()
    assert not review_items


def test_a_non_404_client_error_is_a_review_item(httpx_mock, settings, conn):
    """A persistent 5xx is retried by the shared client and then raises,
    the same "fail the run loudly" behaviour m21's ASHE 502 case documents --
    this module adds no per-call try/except around that on purpose. A 4xx
    other than 404 (nothing here retries or raises on those) is the case
    this module's own review-item path exists for.
    """
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=f"{API}/org/GB-CHC-1079327/grants_received/?limit=100",
        status_code=403, text="Forbidden")
    httpx_mock.add_response(
        url=f"{API}/org/GB-CHC-1079327/grants_made/?limit=100", json=_page([]))
    httpx_mock.add_response(
        url=f"{API}/org/GB-COH-03861209/grants_received/?limit=100",
        status_code=404, json={"detail": "Not found."})
    httpx_mock.add_response(
        url=f"{API}/org/GB-COH-03861209/grants_made/?limit=100",
        status_code=404, json={"detail": "Not found."})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    tsg.run(ctx)

    review_items = conn.execute(
        "SELECT * FROM review_queue WHERE module = 'm36_360giving' "
        "AND item_type = 'three_sixty_giving_org_unavailable'").fetchall()
    assert len(review_items) == 1
    assert review_items[0]["raw_value"] == "GB-CHC-1079327"
    context = json.loads(review_items[0]["context_json"])
    assert context["direction"] == "received"
    assert context["status"] == 403


def test_run_upsert_is_idempotent(httpx_mock, settings, conn):
    for _ in range(2):
        _allow_all_robots(httpx_mock)
        grant = _grant("360G-x-1", funder={"id": "GB-CHC-9", "name": "A Funder"},
                        recipient={"id": "GB-CHC-1079327", "name": "Change Grow Live"},
                        award_date="2023-01-01")
        httpx_mock.add_response(
            url=f"{API}/org/GB-CHC-1079327/grants_received/?limit=100", json=_page([grant]))
        httpx_mock.add_response(
            url=f"{API}/org/GB-CHC-1079327/grants_made/?limit=100", json=_page([]))
        httpx_mock.add_response(
            url=f"{API}/org/GB-COH-03861209/grants_received/?limit=100",
            status_code=404, json={"detail": "Not found."})
        httpx_mock.add_response(
            url=f"{API}/org/GB-COH-03861209/grants_made/?limit=100",
            status_code=404, json={"detail": "Not found."})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    tsg.run(ctx)
    tsg.run(ctx)

    count = conn.execute("SELECT COUNT(*) c FROM three_sixty_giving_grants").fetchone()["c"]
    assert count == 1  # not 2 -- second run upserts onto the same natural key


def test_no_targets_is_a_quiet_no_op(monkeypatch, settings, conn):
    monkeypatch.setattr(tsg, "_target_identifiers", lambda conn: [])
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    tsg.run(ctx)  # must not raise, must not require any HTTP mock
    count = conn.execute("SELECT COUNT(*) c FROM three_sixty_giving_grants").fetchone()["c"]
    assert count == 0
