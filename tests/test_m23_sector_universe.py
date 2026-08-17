"""Module 23 — the sector universe build and its unresolved review leads.

The phase plan's core claim is that the universe build and the 3,160
`unmatched_buyer_name` / `possible_group_company` items are the same
reconciliation labour, and that done systematically it produces a table
instead of a queue. So most of these tests are about the discipline that
keeps the universe defensible: provider_key only ever arrives through an
identifier, name-only captures stay name-only, and capture never hides an
identity question that still needs a person.
"""
from __future__ import annotations

import pytest

from pipeline import providers, review_sweep
from pipeline.modules import m23_sector_universe as u
from pipeline.registry import ModuleContext


def _ctx(conn, dry_run=False):
    return ModuleContext(conn=conn, settings=None, since=None,
                         dry_run=dry_run, limit=None)


def add_authority(conn, ons_code="E08000016", name="Barnsley Metropolitan Borough Council"):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES (?, ?, 'LBO', "
        "'Yorkshire and The Humber', '1996-04-01', '2023', '2026', "
        "'https://ons.uk/g', '2026-08-01T00:00:00Z', 200, 'ons_geoportal', 'h')",
        (ons_code, name))


def add_company(conn, number="03861209", name="Change Grow Live", match_basis="seed",
                provider_key="change_grow_live"):
    conn.execute(
        "INSERT INTO companies (company_number, provider_key, company_name, match_basis, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, 'https://ch.uk/c', '2026-08-01T00:00:00Z', 200, 'companies_house', 'h')",
        (number, provider_key, name, match_basis))


def add_charity(conn, number="1079327", provider_key="change_grow_live"):
    conn.execute(
        "INSERT INTO charity_financials (charity_number, financial_year_end, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '2026-03-31', 'https://charitycommission.uk/c', "
        "'2026-08-01T00:00:00Z', 200, 'charity_commission', 'h')",
        (number,))
    if provider_key:
        providers.record_discovered_identifier(
            conn, provider_key, "charity_number", number, discovered_by="m03_charity_finance")


def add_cqc(conn, provider_id="1-123456789", name="Change Grow Live", company_number=None,
            charity_number=None):
    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_name, companies_house_number, "
        "charity_number, registration_date, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES (?, ?, ?, ?, '2020-01-01', "
        "'https://cqc.uk/p', '2026-08-01T00:00:00Z', 200, 'cqc_public_api', 'h')",
        (provider_id, name, company_number, charity_number))


def add_contract(conn, notice_id, supplier_name, ppon=None, date="2026-01-01",
                 buyer_name=None, buyer_ons_code=None):
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, buyer_name, buyer_ons_code, "
        "supplier_name_raw, supplier_ppon, date_published, psr_basis, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "(?, '', ?, ?, ?, ?, ?, ?, 0, 'https://fts.uk/r', '2026-08-01T00:00:00Z', "
        "200, 'find_a_tender', 'h')",
        (notice_id, f"ocid-{notice_id}", buyer_name, buyer_ons_code, supplier_name,
         ppon, date))


def add_review_item(conn, item_type, raw_value, status="pending"):
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, status, "
        "created_at) VALUES ('m01_procurement', ?, ?, '{}', ?, '2026-08-01T00:00:00Z')",
        (item_type, raw_value, status))
    return conn.execute(
        "SELECT id FROM review_queue WHERE item_type = ? AND raw_value = ?",
        (item_type, raw_value)).fetchone()[0]


