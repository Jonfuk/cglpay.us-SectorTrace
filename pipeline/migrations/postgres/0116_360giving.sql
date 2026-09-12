-- Module 36: 360Giving grants (received and made) for tracked providers.
--
-- Feasibility: docs/m36-360giving-grantnav-feasibility.md. Scoped to the
-- tracked providers' own charity/company numbers via provider_identifiers --
-- the same lookup m03/m04 already do against their own sources -- rather
-- than the API's full 454,270-organisation universe. This is reconciliation
-- by known identifier, never by name, the same discipline m23's match_basis
-- enforces for the sector universe.
--
-- Grants are money received or made by a tracked provider and belong to the
-- 'finance' evidence layer, but are never summed with m01 contract value or
-- m11 public health grant allocations: different populations, different
-- reference periods, a different publisher for every row. See
-- docs/CAVEATS.md, "360Giving grants (Module 36)".
--
-- direction distinguishes a grant a provider received from one it made,
-- rather than two near-identical tables -- the ticket's own two-sided ask
-- ("grants made and received"). matched_scheme/matched_identifier record
-- which of a provider's identifiers found this grant: the same real
-- organisation appears under both a GB-CHC and a GB-COH id on different
-- grants in the live API (confirmed against Change Grow Live), so a
-- provider with both identifiers is looked up under both, and this pair
-- says which one this particular row came from. data_license is stored per
-- grant, not asserted once for the module -- the API attaches a licence to
-- every row and it varies by publisher (CC BY 4.0, OGL v3.0, CC BY-SA 4.0
-- and CC0 all seen live).
CREATE TABLE IF NOT EXISTS three_sixty_giving_grants (
    grant_id              text NOT NULL,
    direction             text NOT NULL, -- 'received' | 'made'
    provider_key          text NOT NULL,
    matched_scheme        text NOT NULL, -- 'charity_number' | 'company_number'
    matched_identifier    text NOT NULL,
    counterparty_org_id   text,
    counterparty_name     text,
    title                 text,
    description           text,
    amount_awarded        double precision,
    currency              text,
    award_date_raw        text, -- verbatim; publishers mix bare dates and full timestamps
    award_date            text, -- normalised YYYY-MM-DD, NULL when unparseable
    date_modified         text, -- verbatim; present on some grants, absent on others
    grant_programme_title text,
    data_license_url      text,
    data_license_name     text,
    source_url            text NOT NULL,
    retrieved_at          text NOT NULL,
    http_status           bigint NOT NULL,
    source_system         text NOT NULL,
    payload_sha256        text NOT NULL,
    PRIMARY KEY (grant_id, direction, provider_key),
    FOREIGN KEY (provider_key) REFERENCES providers (provider_key),
    CHECK (direction IN ('received', 'made')),
    CHECK (matched_scheme IN ('charity_number', 'company_number'))
);

CREATE INDEX IF NOT EXISTS idx_360g_grants_provider ON three_sixty_giving_grants (provider_key);
