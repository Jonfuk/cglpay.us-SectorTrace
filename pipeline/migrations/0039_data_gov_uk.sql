-- Module 19: data.gov.uk CKAN catalogue.
--
-- Discovery metadata, not data: what datasets exist in the central open-data
-- catalogue and where their resources live. A dataset row accumulates every
-- term and every organisation link that found it, across runs and across the
-- keyword and organisation passes, so `matched_terms` is the complete record
-- of how this pipeline has found it -- and its absence means it has not been
-- found, which is not the same as the dataset not existing.

CREATE TABLE IF NOT EXISTS data_gov_uk_datasets (
    dataset_id           TEXT PRIMARY KEY,   -- the catalogue's own id
    title                TEXT,
    notes                TEXT,               -- the catalogue's description, verbatim
    organisation_name    TEXT,               -- as the catalogue spells it
    organisation_id      TEXT,
    license_id           TEXT,               -- the catalogue's own per-dataset terms;
    license_title        TEXT,               -- the catalogue mixes OGL and non-OGL
    license_url          TEXT,
    url                  TEXT,
    date_released        TEXT,
    date_updated         TEXT,
    metadata_modified    TEXT,
    dataset_state        TEXT,
    matched_terms        TEXT,               -- comma-joined; accumulates across runs
    matched_ons_code     TEXT,               -- set by the organisation pass
    matched_provider_key TEXT,
    source_url           TEXT NOT NULL,
    retrieved_at         TEXT NOT NULL,
    http_status          INTEGER NOT NULL,
    source_system        TEXT NOT NULL,
    payload_sha256       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_data_gov_uk_datasets_org
    ON data_gov_uk_datasets (organisation_name);

CREATE TABLE IF NOT EXISTS data_gov_uk_resources (
    dataset_id          TEXT NOT NULL,
    resource_id         TEXT NOT NULL,
    resource_name       TEXT,
    resource_format     TEXT,
    resource_url        TEXT,
    resource_description TEXT,
    resource_position   INTEGER,
    source_url          TEXT NOT NULL,
    retrieved_at        TEXT NOT NULL,
    http_status         INTEGER NOT NULL,
    source_system       TEXT NOT NULL,
    payload_sha256      TEXT NOT NULL,
    PRIMARY KEY (dataset_id, resource_id)
);
