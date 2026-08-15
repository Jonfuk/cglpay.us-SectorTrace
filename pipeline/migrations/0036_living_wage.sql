-- Module 18: Living Wage Foundation accreditation.
--
-- The register is a Drupal views page of accredited employers. A provider
-- is searched once per run (its canonical name variant) and the outcome is
-- binary: the exact name is on the list, or it is not. `found = 0` is a
-- real answer -- the lookup happened, the payload is archived -- and the
-- caveat travels in the docs: accreditation may sit under another legal
-- name, which is what the review queue exists to catch.

CREATE TABLE IF NOT EXISTS living_wage_accreditations (
    provider_key      TEXT NOT NULL,
    searched_variant  TEXT NOT NULL,
    accredited        INTEGER NOT NULL,  -- 1: an exact-name match was on the list
                                         -- 0: not on the list under any checked name
    employer_name     TEXT,              -- as the register spells it
    employer_node_id  TEXT,              -- the register's own node id
    match_basis       TEXT,              -- 'exact' when found; NULL when not
    pages_checked     INTEGER NOT NULL,  -- how many result pages were read
    employers_total   INTEGER,           -- the register's own count line for the search
    source_url        TEXT NOT NULL,
    retrieved_at      TEXT NOT NULL,
    http_status       INTEGER NOT NULL,
    source_system     TEXT NOT NULL,
    payload_sha256    TEXT NOT NULL,
    PRIMARY KEY (provider_key, searched_variant)
);
