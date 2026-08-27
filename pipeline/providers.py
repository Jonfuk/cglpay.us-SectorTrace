"""Provider reference config — seeds the `providers` and
`provider_identifiers` tables on every run.

Only identifiers that are actually verified belong here — asserted by a
person, never discovered by a module. Two ways one earns that:

  * CGL's charity number is stated explicitly in the project brief.
  * The comparators' charity and company numbers were hand-checked on
    2026-08-27 against the primary registers — Companies House for every
    company number (the register itself, not an aggregator) and the
    Charity Commission register for every charity number. The full
    previous-name history was read for each, so a rename could not be
    mistaken for a different legal entity.
  * The CQC provider IDs were hand-checked on the same date against each
    provider's current page on cqc.org.uk. The re-registration hazard is
    real and was checked per provider: Richmond Fellowship's CQC
    registration is archived (services moved to Waythrough) and Delphi has
    a live registration under 'Delphi Medical Limited' alongside an
    archived 'Delphi Medical Consultants Limited' — the live/correct id is
    the one seeded, with the archived predecessor named in PROVIDER_NOTES.

Everything still missing here — PPONs, the company numbers of trading
subsidiaries — is left for Modules 3, 4 and 10 to discover and write back
as 'unverified' pending the same hand check. A guessed identifier
silently mis-attributes contracts, tribunal claims and accounts to the
wrong legal entity, so it is worse than a NULL.

Three provider_keys are historical names of an entity that also appears
under its current name (addaction→with_you, humankind→waythrough,
westminster_drug_project→via). The identifiers live on the current key;
the historical key stays a bare name variant so a notice bearing the old
name still resolves to its own row. See PROVIDER_NOTES.
"""
from __future__ import annotations

from pipeline.keywords import SUPPLIER_NAME_VARIANTS

TARGET_PROVIDER_KEY = "change_grow_live"

# provider_key -> human note, for providers where the name alone is
# ambiguous or the corporate history matters when reading the evidence.
PROVIDER_NOTES: dict[str, str] = {
    "change_grow_live": "Campaign subject. Charity 1079327; operating company 03861209 was 'Crime Reduction Initiatives' until 2016. Contracts are often held by trading subsidiaries.",
    "addaction": "Former name of With You: the registered name of company 02580377 / charity 1001957 from 1998 until 26 Feb 2020. Same legal entity as `with_you`, where the identifiers are seeded — but do not merge evidence rows: the name on a notice is evidence of when it was used.",
    "with_you": "Formerly Addaction (renamed 26 Feb 2020). Company 02580377, charity 1001957.",
    "humankind": "Former name of Waythrough: 'Humankind Charity' was the registered name of company 01820492 / charity 515755 from 2018 until 6 Feb 2025 ('DISC' before that). Same legal entity as `waythrough`, where the identifiers are seeded. Distinct from the 2024 group formation with Richmond Fellowship, which stayed separately registered.",
    "waythrough": "The former Humankind entity (company 01820492, charity 515755) renamed 6 Feb 2025 — not a new legal entity. Richmond Fellowship and Aquarius (charity 1014305) sit alongside it in the Waythrough group, each still separately registered.",
    "richmond_fellowship": "In the Waythrough group since the 2024 merger but still a separate registered entity: company 00662712, charity 200453. Do not join its evidence onto Waythrough's identifiers. Its CQC provider registration (1-151675564) was archived on 4 Jun 2024 with the regulated services moved to Waythrough — pre-June-2024 CQC evidence is still RF's.",
    "via": "Formerly Westminster Drug Project (renamed 5 Jun 2023). Company 02807934 ('Via Community Ltd'), charity 1031602. Short trading name; high false-positive risk in free text — match only exact registered variants or the historic 'Westminster Drug Project'.",
    "westminster_drug_project": "Former name of Via: the registered name of company 02807934 / charity 1031602 until 5 Jun 2023 (also historic 'Waltham Forest Drug Project' / 'Wandsworth Drug Project'). Same legal entity as `via`, where the identifiers are seeded.",
    "delphi_medical": "Private company, not a charity: Delphi Medical Limited, company 06944767, CQC provider 1-2448282802. A separately registered 'Delphi Medical Consultants Limited' (company 06014150, CQC provider 1-125892841) shares the Burnley address and historically held the substance-misuse registrations; its CQC registration was archived on 15 Nov 2024. Seeded identifiers refer to Delphi Medical Limited.",
    "inclusion": "Not a separate legal entity: a service brand of Midlands Partnership University NHS Foundation Trust (NHS provider, ODS / CQC code RRE — no Companies House or Charity Commission registration). Generic word; high false-positive risk in free-text matching.",
}

