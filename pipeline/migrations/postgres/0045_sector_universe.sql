-- Phase 18 (F1): the sector universe — the population workstream's table.
--
-- PostgreSQL dialect of ../0045_sector_universe.sql. See README.md in this
-- directory for the conversion rules; the porting decisions specific to this
-- file are commented where they occur.
--
-- The argument for a new table rather than an extension of `providers`
-- lives in the SQLite original. The short version: `providers` is
-- REFERENCE/CONFIG seeded from code, the universe is evidence-derived and
-- unbounded, and its rows must keep m04's match-basis discipline
-- ('seed' | 'register' | 'ppon' | 'name_only_unconfirmed'). provider_key
-- is set only through provider_identifiers, never on a name.

CREATE TABLE IF NOT EXISTS sector_universe (
    entity_key      text PRIMARY KEY,
    canonical_name  text NOT NULL,
    normalised_name text,
    entity_type     text NOT NULL,
    company_number  text,
    charity_number  text,
    cqc_provider_id text,
    ppon            text,
    provider_key    text,
    match_basis     text NOT NULL,
    first_seen      text,
    last_seen       text,
    notices_count   bigint,
    source_system   text,
    source_url      text,
    retrieved_at    text,
    payload_sha256  text
);

CREATE INDEX IF NOT EXISTS idx_sector_universe_company ON sector_universe (company_number);
CREATE INDEX IF NOT EXISTS idx_sector_universe_charity ON sector_universe (charity_number);
CREATE INDEX IF NOT EXISTS idx_sector_universe_name ON sector_universe (normalised_name);
CREATE INDEX IF NOT EXISTS idx_sector_universe_provider ON sector_universe (provider_key);
