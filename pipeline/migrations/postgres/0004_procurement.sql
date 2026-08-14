-- Module 1: procurement notices (Find a Tender + Contracts Finder OCDS).
--
-- One row per (notice_id, supplier_id): most notices have zero or one
-- supplier, but a multi-lot notice can award to several suppliers, so
-- supplier_id (default '' when no award/supplier exists yet, e.g. a
-- planning or tender-stage notice) is part of the natural key rather than
-- notice_id alone.
--
-- PostgreSQL dialect of ../0004_procurement.sql. See README.md in this directory for
-- the conversion rules.
--
CREATE TABLE IF NOT EXISTS contracts (
    notice_id                text NOT NULL,
    supplier_id                text NOT NULL DEFAULT '',
    ocid                          text NOT NULL,
    notice_type                    text,          -- OCDS release tag(s), comma-joined e.g. 'award,contract'
    buyer_name                       text,
    buyer_ons_code                     text,
    supplier_name_raw                    text,
    supplier_ppon                          text,
    title                                    text,
    description                               text,
    cpv_codes                                   text, -- comma-joined CPV codes found anywhere in the release
    value_core                                    double precision, -- net amount (award/contract value if present, else tender estimate)
    value_max                                       double precision, -- gross/VAT-inclusive amount, when distinct from value_core
    currency                                          text,
    date_published                                      text,
    date_start                                            text, -- contract period start, if awarded
    date_end                                                text, -- contract period end, if awarded
    extension_terms_text                                      text,
    procedure_type                                              text, -- procurementMethod + procurementMethodDetails
    psr_basis                                                     bigint NOT NULL DEFAULT 0, -- legalBasis matches Provider Selection Regime SI 2023/1348
    psr_direct_award_option                                          text, -- 'DA1'/'DA2'/'DA3' only when explicitly stated in text; never inferred
    source_url                                                         text NOT NULL,
    retrieved_at                                                         text NOT NULL,
    http_status                                                            bigint NOT NULL,
    source_system                                                            text NOT NULL,
    payload_sha256                                                             text NOT NULL,
    PRIMARY KEY (notice_id, supplier_id)
);

CREATE INDEX IF NOT EXISTS idx_contracts_ocid ON contracts (ocid);
CREATE INDEX IF NOT EXISTS idx_contracts_buyer_ons ON contracts (buyer_ons_code);
CREATE INDEX IF NOT EXISTS idx_contracts_supplier_name ON contracts (supplier_name_raw);

-- Deterministic supplier name-variant -> canonical key mapping. Seeded from
-- pipeline/keywords.py's SUPPLIER_NAME_VARIANTS on every run; extend that
-- file (not this table) to add variants — never fuzzy-match here.
CREATE TABLE IF NOT EXISTS supplier_aliases (
    alias_raw           text PRIMARY KEY,
    supplier_key           text NOT NULL,
    canonical_name            text NOT NULL
);
