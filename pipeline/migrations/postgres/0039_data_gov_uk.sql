-- Module 19: data.gov.uk CKAN catalogue.
--
-- Discovery metadata, not data: what datasets exist in the central open-data
-- catalogue and where their resources live. A dataset row accumulates every
-- term and every organisation link that found it, across runs and across the
-- keyword and organisation passes, so `matched_terms` is the complete record
-- of how this pipeline has found it -- and its absence means it has not been
-- found, which is not the same as the dataset not existing.
--
-- PostgreSQL dialect of ../0039_data_gov_uk.sql. See README.md in this directory for
-- the conversion rules; the porting decisions specific to this file are
-- commented where they occur.

CREATE TABLE IF NOT EXISTS data_gov_uk_datasets (
    dataset_id           text PRIMARY KEY,   -- the catalogue's own id
    title                text,
    notes                text,               -- the catalogue's description, verbatim
    organisation_name    text,               -- as the catalogue spells it
    organisation_id      text,
    license_id           text,               -- the catalogue's own per-dataset terms;
    license_title        text,               -- the catalogue mixes OGL and non-OGL
    license_url          text,
    url                  text,
    date_released        text,
    date_updated         text,
    metadata_modified    text,
    dataset_state        text,
    matched_terms        text,               -- comma-joined; accumulates across runs
    matched_ons_code     text,               -- set by the organisation pass
    matched_provider_key text,
    source_url           text NOT NULL,
    retrieved_at         text NOT NULL,
    http_status          bigint NOT NULL,
    source_system        text NOT NULL,
    payload_sha256       text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_data_gov_uk_datasets_org
    ON data_gov_uk_datasets (organisation_name);

CREATE TABLE IF NOT EXISTS data_gov_uk_resources (
    dataset_id          text NOT NULL,
    resource_id         text NOT NULL,
    resource_name       text,
    resource_format     text,
    resource_url        text,
    resource_description text,
    resource_position   bigint,
    source_url          text NOT NULL,
    retrieved_at        text NOT NULL,
    http_status         bigint NOT NULL,
    source_system       text NOT NULL,
    payload_sha256      text NOT NULL,
    PRIMARY KEY (dataset_id, resource_id)
);
