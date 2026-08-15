-- Module 18: Living Wage Foundation accreditation.
--
-- The register is a Drupal views page of accredited employers. A provider
-- is searched once per run (its canonical name variant) and the outcome is
-- binary: the exact name is on the list, or it is not. `found = 0` is a
-- real answer -- the lookup happened, the payload is archived -- and the
-- caveat travels in the docs: accreditation may sit under another legal
-- name, which is what the review queue exists to catch.
--
-- PostgreSQL dialect of ../0036_living_wage.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS living_wage_accreditations (
    provider_key      text NOT NULL,
    searched_variant  text NOT NULL,
    accredited        bigint NOT NULL,  -- 1: an exact-name match was on the list
                                        -- 0: not on the list under any checked name
    employer_name     text,              -- as the register spells it
    employer_node_id  text,              -- the register's own node id
    match_basis       text,              -- 'exact' when found; NULL when not
    pages_checked     bigint NOT NULL,  -- how many result pages were read
    employers_total   bigint,           -- the register's own count line for the search
    source_url        text NOT NULL,
    retrieved_at      text NOT NULL,
    http_status       bigint NOT NULL,
    source_system     text NOT NULL,
    payload_sha256    text NOT NULL,
    PRIMARY KEY (provider_key, searched_variant)
);