@pytest.fixture
def universe_conn(conn):
    """A warehouse with every capture kind present, plus the review items the
    universe absorbs."""
    providers.seed_providers(conn)
    add_authority(conn)
    add_company(conn)                                    # seeded CGL company
    add_company(conn, number="01865768", name="Forward Trust Limited",
                match_basis="name_only_unconfirmed", provider_key=None)
    add_charity(conn)
    add_cqc(conn, provider_id="1-111", company_number="03861209")  # merges into company
    add_cqc(conn, provider_id="1-222", name="We Are With You")     # own row
    add_contract(conn, "N1", "Change Grow Live")                    # variant -> provider row
    add_contract(conn, "N2", "CGL")                                 # variant -> provider row
    add_contract(conn, "N3", "Community Care Direct Limited", ppon="P-123")
    add_contract(conn, "N4", "Community Care Direct Ltd", ppon="P-123")  # same ppon, same row
    add_contract(conn, "N5", "The One Off Company Ltd")             # name-only awardee
    add_review_item(conn, "unmatched_buyer_name", "NHS Barnsley ICB")       # funder
    add_review_item(conn, "unmatched_buyer_name", "Barnsley Metropolitan Borough Council")  # authority now
    add_review_item(conn, "unmatched_buyer_name", "Change Grow Live")       # merges into provider
    add_review_item(conn, "possible_group_company", "14438204 CHANGE LIVE GROW LTD")
    add_review_item(conn, "unconfirmed_name_match", "01865768 Forward Trust Limited")
    conn.commit()
    return conn


def run_build(conn, dry_run=False):
    u.run(_ctx(conn, dry_run=dry_run))
    # The runner rolls a dry run back; the test does the same so a run that
    # promised to write nothing writes nothing.
    if dry_run:
        conn.rollback()
    else:
        conn.commit()


def universe_row(conn, entity_key):
    return conn.execute(
        "SELECT * FROM sector_universe WHERE entity_key = ?", (entity_key,)).fetchone()


# --- normalisation -------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Change Grow Live", "change grow live"),
    ("CHANGE, GROW, LIVE SERVICES LIMITED", "change grow live services"),
    ("Barnsley Metropolitan Borough Council", "barnsley"),
    ("Barnsley MBC", "barnsley mbc"),
    ("The One Off Company Ltd", "the one off company"),
    ("Barnardo's", "barnardos"),
    ("", ""),
    (None, ""),
])
def test_normalise_name(raw, expected):
    assert u.normalise_name(raw) == expected


def test_variant_lookup_covers_the_configured_aliases():
    """The same lookup m04 builds from SUPPLIER_NAME_VARIANTS; a notice that
    names a configured variant merges into the provider row."""
    assert u._VARIANT_LOOKUP[u.normalise_name("Change Grow Live Service Limited")] == "change_grow_live"
    assert u._VARIANT_LOOKUP[u.normalise_name("CGL")] == "change_grow_live"


# --- the capture kinds ---------------------------------------------------------

def test_every_capture_kind_lands_with_the_right_basis(universe_conn):
    run_build(universe_conn)

    provider = universe_row(universe_conn, "provider:change_grow_live")
    assert provider["entity_type"] == "provider"
    assert provider["match_basis"] == "seed"
    assert provider["provider_key"] == "change_grow_live"
    assert provider["notices_count"] == 2  # both variant notices, distinct ids

    company = universe_row(universe_conn, "03861209")
    assert company["entity_type"] == "company"
    assert company["match_basis"] == "seed"
    assert company["provider_key"] == "change_grow_live"
    assert company["cqc_provider_id"] == "1-111"  # CQC provider merged in by number

    name_only_company = universe_row(universe_conn, "01865768")
    assert name_only_company["match_basis"] == "name_only_unconfirmed"
    assert name_only_company["provider_key"] is None  # never linked on a name

    charity = universe_row(universe_conn, "charity:1079327")
    assert charity["entity_type"] == "charity"
    assert charity["match_basis"] == "register"
    assert charity["provider_key"] == "change_grow_live"  # via provider_identifiers

    cqc = universe_row(universe_conn, "cqc:1-222")
    assert cqc["entity_type"] == "cqc_provider"
    assert cqc["match_basis"] == "register"
    assert cqc["provider_key"] is None

    ppon = universe_row(universe_conn, "ppon:P-123")
    assert ppon["entity_type"] == "awardee"
    assert ppon["match_basis"] == "ppon"
    assert ppon["notices_count"] == 2  # both spellings, one registration
    assert ppon["canonical_name"] == "Community Care Direct Limited"

    one_off = [r for r in universe_conn.execute(
        "SELECT * FROM sector_universe WHERE entity_type = 'awardee' "
        "AND match_basis = 'name_only_unconfirmed'").fetchall()]
    assert [r["canonical_name"] for r in one_off] == ["The One Off Company Ltd"]
    assert one_off[0]["notices_count"] == 1
    assert one_off[0]["provider_key"] is None

    funder = [r for r in universe_conn.execute(
        "SELECT * FROM sector_universe WHERE entity_type = 'funder'").fetchall()]
    assert [r["canonical_name"] for r in funder] == ["NHS Barnsley ICB"]
    assert funder[0]["match_basis"] == "name_only_unconfirmed"
    assert funder[0]["source_system"] == "review_queue"

    candidate = universe_row(universe_conn, "14438204")
    assert candidate["entity_type"] == "company"
    assert candidate["match_basis"] == "name_only_unconfirmed"
    assert candidate["provider_key"] is None
    assert candidate["company_number"] == "14438204"


