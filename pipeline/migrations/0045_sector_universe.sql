-- Phase 18 (F1): the sector universe — the population workstream's table.
--
-- The thesis the phase delivers on: the pipeline tracks 13 providers and 347
-- authorities, but the denominator — how many organisations make up the
-- sector — was unknown. Every coverage statement ("we track N of the
-- sector's ~M providers") needs a universe to be measured against, and none
-- existed. The universe is the upstream condition for the coverage matrix
-- (W-12) meaning anything beyond the 347, for the claims index's sector-level
-- claims, and for any sentence of the form "we track N of the sector's ~M".
--
-- WHY A NEW TABLE RATHER THAN AN EXTENSION OF `providers`. `providers` is
-- REFERENCE/CONFIG: seeded deterministically from pipeline/providers.py on
-- every run, carries no provenance columns, and is the human-curated list of
-- the campaign's tracked entities. The universe is the opposite shape: it is
-- EVIDENCE-DERIVED, reconstructed from sources the pipeline already reads
-- (the awardees in the contracts, the charity register, Companies House,
-- CQC registrations), it numbers in the tens of thousands rather than
-- thirteen, and its rows must keep the match-basis discipline m04 set or it
-- becomes a larger and less verifiable version of the problem it was built
-- to solve. Bolting that onto `providers` would have made the config table
-- unbounded and the universe table restricted to what config can hold.
-- Organisations are not personal data, so the `restricted_` discipline does
-- not reach this table.
--
-- match_basis is m04's vocabulary extended to three new capture kinds:
--
--   'seed'                    asserted in this project's config (the tracked
--                             providers) or carried over from a company row
--                             whose own match_basis was 'seed' — an
--                             identifier from an authoritative
--                             cross-reference.
--   'register'                identified by an identifier the source itself
--                             published (a charity number, a CQC provider
--                             id). The row is a real registered entity; the
--                             link to a tracked provider is still made only
--                             through provider_identifiers.
--   'ppon'                    identified only by the supplier's GB-PPON
--                             registration id on the notices. The id is
--                             self-declared by the buyer's platform, so it
--                             identifies the supplier's registration, never
--                             the legal entity, and never sets provider_key.
--   'name_only_unconfirmed'   captured from a name alone — an awardee or
--                             buyer name, or a company search result. NOT
--                             linked to any provider, and NOT asserted to be
--                             the same legal entity as anything. m04's rule
--                             verbatim: sharing a name is not sharing an
--                             identity.
--
-- provider_key is set only where an identifier in provider_identifiers
-- matches one of the row's identifiers. provider_identifiers only ever holds
-- identifiers from authoritative cross-references (config, the charity
-- register, CQC), so a name-only row — which has no identifiers — can never
-- acquire one. That is the whole safety argument of the universe, and it is
-- the same argument m04 makes for companies.
--
-- A 'name_only_unconfirmed' row may still carry a company_number: the
-- possible_group_company review items hold the number their search returned,
-- and recording it is capturing the identifier, not asserting the link.
-- match_basis says how the row ENTERED the universe, not the provenance of
-- every identifier it carries.
--
-- provenance columns are representative: a row derived from many notices
-- carries the source_url/retrieved_at/hash of one of them (the newest),
-- because the row is an aggregate over evidence that keeps its own
-- provenance in its own table. Rows derived from review items carry NULL —
-- the item itself is the record of where the candidate came from.

CREATE TABLE IF NOT EXISTS sector_universe (
    entity_key      TEXT PRIMARY KEY, -- company/charity/cqc id, or a hash of the normalised name
    canonical_name  TEXT NOT NULL,    -- the first spelling that captured the row
    normalised_name TEXT,             -- the merge key; equal where two captures are the same string
    entity_type     TEXT NOT NULL,    -- 'provider' | 'company' | 'charity' | 'cqc_provider' | 'awardee' | 'funder'
    company_number  TEXT,
    charity_number  TEXT,
    cqc_provider_id TEXT,
    ppon            TEXT,
    provider_key    TEXT,             -- only ever via provider_identifiers; NULL on name-only rows
    match_basis     TEXT NOT NULL,    -- 'seed' | 'register' | 'ppon' | 'name_only_unconfirmed'
    first_seen      TEXT,             -- earliest date observed in the capturing source
    last_seen       TEXT,             -- latest date observed
    notices_count   INTEGER,          -- distinct notices naming it, where any exist
    source_system   TEXT,             -- the table the row was first derived from
    source_url      TEXT,
    retrieved_at    TEXT,
    payload_sha256  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sector_universe_company ON sector_universe (company_number);
CREATE INDEX IF NOT EXISTS idx_sector_universe_charity ON sector_universe (charity_number);
CREATE INDEX IF NOT EXISTS idx_sector_universe_name ON sector_universe (normalised_name);
CREATE INDEX IF NOT EXISTS idx_sector_universe_provider ON sector_universe (provider_key);
