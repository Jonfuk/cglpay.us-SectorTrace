-- Module 1: procurement notices (Find a Tender + Contracts Finder OCDS).
--
-- One row per (notice_id, supplier_id): most notices have zero or one
-- supplier, but a multi-lot notice can award to several suppliers, so
-- supplier_id (default '' when no award/supplier exists yet, e.g. a
-- planning or tender-stage notice) is part of the natural key rather than
-- notice_id alone.
CREATE TABLE IF NOT EXISTS contracts (
    notice_id                TEXT NOT NULL,
    supplier_id                TEXT NOT NULL DEFAULT '',
    ocid                          TEXT NOT NULL,
    notice_type                    TEXT,          -- OCDS release tag(s), comma-joined e.g. 'award,contract'
    buyer_name                       TEXT,
    buyer_ons_code                     TEXT,
    supplier_name_raw                    TEXT,
    supplier_ppon                          TEXT,
    title                                    TEXT,
    description                               TEXT,
    cpv_codes                                   TEXT, -- comma-joined CPV codes found anywhere in the release
    value_core                                    REAL, -- net amount (award/contract value if present, else tender estimate)
    value_max                                       REAL, -- gross/VAT-inclusive amount, when distinct from value_core
    currency                                          TEXT,
    date_published                                      TEXT,
    date_start                                            TEXT, -- contract period start, if awarded
    date_end                                                TEXT, -- contract period end, if awarded
    extension_terms_text                                      TEXT,
    procedure_type                                              TEXT, -- procurementMethod + procurementMethodDetails
    psr_basis                                                     INTEGER NOT NULL DEFAULT 0, -- legalBasis matches Provider Selection Regime SI 2023/1348
    psr_direct_award_option                                          TEXT, -- 'DA1'/'DA2'/'DA3' only when explicitly stated in text; never inferred
    source_url                                                         TEXT NOT NULL,
    retrieved_at                                                         TEXT NOT NULL,
    http_status                                                            INTEGER NOT NULL,
    source_system                                                            TEXT NOT NULL,
    payload_sha256                                                             TEXT NOT NULL,
    PRIMARY KEY (notice_id, supplier_id)
);

CREATE INDEX IF NOT EXISTS idx_contracts_ocid ON contracts (ocid);
CREATE INDEX IF NOT EXISTS idx_contracts_buyer_ons ON contracts (buyer_ons_code);
CREATE INDEX IF NOT EXISTS idx_contracts_supplier_name ON contracts (supplier_name_raw);

-- Deterministic supplier name-variant -> canonical key mapping. Seeded from
-- pipeline/keywords.py's SUPPLIER_NAME_VARIANTS on every run; extend that
-- file (not this table) to add variants — never fuzzy-match here.
CREATE TABLE IF NOT EXISTS supplier_aliases (
    alias_raw           TEXT PRIMARY KEY,
    supplier_key           TEXT NOT NULL,
    canonical_name            TEXT NOT NULL
);
