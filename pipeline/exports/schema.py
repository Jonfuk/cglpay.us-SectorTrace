"""Export schema: the ten Google Sheets tabs, defined in one place.

The brief asked for the original nine-tab structure; this schema was designed
rather than supplied, on instruction. Two decisions worth stating:

1. Tabs carry the human-readable evidence — things a campaigner or organiser
   reads a row at a time. The NDTMS and Fingertips treatment statistics
   (~40,000 rows between them) are deliberately NOT here: they are map and
   chart data and go to the GeoJSON and ECharts targets instead. A tab
   nobody can scroll is not evidence anyone can check.

2. No tab mixes evidence layers. Each maps to one source system, or to a
   set of tables from one source, so a reader always knows what collection
   method produced the row in front of them (constraint 2).

Every column listed here must exist in the warehouse and must not be a
restricted_ or personal-data column — tests assert both.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TabSpec:
    name: str
    description: str
    sql: str
    columns: list[str]
    # Caveats rendered into the tab header and into the ECharts meta block.
    caveats: list[str] = field(default_factory=list)


TABS: list[TabSpec] = [
    TabSpec(
        name="01_Authorities",
        description="Every English local authority with public health responsibility, and its successors.",
        columns=["ons_code", "name", "type", "region", "parent_code",
                  "active_from", "active_to", "successor_codes"],
        caveats=[
            "Authorities that were reorganised keep their own row with active_to set; "
            "successors are listed rather than the predecessor being collapsed into them.",
        ],
        sql="""
            SELECT a.ons_code, a.name, a.type, a.region, a.parent_code,
                   a.active_from, a.active_to,
                   (SELECT GROUP_CONCAT(s.successor_code, ', ')
                      FROM authority_successors s
                     WHERE s.predecessor_code = a.ons_code) AS successor_codes
              FROM authorities a
             ORDER BY a.name
        """,
    ),
    TabSpec(
        name="02_Public_Health_Grant",
        description="DHSC public health grant allocations per authority per year, including the drug and alcohol ring-fence.",
        columns=["ons_code", "authority_name", "financial_year", "grant_type",
                  "allocation_status", "unit", "amount", "source_document"],
        caveats=[
            "Indicative allocations for future years are marked in allocation_status and are not confirmed funding.",
            "grant_type is a normalised form of the column header in DHSC's own spreadsheet, which changes between years.",
        ],
        sql="""
            SELECT g.ons_code, a.name AS authority_name, g.financial_year, g.grant_type,
                   g.allocation_status, g.unit, g.amount, g.source_document
              FROM public_health_grants g
              LEFT JOIN authorities a ON a.ons_code = g.ons_code
             ORDER BY a.name, g.financial_year, g.grant_type
        """,
    ),
    TabSpec(
        name="03_Contracts",
        description="Procurement notices for substance misuse services, from Find a Tender and Contracts Finder.",
        columns=["notice_id", "ocid", "notice_type", "buyer_name", "buyer_ons_code",
                  "supplier_name_raw", "supplier_ppon", "title", "cpv_codes",
                  "value_core", "value_max", "currency", "date_published",
                  "date_start", "date_end", "procedure_type", "psr_basis",
                  "psr_direct_award_option", "source_system", "source_url"],
        caveats=[
            "Contract values are estimates at notice stage and may differ from actual spend.",
            "Coverage is incomplete before 24 February 2025 for below-threshold contracts, which were published on Contracts Finder rather than Find a Tender.",
            "buyer_ons_code is NULL where the free-text buyer name could not be matched deterministically; those names are in review_queue, and since Phase 18 they are also captured, name-only, in sector_universe as funders.",
        ],
        sql="""
            SELECT notice_id, ocid, notice_type, buyer_name, buyer_ons_code,
                   supplier_name_raw, supplier_ppon, title, cpv_codes,
                   value_core, value_max, currency, date_published,
                   date_start, date_end, procedure_type, psr_basis,
                   psr_direct_award_option, source_system, source_url
              FROM contracts
             -- NULLS LAST is stated, not left to the engine. SQLite sorts
             -- NULLs last in a DESC order and PostgreSQL sorts them first, so
             -- an undated notice would move from the bottom of this tab to the
             -- top purely by changing backend. These tabs are the artefact
             -- somebody defends in a room a year later; the row order is part
             -- of what they are defending, and it does not get to depend on
             -- which database answered. Same reasoning at every ORDER BY in
             -- this file over a column that can be NULL.
             ORDER BY date_published DESC NULLS LAST
        """,
    ),
    TabSpec(
        name="04_Providers",
        description="Provider entities and the legal entities that make them up, with name-free officer churn.",
        columns=["provider_key", "canonical_name", "is_target", "company_number",
                  "company_name", "company_status", "company_type", "date_of_creation",
                  "match_basis", "officers_total", "officers_active", "officers_resigned",
                  "previous_names"],
        caveats=[
            "match_basis 'name_only_unconfirmed' means a company matched a provider name exactly but has NOT been confirmed as the same legal entity — a shared name is not a shared identity.",
            "Officer counts are aggregates; individual officers are personal data and are not exported.",
            "previous_names come from Companies House and are authoritative former names, not aliases inferred by this pipeline.",
        ],
        sql="""
            SELECT p.provider_key, p.canonical_name, p.is_target,
                   c.company_number, c.company_name, c.company_status, c.company_type,
                   c.date_of_creation, c.match_basis,
                   v.officers_total, v.officers_active, v.officers_resigned,
                   (SELECT GROUP_CONCAT(n.previous_name, ' | ')
                      FROM company_previous_names n
                     WHERE n.company_number = c.company_number) AS previous_names
              FROM providers p
              LEFT JOIN companies c ON c.provider_key = p.provider_key
              LEFT JOIN v_company_officer_changes v ON v.company_number = c.company_number
             ORDER BY p.is_target DESC, p.canonical_name
        """,
    ),
    TabSpec(
        name="05_Charity_Finance",
        description="Charity income and expenditure from the register, with staff costs and employee numbers from filed accounts.",
        columns=["charity_number", "provider_key", "financial_year_end",
                  "total_income", "total_expenditure", "income_from_govt_contracts",
                  "wages_and_salaries", "staff_costs_total", "agency_and_third_party",
                  "average_employees", "employees_basis", "average_employees_fte",
                  "indicative_wage_per_head", "indicative_wage_per_fte",
                  "denominator_basis_note", "numerator_scope_note"],
        caveats=[
            "indicative_wage_per_head is NOT an average salary. The denominator is a headcount average that counts part-time staff as whole people, so it reads lower than actual pay.",
            "The numerator is total wages for all grades including senior staff, before employer NI and pension costs.",
            "Register figures and accounts figures come from different documents; both are shown per year but neither was derived from the other.",
        ],
        sql="""
            SELECT f.charity_number,
                   (SELECT i.provider_key FROM provider_identifiers i
                     WHERE i.scheme = 'charity_number' AND i.identifier = f.charity_number
                     LIMIT 1) AS provider_key,
                   f.financial_year_end, f.total_income, f.total_expenditure,
                   f.income_from_govt_contracts,
                   e.wages_and_salaries, e.staff_costs_total, e.agency_and_third_party,
                   e.average_employees, e.employees_basis, e.average_employees_fte,
                   w.indicative_wage_per_head, w.indicative_wage_per_fte,
                   w.denominator_basis_note, w.numerator_scope_note
              FROM charity_financials f
              LEFT JOIN charity_accounts_extracts e
                     ON e.charity_number = f.charity_number
                    AND e.financial_year_end = f.financial_year_end
              LEFT JOIN v_wage_per_employee w
                     ON w.charity_number = f.charity_number
                    AND w.financial_year_end = f.financial_year_end
             ORDER BY f.charity_number, f.financial_year_end
        """,
    ),
    TabSpec(
        name="06_CQC_Locations",
        description="CQC-registered locations for target providers, with ratings and inspection dates.",
        columns=["location_id", "provider_key", "location_name", "postal_code",
                  "latitude", "longitude", "local_authority_raw", "ons_code",
                  "region", "registration_status", "last_inspection_date",
                  "overall_rating", "service_types"],
        caveats=[
            "CQC registration covers only some service types — residential detoxification, inpatient and certain prescribing services. Most community drug and alcohol provision is NOT CQC-registered, so this is a map of regulated locations and not a complete service map.",
            "Counting locations per authority does not measure service coverage.",
        ],
        sql="""
            SELECT l.location_id, l.provider_key, l.location_name, l.postal_code,
                   l.latitude, l.longitude, l.local_authority_raw,
                   l.local_authority_ons_code AS ons_code, l.region,
                   l.registration_status, l.last_inspection_date,
                   l.overall_rating, l.service_types
              FROM cqc_locations l
             -- location_name is nullable; ascending, SQLite puts NULLs first
             -- and PostgreSQL puts them last.
             ORDER BY l.provider_key, l.location_name NULLS FIRST
        """,
    ),
    TabSpec(
        name="07_Tribunal_Cases",
        description="Employment tribunal judgments naming target providers as respondent, pseudonymised.",
        columns=["claim_ref", "case_number", "provider_key", "provider_match_basis",
                  "respondent_normalised", "office_prefix", "case_year", "region",
                  "hearing_venue_raw", "decision_date", "jurisdiction_codes",
                  "outcome", "outcome_confidence", "document_count"],
        caveats=[
            "This database captures only cases reaching a published judgment. Settled, withdrawn and struck-out claims — the majority of all claims — are invisible here. Do NOT compute a claims-per-employee rate or any normalised metric from these counts.",
            "outcome is derived from judgment text, never from structured metadata, and is always low confidence.",
            "region is NULL because no verified case-number-prefix to region mapping has been established; hearing_venue_raw is the raw text from the judgment.",
            "provider_match_basis 'component' means the provider was named alongside co-respondents.",
        ],
        sql="""
            SELECT claim_ref, case_number, provider_key, provider_match_basis,
                   respondent_normalised, office_prefix, case_year, region,
                   hearing_venue_raw, decision_date, jurisdiction_codes,
                   outcome, outcome_confidence, document_count
              FROM tribunal_cases
             ORDER BY decision_date DESC NULLS LAST
        """,
    ),
    TabSpec(
        name="08_PFD_Reports",
        description="Prevention of Future Deaths reports in substance misuse and related categories, with workforce concern flags.",
        columns=["report_ref", "report_date", "coroner_name", "coroner_area",
                  "categories", "report_url", "concern_terms", "provider_recipients",
                  "provider_mentions", "matters_of_concern"],
        caveats=[
            "The deceased is never named in this export; reports are keyed on the coroner's own reference and names are redacted from matters_of_concern.",
            "provider_recipients (the coroner addressed the report to them) and provider_mentions (named in the report but not addressed) are materially different facts and must not be added together.",
            "Roughly two thirds of reports publish only a metadata stub online, with the report itself as a PDF that is not linked in the published data — those have no matters_of_concern here.",
            "Concern terms indicate a word appears. They are a finding aid, not a characterisation of what the coroner found.",
        ],
        sql="""
            SELECT r.report_ref, r.report_date, r.coroner_name, r.coroner_area,
                   r.categories, r.report_url,
                   (SELECT GROUP_CONCAT(t.term || ' (' || t.occurrences || ')', ', ')
                      FROM pfd_concern_terms t WHERE t.report_ref = r.report_ref) AS concern_terms,
                   (SELECT GROUP_CONCAT(m.provider_key, ', ') FROM pfd_provider_mentions m
                     WHERE m.report_ref = r.report_ref AND m.mention_type = 'recipient') AS provider_recipients,
                   (SELECT GROUP_CONCAT(m.provider_key, ', ') FROM pfd_provider_mentions m
                     WHERE m.report_ref = r.report_ref AND m.mention_type = 'body_text') AS provider_mentions,
                   r.matters_of_concern
              FROM pfd_reports r
             ORDER BY r.report_date DESC NULLS LAST
        """,
    ),
    TabSpec(
        name="09_Workforce_Census",
        description="National drug and alcohol workforce census metrics, with the source line each was read from.",
        columns=["census_year", "metric", "workforce_segment", "value", "unit",
                  "verified", "source_page", "raw_text"],
        caveats=[
            "Provider participation varies between census rounds, so years are NOT like-for-like and must not be differenced without reading each year's participation note.",
            "The census publishes sector aggregates only. No figure here can be attributed to a named provider.",
            "verified = 0 means no human has yet checked the parsed value against the source line. Filter on it before publishing anything.",
            "workforce_segment 'ambiguous' means the source line named more than one segment and attribution was not guessed.",
        ],
        sql="""
            SELECT census_year, metric, workforce_segment, value, unit,
                   verified, source_page, raw_text
              FROM workforce_census_metrics
             ORDER BY census_year DESC, metric, workforce_segment
        """,
    ),
    TabSpec(
        name="10_Sector_Universe",
        description="The sector population as reconstructed from what the pipeline already collects (Phase 18, F1): the tracked providers, the companies, charities and CQC registrations collected about them, every distinct awardee in the contract notices, and every buyer no authority could be matched to.",
        columns=["entity_key", "canonical_name", "entity_type", "company_number",
                  "charity_number", "cqc_provider_id", "ppon", "provider_key",
                  "match_basis", "first_seen", "last_seen", "notices_count",
                  "source_system"],
        caveats=[
            "The universe is a capture of who shows up in the corpus, never a complete list of the sector. Awardees enter through notices matched by CPV prefix or keyword, so care, support and other companies that won one in-scope lot appear here; the tracked handful of CQC providers is a floor, not a census.",
            "match_basis 'name_only_unconfirmed' rows were captured from a name alone. Sharing a name is not sharing an identity, and these rows are never linked to a provider; treat them as candidates.",
            "match_basis 'ppon' rows are identified only by the supplier's GB-PPON registration id, self-declared by the buyer's platform. It identifies the registration, not the legal entity.",
            "provider_key is set only through an identifier a source published (provider_identifiers, or a company row m04 seeded) — never on a name.",
            "A funder is a buyer name that matched no authority. Funders include NHS bodies, police and other public bodies, suppliers that also commission, and names that are simply unidentifiable.",
            "notices_count counts distinct notices naming the organisation, by ppon or exact normalised name. It is one layer (contracts) and may be used as a share of that layer; it is not a size measure of the organisation.",
        ],
        sql="""
            SELECT entity_key, canonical_name, entity_type, company_number,
                   charity_number, cqc_provider_id, ppon, provider_key,
                   match_basis, first_seen, last_seen, notices_count,
                   source_system
              FROM sector_universe
             ORDER BY COALESCE(notices_count, 0) DESC, canonical_name
        """,
    ),
]


def tab_by_name(name: str) -> TabSpec | None:
    return next((t for t in TABS if t.name == name), None)