def test_an_authority_buyer_name_never_becomes_a_funder(universe_conn):
    """The name matched m01's own matcher now (overrides may have changed);
    it was never a funder, so it must not appear in the universe."""
    run_build(universe_conn)
    rows = universe_conn.execute(
        "SELECT entity_type FROM sector_universe "
        "WHERE canonical_name = 'Barnsley Metropolitan Borough Council'").fetchall()
    assert rows == []


def test_a_funder_that_is_also_an_awardee_merges_into_the_awardee_row(universe_conn):
    """'Change Grow Live' buys as well as sells: one organisation, one row."""
    run_build(universe_conn)
    provider = universe_row(universe_conn, "provider:change_grow_live")
    assert provider["entity_type"] == "provider"
    funders = universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe WHERE entity_type = 'funder'").fetchone()["c"]
    assert funders == 1  # only the NHS ICB; the provider buyer merged away


def test_review_item_candidates_are_never_linked_to_a_provider(universe_conn):
    run_build(universe_conn)
    linked = universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe "
        "WHERE match_basis = 'name_only_unconfirmed' AND provider_key IS NOT NULL").fetchone()["c"]
    assert linked == 0


def test_no_provider_key_outside_provider_identifiers(universe_conn):
    """A charity whose number is in no identifier table gets no provider_key;
    the identifier table is the only door."""
    add_charity(universe_conn, number="9999999", provider_key=None)
    universe_conn.commit()
    run_build(universe_conn)
    row = universe_row(universe_conn, "charity:9999999")
    assert row["match_basis"] == "register"
    assert row["provider_key"] is None


def test_unverified_provider_identifier_does_not_link(universe_conn):
    """A discovered identifier is a lead until a person verifies it."""
    add_charity(universe_conn, number="9999998", provider_key="change_grow_live")
    universe_conn.commit()
    assert universe_conn.execute(
        "SELECT status FROM provider_identifiers WHERE scheme = 'charity_number' "
        "AND identifier = '9999998'").fetchone()["status"] == "unverified"

    run_build(universe_conn)

    row = universe_row(universe_conn, "charity:9999998")
    assert row["match_basis"] == "register"
    assert row["provider_key"] is None


# --- idempotence and dry runs --------------------------------------------------

def test_a_rebuild_produces_the_same_universe(universe_conn):
    run_build(universe_conn)
    first = universe_conn.execute(
        "SELECT entity_key, canonical_name, notices_count FROM sector_universe "
        "ORDER BY entity_key").fetchall()
    run_build(universe_conn)
    second = universe_conn.execute(
        "SELECT entity_key, canonical_name, notices_count FROM sector_universe "
        "ORDER BY entity_key").fetchall()
    assert [tuple(r) for r in first] == [tuple(r) for r in second]
    assert universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe").fetchone()["c"] > 0


def test_a_rebuild_after_the_sweep_still_rebuilds_funders_and_candidates(universe_conn):
    """An unrelated deterministic sweep does not change universe inputs."""
    run_build(universe_conn)
    review_sweep.sweep(universe_conn)
    run_build(universe_conn)
    first = universe_conn.execute(
        "SELECT entity_key, canonical_name, notices_count FROM sector_universe "
        "ORDER BY entity_key").fetchall()
    assert [tuple(r) for r in first] == [
        tuple(r) for r in universe_conn.execute(
            "SELECT entity_key, canonical_name, notices_count FROM sector_universe "
            "ORDER BY entity_key").fetchall()]
    funders = universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe WHERE entity_type = 'funder'").fetchone()["c"]
    assert funders == 1
    candidates = universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe WHERE entity_key = '14438204'").fetchone()["c"]
    assert candidates == 1


