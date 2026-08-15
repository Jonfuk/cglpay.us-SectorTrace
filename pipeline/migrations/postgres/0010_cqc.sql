-- Module 5: CQC registered locations.
--
-- IMPORTANT SCOPE LIMIT (also recorded in docs/CAVEATS.md): CQC registration
-- covers only certain regulated activities — residential detoxification,
-- inpatient care and some prescribing services. A large share of community
-- drug and alcohol provision is NOT CQC-registered, so this table is a map
-- of regulated locations, never a complete service map. Counting locations
-- per authority and reading it as service coverage would be wrong.

--
-- PostgreSQL dialect of ../0010_cqc.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS cqc_providers (
    provider_id             text PRIMARY KEY,
    provider_key             text,
    provider_name             text NOT NULL,
    companies_house_number     text,
    charity_number              text,
    registration_status          text,
    registration_date             text,
    ownership_type                 text,
    organisation_type               text,
    postal_code                      text,
    match_basis                       text, -- 'exact_name' only; near misses go to review_queue
    source_url                         text NOT NULL,
    retrieved_at                        text NOT NULL,
    http_status                          bigint NOT NULL,
    source_system                         text NOT NULL,
    payload_sha256                         text NOT NULL
);

CREATE TABLE IF NOT EXISTS cqc_locations (
    location_id              text PRIMARY KEY,
    provider_id               text NOT NULL,
    provider_key               text,
    location_name               text,
    postal_code                  text,
    latitude                      double precision,
    longitude                      double precision,
    local_authority_raw             text,  -- as CQC states it
    local_authority_ons_code         text, -- resolved against authorities; NULL if unmatched
    region                            text,
    registration_status                text,
    registration_date                   text,
    last_inspection_date                 text,
    overall_rating                        text,
    overall_rating_date                    text,
    regulated_activities                    text, -- comma-joined
    service_types                            text, -- comma-joined gacServiceTypes
    source_url                                text NOT NULL,
    retrieved_at                               text NOT NULL,
    http_status                                 bigint NOT NULL,
    source_system                                text NOT NULL,
    payload_sha256                                text NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES cqc_providers (provider_id)
);

CREATE INDEX IF NOT EXISTS idx_cqc_locations_provider ON cqc_locations (provider_id);
CREATE INDEX IF NOT EXISTS idx_cqc_locations_authority ON cqc_locations (local_authority_ons_code);

CREATE TABLE IF NOT EXISTS cqc_location_reports (
    location_id        text NOT NULL,
    report_link_id      text NOT NULL,
    report_date          text,
    first_visit_date      text,
    report_uri             text,
    source_url              text NOT NULL,
    retrieved_at             text NOT NULL,
    http_status               bigint NOT NULL,
    source_system              text NOT NULL,
    payload_sha256              text NOT NULL,
    PRIMARY KEY (location_id, report_link_id)
);

-- RESTRICTED: CQC embeds named registered managers inside each location's
-- regulatedActivities. Named individuals never reach an export.
CREATE TABLE IF NOT EXISTS restricted_cqc_location_contacts (
    location_id       text NOT NULL,
    contact_ref        text NOT NULL,
    person_name         text,
    person_role          text,
    regulated_activity    text,
    PRIMARY KEY (location_id, contact_ref)
);
