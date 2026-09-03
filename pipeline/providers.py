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

Not every tracked provider is a going concern. Some keys are former names
of an entity now tracked under its current name (addaction→with_you,
humankind→waythrough, westminster_drug_project→via) or a former group
brand (recovery_focus→waythrough); some are organisations absorbed into
another (richmond_fellowship, aquarius, action_on_addiction, swanswell,
blenheim_cdp, edp_drug_alcohol into the Humankind/Waythrough line;
ley_community into phoenix_futures; kca into with_you; blue_sky into
forward_trust) or wound up entirely (lifeline_project). PROVIDER_STATUS
records that per key —
`status` and, where there is one successor, `superseded_by` — and it is
seeded onto the `providers` table so the portal can say so plainly. The
identifiers still live on the current/surviving key; a former or
dissolved key keeps its name variants so a notice bearing that identity
still resolves to its own row, and its evidence is never rewritten onto
the successor. See PROVIDER_NOTES.
"""
from __future__ import annotations

from pipeline.keywords import SUPPLIER_NAME_VARIANTS

TARGET_PROVIDER_KEY = "change_grow_live"

# provider_key -> human note, for providers where the name alone is
# ambiguous or the corporate history matters when reading the evidence.
PROVIDER_NOTES: dict[str, str] = {
    "change_grow_live": "Campaign subject. Charity 1079327; operating company 03861209 was 'Crime Reduction Initiatives' until 2016. Contracts are often held by trading subsidiaries.",
    "addaction": "Former name of With You: the registered name of company 02580377 / charity 1001957 from 1998 until 26 Feb 2020. Same legal entity as `with_you`, where the identifiers are seeded — but do not merge evidence rows: the name on a notice is evidence of when it was used.",
    "with_you": "Formerly Addaction (renamed 26 Feb 2020). Company 02580377, charity 1001957. Absorbed KCA (Kent Council on Addictions) as a subsidiary in 2015 — see `kca`.",
    "humankind": "Former name of Waythrough: 'Humankind Charity' was the registered name of company 01820492 / charity 515755 from 2018 until 6 Feb 2025 ('DISC' before that). Same legal entity as `waythrough`, where the identifiers are seeded. Distinct from the 2024 group formation with Richmond Fellowship, which stayed separately registered.",
    "waythrough": "The former Humankind entity (company 01820492, charity 515755) renamed 6 Feb 2025 — not a new legal entity. The Humankind/Waythrough line has absorbed several charities: Blenheim CDP (London, 2019), EDP Drug & Alcohol Services (Devon/Dorset, 2023), and — via the 2024 group formation — Richmond Fellowship and Aquarius, which stayed separately registered. Blenheim and EDP evidence is under their own keys.",
    "richmond_fellowship": "In the Waythrough group since the 2024 merger but still a separate registered entity: company 00662712, charity 200453. Do not join its evidence onto Waythrough's identifiers. Its CQC provider registration (1-151675564) was archived on 4 Jun 2024 with the regulated services moved to Waythrough — pre-June-2024 CQC evidence is still RF's. From 2015 until the 2024 merger, RF and Aquarius operated under the group brand 'Recovery Focus' — see `recovery_focus`.",
    "forward_trust": "Charity 1001701, company 02560474 ('Rehabilitation for Addicted Prisoners Trust' / RAPt until 2017, 'The Addictive Diseases Trust' before that). Has absorbed Blue Sky Development and Regeneration (2017, now run as 'Blue Sky Services') and Action on Addiction (2021) — see `blue_sky`, `action_on_addiction`.",
    "via": "Formerly Westminster Drug Project (renamed 5 Jun 2023). Company 02807934 ('Via Community Ltd'), charity 1031602. Short trading name; high false-positive risk in free text — match only exact registered variants or the historic 'Westminster Drug Project'.",
    "westminster_drug_project": "Former name of Via: the registered name of company 02807934 / charity 1031602 until 5 Jun 2023 (also historic 'Waltham Forest Drug Project' / 'Wandsworth Drug Project'). Same legal entity as `via`, where the identifiers are seeded.",
    "delphi_medical": "Private company, not a charity: Delphi Medical Limited, company 06944767, CQC provider 1-2448282802. A separately registered 'Delphi Medical Consultants Limited' (company 06014150, CQC provider 1-125892841) shares the Burnley address and historically held the substance-misuse registrations; its CQC registration was archived on 15 Nov 2024. Seeded identifiers refer to Delphi Medical Limited.",
    "inclusion": "Not a separate legal entity: a service brand of Midlands Partnership University NHS Foundation Trust (NHS provider, ODS / CQC code RRE — no Companies House or Charity Commission registration). Generic word; high false-positive risk in free-text matching.",
    "cranstoun": "National drug and alcohol charity: charity 1061582, company 03306337 ('Cranstoun Drug Services' until 2011), CQC provider 1-101678209. Absorbed Swanswell in 2022.",
    "changing_lives": "'Changing Lives' is the trading name of The Cyrenians Ltd (company 00995799, 'Tyneside Cyrenians Limited' until 2009), charity 500640; CQC registers it as 'The Cyrenians Ltd' (provider 1-144519557). A Collective Voice member. Homelessness charity whose remit includes drug and alcohol recovery services.",
    "alcohol_and_drug_service": "'ADS', Hull: charity 1108595, company 05375809, CQC provider 1-152340136. Delivers the Aspire partnership with Rotherham Doncaster and South Humber NHS FT. NOT the Greater Manchester charity 'ADS (Addiction Dependency Solutions)' (charity 702559, company 01990365, dissolved 2026) — match the exact registered name.",
    "spectrum_community_health": "Community interest company, not a charity: company 07300133, CQC provider 1-183173152. Prison healthcare (including substance misuse) and community services across Northern England. 'Spectrum' alone is generic — match only the registered name.",
    "aquarius": "Operating name 'Aquarius': charity 1014305, company 02427100 (active). West Midlands alcohol, drugs and gambling support. A subsidiary within the Waythrough group (via Richmond Fellowship) but still separately registered. 'Aquarius' alone is a common word — match only the registered form.",
    "action_on_addiction": "Charity 1117988, company 05947481 ('3 To 1' until 2007). Merged into The Forward Trust in May 2021; the shell company remains registered and the name is retained for some Forward Trust services. Itself formed in 2007 from the Chemical Dependency Centre, Clouds and the original Action on Addiction.",
    "lifeline_project": "Manchester drug and alcohol charity (est. 1971), company 01842240. Entered administration in 2017 after a Charity Commission inquiry into financial controls; services were taken over by Change Grow Live, Humankind and others. Company dissolved 25 Jan 2024; charity (515691) removed from the register, so no live charity number to seed. Appears as a co-respondent in older employment-tribunal judgments — see tests/test_m04_viability.py, which uses it as a real insolvency fixture.",
    "swanswell": "Swanswell Charitable Trust: charity 1074891, company 03692925, CQC provider 1-127628178. Rugby / Warwickshire drug and alcohol charity. Merged into Cranstoun in 2022; CQC registration archived 1 Nov 2021, company dissolved 18 Oct 2022.",
    "compass": "Compass: national charity (York, est. 1986), charity 518048, company 02054594, CQC provider 1-126775082 (CQC registers it as 'Compass - Services To Improve Health And Wellbeing'). Young-people-specialist plus adult substance misuse and wider health and wellbeing. 'Compass' alone is extremely common (unrelated 'Compass Group', 'Compass Clinic Limited' 1-152987221, 'Compass Wellbeing CIC') — match the full registered name.",
    "kca": "KCA (Kent Council on Addictions), registered as 'KENT COUNCIL ON ALCOHOLISM': charity 270532, company 01955497 ('KCA (UK)'). South East England's leading substance misuse charity until it became a wholly-owned subsidiary of Addaction on 1 Jan 2015; the shell company was dissolved 25 Apr 2017. Surviving entity is `with_you`. 'KCA' alone is a weak acronym — prefer 'Kent Council on Addictions'.",
    "blue_sky": "Blue Sky Development and Regeneration: charity 1118372, company 05639379. Social enterprise providing paid work for ex-offenders (grounds maintenance, recycling, catering). Merged into The Forward Trust in 2017 and now runs as 'Blue Sky Services'; the company was dissolved 7 Feb 2023. Surviving entity is `forward_trust`. Employment/regeneration rather than treatment, but part of the Forward Trust group. 'Blue Sky' alone is generic — match the fuller forms.",
    "recovery_focus": "Not a legal entity: the group brand under which Richmond Fellowship and Aquarius (and formerly DViP, 2Care, CAN, Croftlands Trust, My Time) operated from 2015 until the 2024 merger, when the group name became 'Waythrough'. No Companies House or Charity Commission registration of its own — the registered entities are `richmond_fellowship` and `aquarius`. Appears on older contracts and CQC quality accounts; resolve those to this key, then read across to the two entities.",
    "blenheim_cdp": "Blenheim Community Drug Project: large London drug and alcohol charity, charity 293959, company 01694712, CQC provider 1-516591398. Merged into Humankind in April 2019 (services kept the Blenheim name); company dissolved 26 Apr 2022. Evidence stays under this key; the surviving entity is `waythrough`.",
    "edp_drug_alcohol": "E D P Drug & Alcohol Services: Devon and Dorset charity, charity 297370, company 02145656, CQC provider 1-587977840. Became a Humankind subsidiary in April 2020 and fully merged into it on 1 Jul 2023; the surviving entity is `waythrough`. 'EDP' alone is a high-false-positive acronym — match the full registered name.",
    "bristol_drugs_project": "Independent Bristol charity (est. ~1986): charity 291714, company 01902326, CQC provider 1-126776288. Delivers the Bristol ROADS partnership. 'BDP' is a common acronym elsewhere — match 'Bristol Drugs Project' in full.",
    "developing_health_independence": "'DHI': charity 1078154, company 03830311, CQC provider 1-927177975. Bath-based; drug and alcohol treatment plus housing across Bath & North East Somerset, Bristol, Wiltshire and Somerset. 'DHI' alone is ambiguous — match the full name.",
    "neca": "North East Council on Addictions (registered as 'NECA'): charity 516516, company 01828287, CQC provider 1-126776368. Independent North East charity; adult and criminal-justice substance misuse.",
    "ley_community": "The Ley Community Drug Services: charity 1074874, company 03736193, CQC provider 1-101610029. Therapeutic-community residential rehab near Oxford (est. 1971). A wholly-owned subsidiary of Phoenix House since 2018, still separately registered; its board reports to the Phoenix Group Board. Surviving parent is `phoenix_futures`.",
    "practice_plus_group": "Practice Plus Group Health and Rehabilitation Services Limited: for-profit, not a charity. Company 10498997, CQC provider 1-3757899473. The Health in Justice arm (rebranded from Care UK Health in Justice in Oct 2020) is the leading independent provider of prison healthcare in England — ~47 establishments — with substance misuse among the services. 'Practice Plus Group' also runs urgent care, hospitals and diagnostics under other companies; match the Health and Rehabilitation Services entity for substance-misuse evidence.",
}

# provider_key -> (status, superseded_by). Seeded onto `providers.status` /
# `providers.superseded_by` (migration 0062) so the portal can show when an
# organisation on a comparison has been renamed, merged or dissolved.
# Anything absent from this map is 'active' with no successor. `superseded_by`
# is only set where there is exactly one — a rename points at the
# current-name key, an absorption at the acquirer; lifeline_project's
# services were split across several, so it stays NULL.
PROVIDER_STATUS: dict[str, tuple[str, str | None]] = {
    "addaction": ("renamed", "with_you"),
    "humankind": ("renamed", "waythrough"),
    "westminster_drug_project": ("renamed", "via"),
    "richmond_fellowship": ("merged", "waythrough"),
    "aquarius": ("merged", "waythrough"),
    "action_on_addiction": ("merged", "forward_trust"),
    "swanswell": ("merged", "cranstoun"),
    "blenheim_cdp": ("merged", "waythrough"),
    "edp_drug_alcohol": ("merged", "waythrough"),
    "ley_community": ("merged", "phoenix_futures"),
    "kca": ("merged", "with_you"),
    "blue_sky": ("merged", "forward_trust"),
    # A former group brand, not a legal entity — the group name is now
    # 'Waythrough'; the two registered entities it covered are tracked
    # under their own keys.
    "recovery_focus": ("renamed", "waythrough"),
    "lifeline_project": ("dissolved", None),
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

    # Further tracked providers added 2026-08-27 — national peers missing
    # from the original 13, plus four merged/dissolved organisations that
    # still appear in older evidence. Same verification as the block above:
    # charity/company numbers off the primary registers, CQC IDs off each
    # provider's current cqc.org.uk page. Status and successor are in
    # PROVIDER_STATUS.
    {
        "provider_key": "cranstoun",
        "scheme": "charity_number",
        "identifier": "1061582",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "cranstoun",
        "scheme": "company_number",
        "identifier": "03306337",
        "role": "charitable company limited by guarantee; 'Cranstoun Drug Services' until 2011",
    },
    {
        "provider_key": "cranstoun",
        "scheme": "cqc_provider_id",
        "identifier": "1-101678209",
        "role": "CQC-registered provider ('Cranstoun')",
    },
    {
        "provider_key": "changing_lives",
        "scheme": "charity_number",
        "identifier": "500640",
        "role": "registered charity (England and Wales); registered name 'The Cyrenians Ltd'",
    },
    {
        "provider_key": "changing_lives",
        "scheme": "company_number",
        "identifier": "00995799",
        "role": "charitable company limited by guarantee ('The Cyrenians Ltd', 'Tyneside Cyrenians Limited' until 2009)",
    },
    {
        "provider_key": "changing_lives",
        "scheme": "cqc_provider_id",
        "identifier": "1-144519557",
        "role": "CQC-registered provider ('The Cyrenians Ltd')",
    },
    {
        "provider_key": "alcohol_and_drug_service",
        "scheme": "charity_number",
        "identifier": "1108595",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "alcohol_and_drug_service",
        "scheme": "company_number",
        "identifier": "05375809",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "alcohol_and_drug_service",
        "scheme": "cqc_provider_id",
        "identifier": "1-152340136",
        "role": "CQC-registered provider ('The Alcohol and Drug Service')",
    },
    {
        "provider_key": "spectrum_community_health",
        "scheme": "company_number",
        "identifier": "07300133",
        "role": "community interest company (not a charity)",
    },
    {
        "provider_key": "spectrum_community_health",
        "scheme": "cqc_provider_id",
        "identifier": "1-183173152",
        "role": "CQC-registered provider ('Spectrum Community Health C.I.C.')",
    },
    {
        "provider_key": "aquarius",
        "scheme": "charity_number",
        "identifier": "1014305",
        "role": "registered charity (England and Wales); within the Waythrough group",
    },
    {
        "provider_key": "aquarius",
        "scheme": "company_number",
        "identifier": "02427100",
        "role": "charitable company limited by guarantee; within the Waythrough group",
    },
    {
        "provider_key": "action_on_addiction",
        "scheme": "charity_number",
        "identifier": "1117988",
        "role": "registered charity (England and Wales); merged into The Forward Trust 2021",
    },
    {
        "provider_key": "action_on_addiction",
        "scheme": "company_number",
        "identifier": "05947481",
        "role": "charitable company limited by guarantee ('3 To 1' until 2007); merged into The Forward Trust 2021",
    },
    {
        "provider_key": "action_on_addiction",
        "scheme": "cqc_provider_id",
        "identifier": "1-101649713",
        "role": "CQC-registered provider ('Action on Addiction')",
    },
    {
        "provider_key": "lifeline_project",
        "scheme": "company_number",
        "identifier": "01842240",
        "role": "charitable company limited by guarantee; dissolved 25 Jan 2024",
    },
    {
        "provider_key": "swanswell",
        "scheme": "charity_number",
        "identifier": "1074891",
        "role": "registered charity (England and Wales); merged into Cranstoun 2022",
    },
    {
        "provider_key": "swanswell",
        "scheme": "company_number",
        "identifier": "03692925",
        "role": "charitable company limited by guarantee; dissolved 18 Oct 2022",
    },
    {
        "provider_key": "swanswell",
        "scheme": "cqc_provider_id",
        "identifier": "1-127628178",
        "role": "CQC-registered provider ('Swanswell Charitable Trust'); archived 1 Nov 2021",
    },

    # Second expansion, 2026-08-27 — two entities absorbed into the
    # Humankind/Waythrough line, three active independent peers, a
    # phoenix_futures subsidiary, and the leading for-profit prison-
    # healthcare provider. Same verification: primary registers + each
    # provider's current cqc.org.uk page.
    {
        "provider_key": "blenheim_cdp",
        "scheme": "charity_number",
        "identifier": "293959",
        "role": "registered charity (England and Wales); merged into Humankind 2019",
    },
    {
        "provider_key": "blenheim_cdp",
        "scheme": "company_number",
        "identifier": "01694712",
        "role": "charitable company limited by guarantee; dissolved 26 Apr 2022",
    },
    {
        "provider_key": "blenheim_cdp",
        "scheme": "cqc_provider_id",
        "identifier": "1-516591398",
        "role": "CQC-registered provider ('Blenheim CDP')",
    },
    {
        "provider_key": "edp_drug_alcohol",
        "scheme": "charity_number",
        "identifier": "297370",
        "role": "registered charity (England and Wales); merged into Humankind 1 Jul 2023",
    },
    {
        "provider_key": "edp_drug_alcohol",
        "scheme": "company_number",
        "identifier": "02145656",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "edp_drug_alcohol",
        "scheme": "cqc_provider_id",
        "identifier": "1-587977840",
        "role": "CQC-registered provider ('E D P Drug & Alcohol Services')",
    },
    {
        "provider_key": "bristol_drugs_project",
        "scheme": "charity_number",
        "identifier": "291714",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "bristol_drugs_project",
        "scheme": "company_number",
        "identifier": "01902326",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "bristol_drugs_project",
        "scheme": "cqc_provider_id",
        "identifier": "1-126776288",
        "role": "CQC-registered provider ('Bristol Drugs Project Limited')",
    },
    {
        "provider_key": "developing_health_independence",
        "scheme": "charity_number",
        "identifier": "1078154",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "developing_health_independence",
        "scheme": "company_number",
        "identifier": "03830311",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "developing_health_independence",
        "scheme": "cqc_provider_id",
        "identifier": "1-927177975",
        "role": "CQC-registered provider ('Developing Health and Independence')",
    },
    {
        "provider_key": "neca",
        "scheme": "charity_number",
        "identifier": "516516",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "neca",
        "scheme": "company_number",
        "identifier": "01828287",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "neca",
        "scheme": "cqc_provider_id",
        "identifier": "1-126776368",
        "role": "CQC-registered provider ('NECA')",
    },
    {
        "provider_key": "ley_community",
        "scheme": "charity_number",
        "identifier": "1074874",
        "role": "registered charity (England and Wales); wholly-owned subsidiary of Phoenix House",
    },
    {
        "provider_key": "ley_community",
        "scheme": "company_number",
        "identifier": "03736193",
        "role": "charitable company limited by guarantee; wholly-owned subsidiary of Phoenix House",
    },
    {
        "provider_key": "ley_community",
        "scheme": "cqc_provider_id",
        "identifier": "1-101610029",
        "role": "CQC-registered provider ('Ley Community Drug Services')",
    },
    {
        "provider_key": "practice_plus_group",
        "scheme": "company_number",
        "identifier": "10498997",
        "role": "private limited company (not a charity); 'Practice Plus Group Health and Rehabilitation Services Limited'",
    },
    {
        "provider_key": "practice_plus_group",
        "scheme": "cqc_provider_id",
        "identifier": "1-3757899473",
        "role": "CQC-registered provider ('Practice Plus Group Health and Rehabilitation Services Limited')",
    },

    # Third small batch, 2026-08-27 — Compass (active national charity),
    # KCA and Blue Sky (absorbed into with_you / forward_trust), and
    # recovery_focus (a former group brand, no registration of its own).
    {
        "provider_key": "compass",
        "scheme": "charity_number",
        "identifier": "518048",
        "role": "registered charity (England and Wales)",
    },
    {
        "provider_key": "compass",
        "scheme": "company_number",
        "identifier": "02054594",
        "role": "charitable company limited by guarantee",
    },
    {
        "provider_key": "compass",
        "scheme": "cqc_provider_id",
        "identifier": "1-126775082",
        "role": "CQC-registered provider ('Compass - Services To Improve Health And Wellbeing')",
    },
    {
        "provider_key": "kca",
        "scheme": "charity_number",
        "identifier": "270532",
        "role": "registered charity (England and Wales), 'Kent Council on Alcoholism'; subsidiary of Addaction from 2015",
    },
    {
        "provider_key": "kca",
        "scheme": "company_number",
        "identifier": "01955497",
        "role": "charitable company limited by guarantee ('KCA (UK)'); dissolved 25 Apr 2017",
    },
    {
        "provider_key": "blue_sky",
        "scheme": "charity_number",
        "identifier": "1118372",
        "role": "registered charity (England and Wales); merged into The Forward Trust 2017",
    },
    {
        "provider_key": "blue_sky",
        "scheme": "company_number",
        "identifier": "05639379",
        "role": "charitable company limited by guarantee; dissolved 7 Feb 2023",
    },
]


def seed_rows() -> tuple[list[dict], list[dict]]:
    """Returns (providers, provider_identifiers) rows to upsert."""
    providers = []
    for key, variants in SUPPLIER_NAME_VARIANTS.items():
        status, superseded_by = PROVIDER_STATUS.get(key, ("active", None))
        providers.append({
            "provider_key": key,
            "canonical_name": variants[0],
            "is_target": 1 if key == TARGET_PROVIDER_KEY else 0,
            "notes": PROVIDER_NOTES.get(key),
            "status": status,
            "superseded_by": superseded_by,
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
        "SELECT status FROM provider_identifiers WHERE provider_key = %s AND scheme = %s AND identifier = %s",
        (provider_key, scheme, identifier),
    ).fetchone()
    if existing and existing["status"] == "verified":
        return
    db.upsert(conn, "provider_identifiers", {
        "provider_key": provider_key, "scheme": scheme, "identifier": identifier,
        "role": role, "status": "unverified", "discovered_by": discovered_by,
    }, natural_key=["provider_key", "scheme", "identifier"])
