export type PayRow = Record<string, unknown>
export interface PayColumn { key: string; label: string; numeric?: boolean; link?: boolean }
export interface PayLens {
  key: string; group: string; array: string; question: string; title: string; description: string
  provider: boolean; years?: boolean; role?: boolean; unit?: boolean; caveats: string[]
  identity: string[]; columns: PayColumn[]
}
const columns = (items: Array<[string, string, boolean?]>): PayColumn[] => items.map(([key, label, numeric]) => ({ key, label, numeric }))
// These are the existing public source groups and array fields, not new API
// enum values. Sub-lenses keep unlike arrays in the same API group separate.
export const payLenses: PayLens[] = [
  { key: 'charity', group: 'indicative_wage', array: 'charity_wage_series', question: 'What do charity accounts report about wages?', title: 'Charity wage observations', provider: true, years: true,
    description: 'These account-derived observations use wages and salaries across all grades and the published average employee denominator. A per-head observation is not a salary or pay scale. The response does not supply the underlying account URL, retrieval date or hash.', caveats: ['indicative_wage_note'], identity: ['charity_number', 'financial_year_end', 'provider_key'],
    columns: columns([['canonical_name', 'Provider'], ['charity_number', 'Charity number'], ['financial_year_end', 'Financial year end'], ['wages_and_salaries', 'Wages and salaries', true], ['average_employees', 'Average employees', true], ['average_employees_fte', 'Average FTE', true], ['employees_basis', 'Employee basis'], ['indicative_wage_per_head', 'Indicative wage per head', true], ['indicative_wage_per_fte', 'Indicative wage per FTE', true]]) },
  { key: 'adverts', group: 'advertised_roles', array: 'nhs_job_adverts', question: 'What pay do published job adverts offer?', title: 'Advertised roles', provider: true, role: true, unit: true,
    description: 'Adverts show offers to new starters on a date. They do not establish what existing staff are paid. Hourly and annual amounts stay in their original periods. No annualisation or comparison with a statutory floor is calculated.', caveats: ['nhs_jobs_floor_note'], identity: ['job_reference', 'provider_key', 'source_url'],
    columns: columns([['job_title', 'Advertised role'], ['canonical_name', 'Matched provider'], ['job_reference', 'Job reference'], ['salary_raw', 'Published salary'], ['salary_min', 'Published minimum', true], ['salary_max', 'Published maximum', true], ['salary_period', 'Source pay period'], ['salary_basis', 'Salary basis'], ['posted_date', 'Posted'], ['closing_date', 'Closing date']]) },
  { key: 'published', group: 'published_statutory', array: 'provider_published_pay', question: 'What has a provider published about pay?', title: 'Provider-published pay', provider: true, role: true, unit: true,
    description: 'These passages come from provider-owned pages. A published band is an offer or statement from that page, not evidence of everyone’s pay. Missing pages and pages without figures do not establish that no pay information exists.', caveats: ['provider_published_pay_note'], identity: ['provider_key', 'page_url', 'section', 'mention_text', 'salary_raw'],
    columns: columns([['canonical_name', 'Provider'], ['section', 'Page section'], ['mention_text', 'Published passage'], ['salary_raw', 'Published salary'], ['salary_period', 'Source pay period'], ['salary_basis', 'Salary basis']]) },
  { key: 'statutory', group: 'published_statutory', array: 'statutory_pay_rates', question: 'Which statutory hourly rates are held?', title: 'Statutory pay rates', provider: false, role: true,
    description: 'These are published statutory hourly rates for the stated bands and effective dates. All returned periods and age bands remain available. The first returned period is not automatically labelled current.', caveats: ['statutory_pay_rates_note'], identity: ['period_label', 'effective_from', 'band_label', 'band_role', 'source_url'],
    columns: columns([['period_label', 'Published period'], ['effective_from', 'Effective from'], ['band_label', 'Band'], ['band_role', 'Band role'], ['value_text', 'Published hourly value'], ['amount', 'Hourly amount', true]]) },
  { key: 'living-wage', group: 'published_statutory', array: 'living_wage_accreditations', question: 'Which employer names matched the Living Wage directory?', title: 'Living Wage name checks', provider: true,
    description: 'A failed name match is not proof that an employer is unaccredited. Read the searched variant, matched employer identity and extent of the directory check together.', caveats: ['living_wage_note'], identity: ['provider_key', 'searched_variant', 'employer_node_id', 'source_url'],
    columns: columns([['canonical_name', 'Provider'], ['searched_variant', 'Searched name'], ['accredited', 'Name-check result'], ['employer_name', 'Matched employer name'], ['employer_node_id', 'Directory employer ID'], ['match_basis', 'Match basis'], ['pages_checked', 'Pages checked', true], ['employers_total', 'Directory employers reported', true]]) },
  { key: 'gender-gap', group: 'published_statutory', array: 'gender_pay_gap_reports', question: 'What gender pay gaps did employers report?', title: 'Gender pay gap filings', provider: true,
    description: 'Filings belong to the named reporting employer and employer ID. Provider matches do not merge distinct employers. The reported percentages remain separate from wage observations and advertised salaries.', caveats: ['gender_pay_gap_note'], identity: ['employer_id', 'reporting_year', 'provider_key', 'source_url'],
    columns: columns([['employer_name', 'Reporting employer'], ['employer_id', 'Employer ID'], ['canonical_name', 'Matched provider'], ['reporting_year_label', 'Reporting year label'], ['reporting_year', 'Reporting year'], ['diff_mean_hourly_percent', 'Mean hourly gap (%)', true], ['diff_median_hourly_percent', 'Median hourly gap (%)', true], ['diff_mean_bonus_percent', 'Mean bonus gap (%)', true], ['diff_median_bonus_percent', 'Median bonus gap (%)', true]]) },
  { key: 'census', group: 'workforce_census', array: 'workforce_census', question: 'What does the national workforce census report?', title: 'National workforce census', provider: false, role: true,
    description: 'Census observations describe the participating national sample. Participation differs between rounds, so years are not differenced. Verified means checked transcription, not comparability, completeness or provider attribution.', caveats: ['census_comparability_note'], identity: ['census_year', 'metric', 'workforce_segment', 'source_url', 'source_page'],
    columns: columns([['census_year', 'Census year'], ['metric', 'Metric'], ['workforce_segment', 'Workforce segment'], ['value', 'Published value'], ['unit', 'Source unit'], ['verified', 'Transcription status'], ['source_page', 'Source page']]) },
  { key: 'ashe', group: 'external_comparators', array: 'ons_ashe_observations', question: 'What earnings context does ONS ASHE provide?', title: 'ONS ASHE observations', provider: false, role: true, unit: true,
    description: 'ASHE observations retain their dataset, edition, dimension, geography, period and unit. They describe the published labour-market population and are not measures of a tracked provider’s pay.', caveats: ['ashe_note'], identity: ['dataset_id', 'edition', 'version', 'dimension_kind', 'dimension_code', 'geography_code', 'time', 'unit_of_measure'],
    columns: columns([['dataset_title', 'Dataset'], ['dimension_label', 'Published dimension'], ['geography_label', 'Published geography'], ['time', 'Published period'], ['value_text', 'Published value text'], ['value', 'Value', true], ['unit_of_measure', 'Source unit'], ['edition', 'Edition'], ['version', 'Version']]) },
  { key: 'skills-for-care', group: 'external_comparators', array: 'skills_for_care_estimates', question: 'What national context does Skills for Care provide?', title: 'Skills for Care estimates', provider: false, role: true, unit: true,
    description: 'This endpoint returns up to 500 national adult social care observations. Sector, service, role and source year remain separate. These estimates are not provider observations. A unit filter classifies rows and does not convert their published values.', caveats: ['skills_for_care_note'], identity: ['file_url', 'year', 'area_code', 'sector', 'service', 'job_role_group', 'job_role'],
    columns: columns([['year', 'Source year'], ['area', 'Area'], ['area_level', 'Area level'], ['sector', 'Sector'], ['service', 'Service'], ['job_role_group', 'Role group'], ['job_role', 'Role'], ['fte_annual_pay', 'Published FTE annual pay', true], ['hourly_pay', 'Published hourly pay', true], ['turnover_rate', 'Published turnover rate', true], ['vacancy_rate', 'Published vacancy rate', true]]) },
]
export interface PayPayload extends Record<string, unknown> {
  source_groups?: Array<{ key: string; label: string; count: number; arrays?: string[] }>
  filters_available?: { roles?: string[]; pay_units?: string[]; sources?: Array<{ key: string; label: string }> }
  caveats?: Record<string, string | null>
}
export function payRows(payload: PayPayload | null, array: string): PayRow[] | null {
  const value = payload?.[array]
  return Array.isArray(value) ? value as PayRow[] : null
}
export function payRecordKey(lens: PayLens, row: PayRow): string { return JSON.stringify(lens.identity.map(key => row[key] ?? null)) }
export function payCell(column: PayColumn, row: PayRow): string {
  const value = row[column.key]
  // Only the census exposes this documented zero-based PDF page index.
  if (column.key === 'source_page' && typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) return String(value + 1)
  if (column.key === 'accredited') return value === true || value === 1 ? 'Name matched in directory' : value === false || value === 0 ? 'No name match in this check' : 'Result not supplied'
  if (column.key === 'verified') return value === true || value === 1 ? 'Transcription verified' : value === false || value === 0 ? 'Unverified transcription' : 'Verification status not supplied'
  if (value == null || value === '') return 'Not supplied'
  return typeof value === 'number' && column.numeric ? value.toLocaleString('en-GB', { maximumSignificantDigits: 21 }) : String(value)
}
export function payQuery(lens: PayLens | undefined, query: Record<string, string | undefined>) {
  if (!lens) return { source: query.source || undefined, provider_key: query.provider_key || undefined }
  return { source: lens.group, provider_key: lens.provider ? query.provider_key || undefined : undefined, year_from: lens.years ? query.year_from || undefined : undefined, year_to: lens.years ? query.year_to || undefined : undefined, role: lens.role ? query.role || undefined : undefined, pay_unit: lens.unit ? query.pay_unit || undefined : undefined }
}
