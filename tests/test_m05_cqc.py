from __future__ import annotations

import re

import pytest

from pipeline import providers
from pipeline.modules import m05_cqc as cqc
from pipeline.registry import ModuleContext

API = "https://api.service.cqc.org.uk/public/v1"


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://api.service.cqc.org.uk/robots.txt",
                             status_code=200, text="", is_reusable=True)


def _seed_authority(conn, ons_code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'metropolitan_district', '2020-01-01', 'x', 'x', 'https://example.com', "
        "'2020-01-01T00:00:00Z', 200, 'test', 'abc')",
        (ons_code, name))


def _seed_cqc_provider(conn, provider_id: str = "1-125892604") -> None:
    """cqc_locations has an FK to cqc_providers; the real module always writes
    the provider before its locations, so tests do the same."""
    conn.execute(
        "INSERT OR IGNORE INTO cqc_providers (provider_id, provider_key, provider_name, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, 'change_grow_live', 'Change, Grow, Live', 'https://example.com', "
        "'2026-01-01T00:00:00Z', 200, 'test', 'abc')",
        (provider_id,))


# --- provider name matching ------------------------------------------------------

@pytest.mark.parametrize("name,key", [
    ("Change, Grow, Live", "change_grow_live"),
    ("Turning Point", "turning_point"),
    ("Waythrough", "waythrough"),
    ("Humankind", "humankind"),
])
def test_exact_provider_names_match(name, key):
    assert cqc.match_provider_name(name) == (key, "exact")


@pytest.mark.parametrize("name", [
    # real CQC provider names that merely contain a variant as a substring
    "At Home With You Limited",
    "With You Care Ltd",
    "Care With You Ltd",
    "Home With You Limited",
    "Be Humankind Care Ltd",
    "The Turning Point Project Ltd",
    "We are With You",
])
def test_substring_hits_are_flagged_not_matched(name):
    _key, basis = cqc.match_provider_name(name)
    assert basis != "exact"


def test_unrelated_provider_does_not_match_at_all():
    assert cqc.match_provider_name("Artemis Cystitis Limited") == (None, None)
    assert cqc.match_provider_name(None) == (None, None)


def test_generic_acronyms_are_not_substring_matched():
    # "Via" and "Inclusion" are ordinary words; they must not drag in
    # unrelated care providers via substring matching
    assert cqc.match_provider_name("Inclusion Housing Group")[1] != "exact"


# --- local authority resolution ---------------------------------------------------

def test_local_authority_resolves_to_ons_code(conn):
    _seed_authority(conn, "E08000034", "Kirklees")
    lookup = cqc._build_authority_lookup(conn)
    assert lookup[cqc._normalise_authority_name("Kirklees")] == "E08000034"


# --- location storage --------------------------------------------------------------

class _FakeResult:
    url = "https://api.service.cqc.org.uk/public/v1/locations/1-10559211016"
    status_code = 200
    payload_sha256 = "abc123"

    @property
    def retrieved_at(self):
        import datetime
        return datetime.datetime(2026, 8, 10, tzinfo=datetime.timezone.utc)


def _location_payload():
    return {
        "locationId": "1-10559211016",
        "name": "CHART Kirklees",
        "postalCode": "WF13 1LY",
        "onspdLatitude": 53.691003,
        "onspdLongitude": -1.632177,
        "registrationStatus": "Registered",
        "localAuthority": "Kirklees",
        "region": "Yorkshire & Humberside",
        "lastInspection": {"date": "2022-02-23"},
        "currentRatings": {"overall": {"rating": "Good", "reportDate": "2022-04-14"}},
        "gacServiceTypes": [{"name": "Community services - Substance abuse"}],
        "regulatedActivities": [{
            "name": "Treatment of disease, disorder or injury",
            "contacts": [{"personTitle": "Ms", "personGivenName": "Alex",
                           "personFamilyName": "Roe", "personRole": "Registered Manager"}],
        }],
        "reports": [{"linkId": "r1", "reportDate": "2022-04-14",
                      "firstVisitDate": "2022-02-15", "reportUri": "/reports/r1"}],
    }