def test_a_decided_group_company_item_is_not_resurrected(universe_conn):
    """'approved'/'rejected' are a person's decisions; the build does not read
    them, so the universe does not re-capture a company a human disposed of."""
    add_review_item(universe_conn, "possible_group_company", "09999999 REJECTED CO LTD",
                    status="rejected")
    run_build(universe_conn)
    assert universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe WHERE entity_key = '09999999'"
    ).fetchone()["c"] == 0


def test_a_dry_run_writes_nothing(universe_conn):
    run_build(universe_conn, dry_run=True)
    assert universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe").fetchone()["c"] == 0


# --- capture remains unresolved ------------------------------------------------

def _pending_by_type(conn):
    return dict(conn.execute(
        "SELECT item_type, COUNT(*) c FROM review_queue WHERE status = 'pending' "
        "GROUP BY item_type").fetchall())


def test_the_sweep_leaves_captured_identity_questions_pending(universe_conn):
    run_build(universe_conn)
    review_sweep.sweep(universe_conn)

    statuses = {(r["item_type"], r["raw_value"]): r["status"] for r in universe_conn.execute(
        "SELECT item_type, raw_value, status FROM review_queue").fetchall()}
    for status in statuses.values():
        assert status == "pending"
    assert universe_conn.execute(
        "SELECT COUNT(*) FROM review_resolutions").fetchone()[0] == 0


def test_the_sweep_leaves_decided_items_alone(universe_conn):
    """The item was pending when the build captured it; a person approved it
    after; the sweep must not overwrite that decision in either direction."""
    item_id = add_review_item(universe_conn, "unmatched_buyer_name", "NHS Everywhere ICB")
    run_build(universe_conn)
    universe_conn.execute(
        "UPDATE review_queue SET status = 'approved', resolved_at = '2026-08-02T00:00:00Z' "
        "WHERE id = ?", (item_id,))
    universe_conn.commit()
    review_sweep.sweep(universe_conn)
    assert universe_conn.execute(
        "SELECT status FROM review_queue WHERE id = ?", (item_id,)).fetchone()["status"] == "approved"


def test_preview_has_no_universe_capture_resolution_rules(universe_conn):
    run_build(universe_conn)
    preview = review_sweep.preview(universe_conn)
    assert "unmatched_buyer_captured_as_funder" not in preview
    assert "possible_group_company_in_universe" not in preview
    assert "unconfirmed_name_match_in_universe" not in preview
    assert _pending_by_type(universe_conn)["unmatched_buyer_name"] == 3


def test_the_sweep_closes_nothing_before_the_build_runs(universe_conn):
    """The rules are evidence-driven: no universe rows, no closures. This is
    what makes the sweep safe to run any time."""
    review_sweep.sweep(universe_conn)
    assert _pending_by_type(universe_conn)["unmatched_buyer_name"] == 3
    assert _pending_by_type(universe_conn)["possible_group_company"] == 1


# --- the export tab ------------------------------------------------------------

def test_the_universe_tab_exports_every_row_with_its_caveats(universe_conn, tmp_path):
    from pipeline.exports import sheets as sheets_export
    from pipeline.exports.schema import tab_by_name

    run_build(universe_conn)
    tab = tab_by_name("10_Sector_Universe")
    assert tab is not None
    columns, rows = sheets_export.run_tab_query(universe_conn, tab)
    assert columns == tab.columns
    assert len(rows) == universe_conn.execute(
        "SELECT COUNT(*) c FROM sector_universe").fetchone()["c"]

    paths = sheets_export.export_sheets(universe_conn, tmp_path)
    assert any(p.name == "10_Sector_Universe.csv" for p in paths)
    text = (tmp_path / "10_Sector_Universe.csv").read_text(encoding="utf-8")
    for caveat in tab.caveats:
        assert caveat in text
    assert "NHS Barnsley ICB" in text
    assert "14438204" in text
    assert "notices_count" in text
