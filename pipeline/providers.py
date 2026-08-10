"""Provider reference config — seeds the `providers` and
`provider_identifiers` tables on every run.

Only identifiers that are actually verified belong here. CGL's charity
number is stated explicitly in the project brief, so it's seeded as
'verified'. Every other provider's charity/company numbers are left for
Modules 3 and 4 to discover from the Charity Commission and Companies
House APIs, and are written back as 'unverified' pending human
confirmation — deliberately NOT guessed here from general knowledge, since
a wrong company number would silently mis-attribute contracts, tribunal
claims and accounts to the wrong legal entity.
"""
from __future__ import annotations

from pipeline.keywords import SUPPLIER_NAME_VARIANTS

TARGET_PROVIDER_KEY = "change_grow_live"

# provider_key -> human note, for providers where the name alone is
# ambiguous or the corporate history matters when reading the evidence.
PROVIDER_NOTES: dict[str, str] = {
    "change_grow_live": "Campaign subject. Registered charity; contracts are often held by trading subsidiaries.",
    "addaction": "Former name of With You — treat as the same organisation over time, but do not merge rows: the name on a notice is evidence of when it was used.",
    "with_you": "Formerly Addaction.",
    "humankind": "Merged into Waythrough (with Richmond Fellowship) — verify entity identity per document before joining.",
    "waythrough": "Formed from Humankind / Richmond Fellowship merger.",
    "richmond_fellowship": "Associated with Waythrough via merger.",
    "via": "Short trading name; high false-positive risk when matching free text — match only exact registered variants.",
    "inclusion": "Generic word; part of Midlands Partnership NHS Foundation Trust. High false-positive risk in free-text matching.",
}

# Identifiers asserted here are treated as verified. Keep this list to
# things that are actually confirmed — see module docstring.
VERIFIED_IDENTIFIERS: list[dict[str, str]] = [
    {
        "provider_key": "change_grow_live",
        "scheme": "charity_number",
        "identifier": "1079327",
        "role": "registered charity (England and Wales)",
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


def seed_providers(conn) -> None:
    """Idempotently seed the provider reference tables. Safe to call at the
    start of any module that needs provider_key to resolve.
    """
    from pipeline import db

    providers, identifiers = seed_rows()
    for row in providers:
        db.upsert(conn, "providers", row, natural_key=["provider_key"])
    for row in identifiers:
        db.upsert(conn, "provider_identifiers", row,
                   natural_key=["provider_key", "scheme", "identifier"])


def record_discovered_identifier(
    conn, provider_key: str, scheme: str, identifier: str, discovered_by: str, role: str | None = None
) -> None:
    """Record an identifier a module found in a source. Always written as
    'unverified' — and never overwrites a config-asserted 'verified' row,
    so a bad API match can't quietly displace a confirmed identifier.
    """
    from pipeline import db

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
