-- Trigram indexes, SQLite dialect.
--
-- On PostgreSQL (../postgres/0069_trgm_indexes.sql) these are `pg_trgm` GIN
-- indexes that make `similarity()` ranking cheap: the operator's fuzzy-name
-- search over the review queue (`unmatched_buyer_name` -> an authority,
-- `possible_group_company` -> a known company or provider) and the portal's
-- contract supplier/buyer text filter.
--
-- SQLite has no trigram index. Its fuzzy path is `difflib` in Python
-- (pipeline/web/review.py), and the portal's text filter is `LIKE`. These
-- plain btrees exist for name-parity with the PostgreSQL tree —
-- tests/test_migration_equivalence.py compares the object inventories the two
-- trees declare and they must match — and two of them (`buyer_name`,
-- `company_name`) are useful equality indexes in their own right regardless.
--
-- Nothing here resolves a name. A trigram score orders candidates for a
-- person to confirm; the override is still a human decision
-- (pipeline/buyer_name_overrides.py).

CREATE INDEX IF NOT EXISTS idx_authorities_name_trgm ON authorities (name);
CREATE INDEX IF NOT EXISTS idx_companies_name_trgm ON companies (company_name);
CREATE INDEX IF NOT EXISTS idx_providers_name_trgm ON providers (canonical_name);
CREATE INDEX IF NOT EXISTS idx_contracts_supplier_name_trgm ON contracts (supplier_name_raw);
CREATE INDEX IF NOT EXISTS idx_contracts_buyer_name_trgm ON contracts (buyer_name);
