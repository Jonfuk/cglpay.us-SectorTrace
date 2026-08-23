-- One row per (notice_id, source_system): what a *specific* m01 channel
-- itself observed for a notice, kept alongside (never instead of) the
-- deduplicated `contracts` table.
--
-- Until now m01's channels never overlapped enough to matter: FTS/CF live
-- cover everything from WINDOW_START, the CSV archive covers everything
-- before it, so `contracts`'s (notice_id, supplier_id) upsert rarely saw the
-- same notice twice and "last write wins silently" was never really tested.
-- --kag changes that -- the Kaggle archive spans 2014-2025, i.e. the whole of
-- both other channels' windows -- so a fourth channel that also wrote
-- `contracts` would silently overwrite a live-API-sourced value with a
-- third-party re-host's transcription of it on every overlapping notice.
--
-- --kag therefore never writes to `contracts` (see the module docstring).
-- Every channel -- including the three that do write `contracts` -- writes
-- its own notice-level summary here instead, so the three "supply routes"
-- can be compared directly: which notices only one channel saw, and where
-- two channels saw the same notice but disagree. `pipeline.modules.
-- m01_procurement._check_kaggle_against_other_channels` reads this table to
-- raise `kaggle_coverage_gap` / `kaggle_cross_channel_mismatch` review items;
-- it is also there to be queried directly for anything that check does not
-- already flag.
--
-- Notice-level, not supplier-level, because the Kaggle CSV collapses a
-- multi-award notice to its first award only (see the module docstring) --
-- comparing at supplier grain would flag that collapsing as a "mismatch" on
-- every multi-supplier notice, which is a known channel limitation, not a
-- finding.
CREATE TABLE IF NOT EXISTS procurement_channel_sightings (
    notice_id                TEXT NOT NULL,
    source_system              TEXT NOT NULL,
    ocid                          TEXT,
    buyer_name                     TEXT,
    title                             TEXT,
    cpv_codes                          TEXT,
    tender_value_amount                  REAL,
    tender_value_currency                  TEXT,
    total_award_value_amount                 REAL, -- sum of this channel's own per-supplier award values; NULL if none
    supplier_names                             TEXT, -- pipe-joined, as this channel saw them
    date_published                               TEXT,
    source_url                                     TEXT NOT NULL,
    retrieved_at                                     TEXT NOT NULL,
    http_status                                        INTEGER NOT NULL,
    payload_sha256                                       TEXT NOT NULL,
    PRIMARY KEY (notice_id, source_system)
);

CREATE INDEX IF NOT EXISTS idx_procurement_sightings_notice ON procurement_channel_sightings (notice_id);
