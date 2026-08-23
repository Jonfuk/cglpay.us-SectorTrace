-- PostgreSQL dialect of ../0058_procurement_channel_sightings.sql. See
-- README.md in this directory for the conversion rules.
CREATE TABLE IF NOT EXISTS procurement_channel_sightings (
    notice_id                TEXT NOT NULL,
    source_system              TEXT NOT NULL,
    ocid                          TEXT,
    buyer_name                     TEXT,
    title                             TEXT,
    cpv_codes                          TEXT,
    tender_value_amount                  double precision,
    tender_value_currency                  TEXT,
    total_award_value_amount                 double precision,
    supplier_names                             TEXT,
    date_published                               TEXT,
    source_url                                     TEXT NOT NULL,
    retrieved_at                                     TEXT NOT NULL,
    http_status                                        bigint NOT NULL,
    payload_sha256                                       TEXT NOT NULL,
    PRIMARY KEY (notice_id, source_system)
);

CREATE INDEX IF NOT EXISTS idx_procurement_sightings_notice ON procurement_channel_sightings (notice_id);
