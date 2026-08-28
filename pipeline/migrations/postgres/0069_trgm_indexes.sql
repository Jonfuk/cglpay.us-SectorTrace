-- Trigram indexes, PostgreSQL dialect of ../0069_trgm_indexes.sql.
--
-- `pg_trgm` GIN indexes behind `similarity()` / `%` ranking, for two things:
--
--   * the operator's fuzzy-name search over the review queue — an
--     `unmatched_buyer_name` item ranked against `authorities.name`, a
--     `possible_group_company` item against `companies.company_name` and
--     `providers.canonical_name` (pipeline/web/review.py);
--   * the portal's contract supplier/buyer text filter, which becomes an
--     index scan instead of a full `ILIKE '%...%'` sweep of 98k rows
--     (pipeline/web/public_queries.py).
--
-- Ranking only. Nothing here resolves a name — a person still confirms every
-- match and writes the override (pipeline/buyer_name_overrides.py, settled
-- decision 4's spirit: judgement is not automated).
--
-- Guarded: on a server that carries neither `pg_trgm` nor the right to
-- `CREATE EXTENSION` it (an unusual managed PostgreSQL — the extension is
-- contrib and normally present), the indexes are skipped and the queries
-- fall back to a sequential scan, exactly as the SQLite path already does.
-- `db.ensure_extensions()` has already attempted the `CREATE EXTENSION` by
-- the time this runs.
--
-- The SQLite tree declares the same index NAMES as plain btrees so the two
-- object inventories match (tests/test_migration_equivalence.py).

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS idx_authorities_name_trgm
            ON authorities USING gin (name gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_companies_name_trgm
            ON companies USING gin (company_name gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_providers_name_trgm
            ON providers USING gin (canonical_name gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_contracts_supplier_name_trgm
            ON contracts USING gin (supplier_name_raw gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_contracts_buyer_name_trgm
            ON contracts USING gin (buyer_name gin_trgm_ops);
    ELSE
        RAISE NOTICE 'pg_trgm not installed - trigram indexes skipped; fuzzy name search and the contract text filter will sequential-scan';
    END IF;
END $$;
