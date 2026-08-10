-- Provider entity model: the second stable entity alongside `authorities`.
--
-- Modules 2/3/4/5 (tribunals, charity finance, companies, CQC) and Module 1
-- (procurement) all hang off provider_key, so the whole evidence base can be
-- navigated per-provider as well as per-authority.
--
-- These two tables are REFERENCE/CONFIG, not evidence: they're seeded
-- deterministically from pipeline/providers.py on every run and carry no
-- provenance columns — same treatment as supplier_aliases. Anything fetched
-- from a source (charity financials, filings, tribunal cases) goes in its own
-- evidence table, references provider_key, and carries full provenance.

CREATE TABLE IF NOT EXISTS providers (
    provider_key      TEXT PRIMARY KEY, -- stable slug, matches keywords.SUPPLIER_NAME_VARIANTS keys
    canonical_name     TEXT NOT NULL,
    is_target           INTEGER NOT NULL DEFAULT 0, -- 1 = campaign subject (CGL), 0 = comparator
    notes                TEXT
);

-- External identifiers for a provider. `status` distinguishes an identifier
-- asserted in config (and therefore human-verified) from one discovered by a
-- module, which must be confirmed before it's trusted for joins.
--
-- Deliberately many-to-one: a provider commonly has several company numbers
-- (the charity plus its trading subsidiaries), and the entity that holds a
-- contract is often not the entity that employs the staff — which is exactly
-- the distinction Module 4 exists to make visible, so the schema must not
-- collapse it.
CREATE TABLE IF NOT EXISTS provider_identifiers (
    provider_key     TEXT NOT NULL,
    scheme            TEXT NOT NULL, -- 'charity_number' | 'company_number' | 'cqc_provider_id' | 'ppon'
    identifier         TEXT NOT NULL,
    role                TEXT,         -- free text, e.g. 'registered charity', 'trading subsidiary'
    status               TEXT NOT NULL DEFAULT 'unverified', -- 'verified' (config-asserted) | 'unverified' (module-discovered)
    discovered_by         TEXT,        -- module name, when not config-seeded
    PRIMARY KEY (provider_key, scheme, identifier),
    FOREIGN KEY (provider_key) REFERENCES providers (provider_key)
);

CREATE INDEX IF NOT EXISTS idx_provider_identifiers_scheme ON provider_identifiers (scheme, identifier);