# Identifiers asserted here are treated as verified. Keep this list to
# things that are actually confirmed — see module docstring.
#
# Company numbers are stored in the 8-character form Companies House uses,
# so a module that later re-discovers one (normalised via
# m04.normalise_company_number) produces the same row rather than a
# duplicate.
#
# Charity numbers are the England & Wales register numbers only. Phoenix
# Futures is also OSCR-registered (SC039008) and Change Grow Live also
# holds SC039861; those are left out until m03 can route a Scottish
# number, since it would otherwise just feed them to the CCEW API and log
# a review item.
VERIFIED_IDENTIFIERS: list[dict[str, str]] = [
    # Campaign subject. Charity number from the project brief; company
    # number confirmed against Companies House (ex 'Crime Reduction
    # Initiatives').
    {
        "provider_key": "change_grow_live",
        "scheme": "charity_number",
        "identifier": "1079327",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "change_grow_live",
        "scheme": "company_number",
        "identifier": "03861209",
        "role": "charitable company limited by guarantee",
    },

    # Comparators — hand-checked 2026-08-27 against the Charity Commission
    # register and Companies House, previous-name history read for each.
    {
        "provider_key": "turning_point",
        "scheme": "charity_number",
        "identifier": "234887",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "turning_point",
        "scheme": "company_number",
        "identifier": "00793558",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "with_you",
        "scheme": "charity_number",
        "identifier": "1001957",
        "role": "registered charity (England and Wales); 'Addaction' until 2020",
    },
    {
        "provider_key": "with_you",
        "scheme": "company_number",
        "identifier": "02580377",
        "role": "charitable company limited by guarantee; 'Addaction' until 2020",
    },
    {
        "provider_key": "waythrough",
        "scheme": "charity_number",
        "identifier": "515755",
        "role": "registered charity (England and Wales); 'Humankind' until 2025",
    },
    {
        "provider_key": "waythrough",
        "scheme": "company_number",
        "identifier": "01820492",
        "role": "charitable company limited by guarantee; 'Humankind' until 2025",
    },
    {
        "provider_key": "richmond_fellowship",
        "scheme": "charity_number",
        "identifier": "200453",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "richmond_fellowship",
        "scheme": "company_number",
        "identifier": "00662712",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "via",
        "scheme": "charity_number",
        "identifier": "1031602",
        "role": "registered charity (England and Wales); 'Westminster Drug Project' until 2023",
    },
    {
        "provider_key": "via",
        "scheme": "company_number",
        "identifier": "02807934",
        "role": "charitable company limited by guarantee; 'Westminster Drug Project' until 2023",
    },
    {
        "provider_key": "forward_trust",
        "scheme": "charity_number",
        "identifier": "1001701",
        "role": "registered charity (England and Wales); 'RAPt' until 2017",
    },
    {
        "provider_key": "forward_trust",
        "scheme": "company_number",
        "identifier": "02560474",
        "role": "charitable company limited by guarantee; 'RAPt' until 2017",
    },
    {
        "provider_key": "phoenix_futures",
        "scheme": "charity_number",
        "identifier": "284880",
        "role": "registered charity (England and Wales); operating name 'Phoenix House'",
    },
    {
        "provider_key": "phoenix_futures",
        "scheme": "company_number",
        "identifier": "01626869",
        "role": "charitable company limited by guarantee ('Phoenix House')",
    },
    {
        "provider_key": "delphi_medical",
        "scheme": "company_number",
        "identifier": "06944767",
        "role": "private limited company (not a charity)",
    },

    # CQC provider IDs — hand-checked 2026-08-27 against each provider's
    # current page on cqc.org.uk. CQC's registered name is kept in `role`
    # because it often differs from the canonical name and is what the
    # bulk-directory match in m05 keys on. NHS trusts (inclusion) carry
    # their ODS code as the provider id. Two archived registrations are
    # noted rather than seeded stale: see PROVIDER_NOTES for
    # richmond_fellowship and delphi_medical.
    {
        "provider_key": "change_grow_live",
        "scheme": "cqc_provider_id",
        "identifier": "1-125892604",
        "role": "CQC-registered provider ('Change, Grow, Live')",
    },
    {
        "provider_key": "turning_point",
        "scheme": "cqc_provider_id",
        "identifier": "1-102642564",
        "role": "CQC-registered provider ('Turning Point')",
    },
    {
        "provider_key": "with_you",
        "scheme": "cqc_provider_id",
        "identifier": "1-101617404",
        "role": "CQC-registered provider ('We are With You')",
    },
    {
        "provider_key": "waythrough",
        "scheme": "cqc_provider_id",
        "identifier": "1-126775024",
        "role": "CQC-registered provider ('Waythrough')",
    },
    {
        "provider_key": "richmond_fellowship",
        "scheme": "cqc_provider_id",
        "identifier": "1-151675564",
        "role": "CQC-registered provider ('Richmond Fellowship (The)'); archived 4 Jun 2024, services moved to Waythrough",
    },
    {
        "provider_key": "via",
        "scheme": "cqc_provider_id",
        "identifier": "1-126775066",
        "role": "CQC-registered provider ('Via Community Ltd')",
    },
    {
        "provider_key": "forward_trust",
        "scheme": "cqc_provider_id",
        "identifier": "1-126776256",
        "role": "CQC-registered provider ('The Forward Trust')",
    },
    {
        "provider_key": "phoenix_futures",
        "scheme": "cqc_provider_id",
        "identifier": "1-101660529",
        "role": "CQC-registered provider ('Phoenix House')",
    },
    {
        "provider_key": "delphi_medical",
        "scheme": "cqc_provider_id",
        "identifier": "1-2448282802",
        "role": "CQC-registered provider ('Delphi Medical Limited'); predecessor 'Delphi Medical Consultants Limited' (1-125892841) archived 15 Nov 2024",
    },
    {
        "provider_key": "inclusion",
        "scheme": "cqc_provider_id",
        "identifier": "RRE",
        "role": "CQC provider id is the ODS trust code for Midlands Partnership University NHS Foundation Trust",
    },
]


