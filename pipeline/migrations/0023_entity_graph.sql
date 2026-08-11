-- Entity graph: views over evidence already collected.
--
-- No new source, no new fetching, no new politeness surface. Everything here
-- is a join across tables the pipeline already holds — company officers from
-- m04, charity identifiers from m03, contract suppliers from m01, CQC
-- registrations from m05, tribunal respondents from m02 and authorities from
-- m00. That is the whole argument for building it: the data is on disk and
-- unconnected, and connecting it costs nothing anyone has to be polite about.
--
-- Views rather than tables, deliberately. A materialised graph would be a
-- fifth copy of facts that already have provenance in their own rows, and it
-- would go stale the moment any module ran. A view cannot disagree with its
-- sources.
--
-- PERSONAL DATA. Every view whose rows can name a person carries the
-- restricted_ prefix, which pipeline/exports guards on. Officers are named
-- individuals: a graph that links a person to a company, to a charity, to a
-- contract and to a local authority is a personal-data product however
-- public each individual fact is. The unrestricted views below are
-- organisation-to-organisation only.

-- --- edges between organisations -------------------------------------------
--
-- One row per (source entity, relationship, target entity), with the evidence
-- that supports it. `basis` matters as much as the edge: an edge resting on
-- match_basis = 'name_only_unconfirmed' is a lead, not a fact, and must not
-- be read as one. See docs/CAVEATS.md on Module 4 — the "FORWARD TRUST
-- LIMITED" that matches by name is a dissolved Bradford & Bingley subsidiary.
CREATE VIEW IF NOT EXISTS v_entity_edges AS
    -- provider -> company, from Companies House
    SELECT 'provider'          AS source_type,
           c.provider_key      AS source_id,
           'registered_as'     AS relationship,
           'company'           AS target_type,
           c.company_number    AS target_id,
           c.company_name      AS target_label,
           c.match_basis       AS basis,
           c.source_url        AS source_url,
           c.retrieved_at      AS retrieved_at
      FROM companies c
     WHERE c.provider_key IS NOT NULL

    UNION ALL
    -- provider -> charity / company number, from the identifier register
    SELECT 'provider', i.provider_key, 'identified_by', i.scheme, i.identifier,
           i.identifier, i.discovered_by, NULL, NULL
      FROM provider_identifiers i

    UNION ALL
    -- provider -> CQC provider registration
    SELECT 'provider', p.provider_key, 'cqc_registered_as', 'cqc_provider',
           p.provider_id, p.provider_name, p.match_basis, p.source_url, p.retrieved_at
      FROM cqc_providers p
     WHERE p.provider_key IS NOT NULL

    UNION ALL
    -- authority -> supplier, from awarded contract notices. The strongest
    -- commissioner relationship in the warehouse, and the one a pay campaign
    -- actually needs: who pays whom, for what, and how much.
    SELECT 'authority', ct.buyer_ons_code, 'awarded_contract_to', 'supplier',
           COALESCE(sa.supplier_key, ct.supplier_name_raw), ct.supplier_name_raw,
           CASE WHEN sa.supplier_key IS NOT NULL THEN 'alias_matched'
                ELSE 'supplier_name_unmatched' END,
           ct.source_url, ct.retrieved_at
      FROM contracts ct
      LEFT JOIN supplier_aliases sa ON sa.alias_raw = ct.supplier_name_raw
     WHERE ct.buyer_ons_code IS NOT NULL
       AND ct.supplier_name_raw IS NOT NULL

    UNION ALL
    -- provider -> tribunal case. 'component' means the provider was named
    -- alongside co-respondents; the case is not solely about them.
    SELECT 'provider', t.provider_key, 'respondent_in', 'tribunal_case',
           t.case_number, t.claim_ref, t.provider_match_basis,
           t.source_url, t.retrieved_at
      FROM tribunal_cases t
     WHERE t.provider_key IS NOT NULL;

-- --- shared officers, which is where the hidden structure is ---------------
--
-- Two companies with a director in common. This is the edge that finds
-- provider groups nobody has announced, and it is also the edge most likely
-- to be wrong: officer_name is a string, and two different people share a
-- name more often than anyone expects. Restricted because it names them, and
-- 'basis' says plainly that the match is nominal.
CREATE VIEW IF NOT EXISTS restricted_v_shared_officers AS
    SELECT a.officer_name                         AS officer_name,
           a.company_number                       AS company_number_a,
           b.company_number                       AS company_number_b,
           ca.company_name                        AS company_name_a,
           cb.company_name                        AS company_name_b,
           ca.provider_key                        AS provider_key_a,
           cb.provider_key                        AS provider_key_b,
           'name_match_only'                      AS basis,
           -- The officers table carries no provenance columns of its own;
           -- it inherits the Companies House fetch that produced the company
           -- row, which is where the URL and timestamp live.
           ca.source_url                          AS source_url,
           ca.retrieved_at                        AS retrieved_at
      FROM restricted_company_officers a
      JOIN restricted_company_officers b
        ON a.officer_name = b.officer_name
       AND a.company_number < b.company_number
      LEFT JOIN companies ca ON ca.company_number = a.company_number
      LEFT JOIN companies cb ON cb.company_number = b.company_number
     WHERE a.officer_name IS NOT NULL
       AND TRIM(a.officer_name) <> '';

-- Officer appointments as graph edges. Restricted for the same reason.
CREATE VIEW IF NOT EXISTS restricted_v_officer_edges AS
    SELECT o.officer_name  AS source_id,
           'officer_of'    AS relationship,
           o.company_number AS target_id,
           c.company_name  AS target_label,
           c.provider_key  AS provider_key,
           o.officer_role  AS officer_role,
           o.appointed_on  AS appointed_on,
           o.resigned_on   AS resigned_on,
           c.source_url    AS source_url,
           c.retrieved_at  AS retrieved_at
      FROM restricted_company_officers o
      LEFT JOIN companies c ON c.company_number = o.company_number;

-- --- how much of the graph rests on a guess -------------------------------
--
-- The count that stops the graph being read as fact. Every edge carries a
-- basis, and this is the tally of how many rest on an unconfirmed name match
-- rather than on a confirmed identifier. Publish it beside any graph figure.
CREATE VIEW IF NOT EXISTS v_entity_edge_confidence AS
    SELECT relationship,
           basis,
           COUNT(*) AS edges
      FROM v_entity_edges
     GROUP BY relationship, basis;
