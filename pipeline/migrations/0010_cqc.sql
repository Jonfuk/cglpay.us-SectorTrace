-- Module 5: CQC registered locations.
--
-- IMPORTANT SCOPE LIMIT (also recorded in docs/CAVEATS.md): CQC registration
-- covers only certain regulated activities — residential detoxification,
-- inpatient care and some prescribing services. A large share of community
-- drug and alcohol provision is NOT CQC-registered, so this table is a map
-- of regulated locations, never a complete service map. Counting locations
-- per authority and reading it as service coverage would be wrong.

CREATE TABLE IF NOT EXISTS cqc_providers (
    provider_id             TEXT PRIMARY KEY,
    provider_key             TEXT,
    provider_name             TEXT NOT NULL,
    companies_house_number     TEXT,
    charity_number              TEXT,
    registration_status          TEXT,
    registration_date             TEXT,
    ownership_type                 TEXT,
    organisation_type               TEXT,
    postal_code                      TEXT,
    match_basis                       TEXT, -- 'exact_name' only; near misses go to review_queue
    source_url                         TEXT NOT NULL,
    retrieved_at                        TEXT NOT NULL,
    http_status                          INTEGER NOT NULL,
    source_system                         TEXT NOT NULL,
    payload_sha256                         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cqc_locations (
    location_id              TEXT PRIMARY KEY,
    provider_id               TEXT NOT NULL,
    provider_key               TEXT,
    location_name               TEXT,
    postal_code                  TEXT,
    latitude                      REAL,
    longitude                      REAL,
    local_authority_raw             TEXT,  -- as CQC states it
    local_authority_ons_code         TEXT, -- resolved against authorities; NULL if unmatched
    region                            TEXT,
    registration_status                TEXT,
    registration_date                   TEXT,
    last_inspection_date                 TEXT,
    overall_rating                        TEXT,
    overall_rating_date                    TEXT,
    regulated_activities                    TEXT, -- comma-joined
    service_types                            TEXT, -- comma-joined gacServiceTypes
    source_url                                TEXT NOT NULL,
    retrieved_at                               TEXT NOT NULL,
    http_status                                 INTEGER NOT NULL,
    source_system                                TEXT NOT NULL,
    payload_sha256                                TEXT NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES cqc_providers (provider_id)
);

CREATE INDEX IF NOT EXISTS idx_cqc_locations_provider ON cqc_locations (provider_id);
CREATE INDEX IF NOT EXISTS idx_cqc_locations_authority ON cqc_locations (local_authority_ons_code);

CREATE TABLE IF NOT EXISTS cqc_location_reports (
    location_id        TEXT NOT NULL,
    report_link_id      TEXT NOT NULL,
    report_date          TEXT,
    first_visit_date      TEXT,
    report_uri             TEXT,
    source_url              TEXT NOT NULL,
    retrieved_at             TEXT NOT NULL,
    http_status               INTEGER NOT NULL,
    source_system              TEXT NOT NULL,
    payload_sha256              TEXT NOT NULL,
    PRIMARY KEY (location_id, report_link_id)
);

-- RESTRICTED: CQC embeds named registered managers inside each location's
-- regulatedActivities. Named individuals never reach an export.
CREATE TABLE IF NOT EXISTS restricted_cqc_location_contacts (
    location_id       TEXT NOT NULL,
    contact_ref        TEXT NOT NULL,
    person_name         TEXT,
    person_role          TEXT,
    regulated_activity    TEXT,
    PRIMARY KEY (location_id, contact_ref)
);
