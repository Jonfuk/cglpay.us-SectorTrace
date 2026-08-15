-- Module 21: ONS ASHE earnings, via the ONS developer API (Data Explorer).
--
-- The comparator market: median gross hourly pay (excluding overtime) as the
-- Annual Survey of Hours and Earnings publishes it, for the occupation groups
-- (SOC 2010, two-digit) and industry groups (SIC 2007, two-digit) the sector's
-- workforce sits in, at UK and England geography, all published tax years of
-- the version the API serves.
--
-- One observation per (dataset, version, measure, dimension, code, geography,
-- time) -- the natural key is what ONE request returns; the measure is part
-- of it so a future collection of a second measure cannot silently overwrite
-- this one. Codes are pinned in the module config (SOC/SIC codes are stable
-- standards); labels are pinned there too, because the API's code-list items
-- carry no label text (verified 2026-08-15).
--
-- The gate from the phase plan governs anything built on this table: an
-- ASHE-versus-adverts statement is a side-by-side comparison, never an
-- arithmetic ratio, and nothing in the module computes one.

CREATE TABLE IF NOT EXISTS ons_ashe_observations (
    dataset_id             TEXT NOT NULL,  -- 'ashe-tables-3' (occupation) | 'ashe-table-5' (industry)
    dataset_title          TEXT,           -- the catalogue's own title for the dataset
    edition                TEXT NOT NULL,  -- 'time-series'
    version                TEXT NOT NULL,  -- the API version the observation came from
    hoursandearnings       TEXT NOT NULL,  -- 'hourly-pay-excluding-overtime' (the measure)
    averagesandpercentiles TEXT NOT NULL,  -- 'median'
    sex                    TEXT NOT NULL,  -- 'all'
    workingpattern         TEXT NOT NULL,  -- 'all'
    dimension_kind         TEXT NOT NULL,  -- 'occupation' | 'industry'
    dimension_code         TEXT NOT NULL,  -- the SOC or SIC code queried, verbatim
    dimension_label        TEXT NOT NULL,  -- the standard's own title, pinned in the module
    geography_code         TEXT NOT NULL,  -- 'K02000001' (UK) | 'E92000001' (England)
    geography_label        TEXT NOT NULL,  -- pinned in the module
    time                   TEXT NOT NULL,  -- the tax year label as the API serves it ("2023")
    value                  REAL,           -- the observation as a number; NULL where it is not one
    value_text             TEXT,           -- the observation exactly as the API served it
    unit_of_measure        TEXT,           -- the response's own unit statement
    source_url             TEXT NOT NULL,
    retrieved_at           TEXT NOT NULL,
    http_status            INTEGER NOT NULL,
    source_system          TEXT NOT NULL,
    payload_sha256         TEXT NOT NULL,
    PRIMARY KEY (dataset_id, edition, version, hoursandearnings,
                 dimension_kind, dimension_code, geography_code, time)
);

CREATE INDEX IF NOT EXISTS idx_ons_ashe_code_time
    ON ons_ashe_observations (dimension_kind, dimension_code, time);