def seed_rows() -> tuple[list[dict], list[dict]]:
    """Returns (providers, provider_identifiers) rows to upsert."""
    providers = []
    for key, variants in SUPPLIER_NAME_VARIANTS.items():
        providers.append({
            "provider_key": key,
            "canonical_name": variants[0],
            "is_target": 1 if key == TARGET_PROVIDER_KEY else 0,
            "notes": PROVIDER_NOTES.get(key),
        })

    identifiers = [
        {**row, "status": "verified", "discovered_by": None}
        for row in VERIFIED_IDENTIFIERS
    ]
    return providers, identifiers


def seed_providers(conn, commit: bool = True) -> None:
    """Idempotently seed the provider reference tables. Safe to call at the
    start of any module that needs provider_key to resolve.

    COMMITS BY DEFAULT, and that is the whole point of the argument.

    SQLite allows one writer at a time. Python's sqlite3 opens a transaction on
    the first write and holds it until commit, so a module that seeded here and
    then went off to fetch held the database's only write slot for every second
    of its crawl. Serially that is invisible. Under `run all --jobs N` every
    module in a wave seeds within milliseconds of starting, one of them wins
    the slot, and the rest sit on the busy handler until it expires — which is
    a `run all --jobs 4` reporting "OperationalError: database is locked"
    against twelve modules that had each burned two minutes waiting, after
    making no requests at all.

    These rows are reference data built from `pipeline/keywords.py`, not
    fetched evidence: identical on every run, and nothing a module does can
    make them wrong. Committing them immediately costs nothing and hands the
    write slot straight back.

    `commit=False` is for `--dry-run`, where the caller rolls the whole
    transaction back and a run that promised to write nothing must write
    nothing. A dry run with `--jobs` can therefore still contend — it is the
    one case where the promise and the concurrency pull in opposite directions,
    and the promise wins.
    """
    from pipeline import db

    providers, identifiers = seed_rows()
    for row in providers:
        db.upsert(conn, "providers", row, natural_key=["provider_key"])
    for row in identifiers:
        db.upsert(conn, "provider_identifiers", row,
                   natural_key=["provider_key", "scheme", "identifier"])
    if commit:
        conn.commit()


def normalise_identifier(scheme: str, identifier: str) -> str:
    """Canonical form for an identifier, so the same entity discovered by two
    modules produces one row rather than two.

    Company numbers are the case that bites: the Charity Commission publishes
    them unpadded ("3861209") while Companies House uses 8 characters
    ("03861209"), and storing both would split one company's evidence in two.
    """
    value = str(identifier).strip()
    if scheme == "company_number":
        from pipeline.modules.m04_companies import normalise_company_number

        return normalise_company_number(value)
    return value


def record_discovered_identifier(
    conn, provider_key: str, scheme: str, identifier: str, discovered_by: str, role: str | None = None
) -> None:
    """Record an identifier a module found in a source. Always written as
    'unverified' — and never overwrites a config-asserted 'verified' row,
    so a bad API match can't quietly displace a confirmed identifier.
    """
    from pipeline import db

    identifier = normalise_identifier(scheme, identifier)
    existing = conn.execute(
        "SELECT status FROM provider_identifiers WHERE provider_key = ? AND scheme = ? AND identifier = ?",
        (provider_key, scheme, identifier),
    ).fetchone()
    if existing and existing["status"] == "verified":
        return
    db.upsert(conn, "provider_identifiers", {
        "provider_key": provider_key, "scheme": scheme, "identifier": identifier,
        "role": role, "status": "unverified", "discovered_by": discovered_by,
    }, natural_key=["provider_key", "scheme", "identifier"])