def test_store_location_populates_public_fields(conn):
    _seed_authority(conn, "E08000034", "Kirklees")
    _seed_cqc_provider(conn)
    lookup = cqc._build_authority_lookup(conn)
    cqc._store_location(conn, "m05_cqc", "1-125892604", "change_grow_live",
                         _location_payload(), _FakeResult(), lookup)

    row = conn.execute("SELECT * FROM cqc_locations").fetchone()
    assert row["location_name"] == "CHART Kirklees"
    assert row["postal_code"] == "WF13 1LY"
    assert row["latitude"] == pytest.approx(53.691003)
    assert row["local_authority_ons_code"] == "E08000034"
    assert row["overall_rating"] == "Good"
    assert row["last_inspection_date"] == "2022-02-23"
    assert "Substance abuse" in row["service_types"]
    assert row["source_url"] is not None


def test_registered_manager_names_go_only_to_restricted_table(conn):
    _seed_cqc_provider(conn)
    lookup = cqc._build_authority_lookup(conn)
    cqc._store_location(conn, "m05_cqc", "1-125892604", "change_grow_live",
                         _location_payload(), _FakeResult(), lookup)

    contact = conn.execute("SELECT * FROM restricted_cqc_location_contacts").fetchone()
    assert contact["person_name"] == "Ms Alex Roe"
    assert contact["person_role"] == "Registered Manager"

    public_blob = " ".join(
        str(v) for v in tuple(conn.execute("SELECT * FROM cqc_locations").fetchone())
        if v is not None)
    assert "Roe" not in public_blob
    assert "Alex" not in public_blob


def test_reports_are_stored_per_location(conn):
    _seed_cqc_provider(conn)
    lookup = cqc._build_authority_lookup(conn)
    cqc._store_location(conn, "m05_cqc", "1-125892604", "change_grow_live",
                         _location_payload(), _FakeResult(), lookup)
    report = conn.execute("SELECT * FROM cqc_location_reports").fetchone()
    assert report["report_uri"] == "/reports/r1"


def test_unmatched_local_authority_is_queued_not_guessed(conn):
    _seed_cqc_provider(conn)
    lookup = cqc._build_authority_lookup(conn)  # empty authorities table
    cqc._store_location(conn, "m05_cqc", "1-125892604", "change_grow_live",
                         _location_payload(), _FakeResult(), lookup)

    row = conn.execute("SELECT * FROM cqc_locations").fetchone()
    assert row["local_authority_raw"] == "Kirklees"
    assert row["local_authority_ons_code"] is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='unmatched_cqc_local_authority'"
    ).fetchone()["c"] == 1


def test_store_location_without_id_records_parse_failure(conn):
    lookup = {}
    cqc._store_location(conn, "m05_cqc", "p1", "change_grow_live", {"name": "X"},
                         _FakeResult(), lookup)
    assert conn.execute("SELECT COUNT(*) c FROM cqc_locations").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM parse_failures").fetchone()["c"] == 1


# --- end-to-end -------------------------------------------------------------------

def test_run_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    _seed_authority(conn, "E08000034", "Kirklees")

    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/providers\?.*"),
        json={"totalPages": 1, "providers": [
            {"providerId": "1-125892604", "providerName": "Change, Grow, Live"},
            {"providerId": "1-999", "providerName": "At Home With You Limited"},
            {"providerId": "1-888", "providerName": "Artemis Cystitis Limited"},
        ]})
    httpx_mock.add_response(
        url=f"{API}/providers/1-125892604",
        json={"name": "Change, Grow, Live", "companiesHouseNumber": "03861209",
              "charityNumber": "1079327", "registrationStatus": "Registered",
              "locationIds": ["1-10559211016"]})
    httpx_mock.add_response(url=f"{API}/locations/1-10559211016", json=_location_payload())

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    cqc.run(ctx)

    provider = conn.execute("SELECT * FROM cqc_providers").fetchall()
    assert len(provider) == 1  # only the exact match, not the substring hits
    assert provider[0]["provider_key"] == "change_grow_live"
    assert conn.execute("SELECT COUNT(*) c FROM cqc_locations").fetchone()["c"] == 1

    # substring hit queued for review rather than treated as this provider
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='possible_cqc_provider'"
    ).fetchone()["c"] == 1

    # cross-referenced identifiers recorded against the provider entity
    ids = {(r["scheme"], r["identifier"]) for r in conn.execute(
        "SELECT scheme, identifier FROM provider_identifiers WHERE provider_key='change_grow_live'")}
    assert ("cqc_provider_id", "1-125892604") in ids
    assert ("company_number", "03861209") in ids
