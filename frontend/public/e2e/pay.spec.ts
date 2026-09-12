import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const provider = { provider_key: 'example-recovery', canonical_name: 'Example Recovery' }
const source = { source_url: 'https://example.invalid/pay-source', retrieved_at: '2026-08-01T12:00:00Z', payload_sha256: 'e'.repeat(64) }
const groups = [
  { key: 'indicative_wage', label: 'Indicative wage', arrays: ['charity_wage_series'], count: 0 },
  { key: 'advertised_roles', label: 'Advertised roles', arrays: ['nhs_job_adverts', 'nhs_job_by_band', 'repeat_advertised_roles'], count: 0 },
  { key: 'published_statutory', label: 'Published and statutory', arrays: ['provider_published_pay', 'statutory_pay_rates', 'living_wage_accreditations', 'gender_pay_gap_reports'], count: 0 },
  { key: 'workforce_census', label: 'Workforce census', arrays: ['workforce_census'], count: 0 },
  { key: 'external_comparators', label: 'External comparators', arrays: ['ons_ashe_observations', 'skills_for_care_estimates'], count: 0 },
]
const response = (arrays: Record<string, unknown> = {}) => ({
  ...Object.fromEntries(groups.flatMap(group => group.arrays).map(key => [key, []])),
  source_groups: groups, filters_available: { roles: ['Recovery worker'], pay_units: ['hourly', 'annual', 'other'], sources: groups.map(({ key, label }) => ({ key, label })) },
  caveats: { nhs_jobs_floor_note: 'Synthetic adverts describe offers, not current staff pay.', census_comparability_note: 'Synthetic census rounds have different participating samples.' }, ...arrays,
})
const advert = (reference: string, additions: Record<string, unknown> = {}) => ({ ...provider, job_reference: reference, job_title: `Recovery worker ${reference}`, salary_raw: '£30,000 to £40,000 a year', salary_min: 30000, salary_max: 40000, salary_period: 'year', salary_basis: 'range', contract_type: 'Permanent', working_pattern: 'Part-time', posted_date: '2025-02-03', closing_date: '2025-03-03', advert_url: `https://example.invalid/advert/${reference}`, source_url: `https://example.invalid/source/${reference}`, retrieved_at: source.retrieved_at, provider_match_basis: 'exact', ...additions })

test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers: [provider] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture for this request' } })
    return route.continue()
  })
})
async function question(page: Page, title: string) {
  await page.getByRole('button', { name: 'All pay and workforce questions', exact: true }).click()
  await page.getByRole('button', { name: `Read ${title.toLowerCase()}`, exact: true }).click()
}

test('pay questions preserve national scope, statutory bands, employer identities and source fields', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  await page.route('**/api/v1/pay*', route => {
    requests.push(new URL(route.request().url()))
    return route.fulfill({ json: response({
      workforce_census: [{ census_year: 2023, metric: 'WTE', workforce_segment: 'ambiguous', value: 0, unit: 'WTE', verified: 1, source_page: 0, source_url: source.source_url, retrieved_at: source.retrieved_at }, { census_year: 2022, metric: 'Headcount', workforce_segment: 'National', value: '[suppressed]', unit: 'people', verified: 0, source_page: 4 }],
      statutory_pay_rates: [{ ...source, period_label: '2025/26', effective_from: '2025-04-01', band_label: 'Under 18', band_role: 'worker', amount: 7.55, value_text: '£7.55' }, { ...source, period_label: '2024/25', effective_from: '2024-04-01', band_label: 'Apprentice', band_role: 'apprentice', amount: 6.4, value_text: '£6.40' }],
      gender_pay_gap_reports: [{ ...provider, ...source, employer_name: 'Example Employer', employer_id: '100', reporting_year: 2025, reporting_year_label: '2025 to 2026', diff_mean_hourly_percent: 0, diff_median_hourly_percent: -2.5 }, { ...provider, ...source, employer_name: 'Example Employer', employer_id: '200', reporting_year: 2025, reporting_year_label: '2025 to 2026', diff_mean_hourly_percent: 12, diff_median_hourly_percent: null }],
      ons_ashe_observations: [{ ...source, dataset_id: 'ASHE', dataset_title: 'Synthetic earnings dataset', edition: '2025', version: '1', dimension_kind: 'occupation', dimension_code: 'example', dimension_label: 'Published occupation', geography_code: 'K02000001', geography_label: 'United Kingdom', time: '2025', value: null, value_text: '[suppressed]', unit_of_measure: 'Weekly earnings (£)' }],
      living_wage_accreditations: [{ ...provider, ...source, searched_variant: 'Example Recovery', accredited: 0, employer_name: null, employer_node_id: null, match_basis: null, pages_checked: 2, employers_total: 100 }],
    }) })
  })
  await page.goto('/#/pay?provider_key=example-recovery&year_from=2020&year_to=2025')
  await expect(page.locator('.st-pay-questions > li')).toHaveCount(9)
  await page.getByRole('button', { name: 'Read national workforce census', exact: true }).click()
  await expect(page.getByRole('cell', { name: '[suppressed]', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '0', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '1', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ source: 'workforce_census' })
  await expect(page.getByText('The provider selection example-recovery is retained', { exact: false })).toBeVisible()
  await expect(page.getByText('Account-year bounds are retained', { exact: false })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Transcription verified', exact: true })).toBeVisible()
  await question(page, 'Statutory pay rates')
  await expect(page.getByRole('cell', { name: 'Under 18', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Apprentice', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ source: 'published_statutory' })
  await question(page, 'Gender pay gap filings')
  const buttons = page.getByRole('button', { name: /^Inspect Example Employer, displayed row/ })
  await expect(buttons).toHaveCount(2)
  await buttons.nth(1).click()
  let inspector = page.getByRole('complementary', { name: 'Example Employer', exact: true })
  await expect(inspector.getByText('200', { exact: true })).toBeVisible()
  const selection = page.url()
  await page.reload()
  inspector = page.getByRole('complementary', { name: 'Example Employer', exact: true })
  await expect(inspector.getByText('200', { exact: true })).toBeVisible()
  expect(page.url()).toBe(selection)
  await inspector.getByText('Source details', { exact: true }).click()
  await expect(inspector.getByText(source.payload_sha256, { exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('pay-employer-inspector-dark.png'), fullPage: true })
  await question(page, 'ONS ASHE observations')
  await expect(page.getByRole('cell', { name: 'Weekly earnings (£)', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '[suppressed]', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ source: 'external_comparators' })
  await question(page, 'Living Wage name checks')
  await expect(page.getByRole('cell', { name: 'No name match in this check', exact: true })).toBeVisible()
})

test('annual advert chart preserves gaps, local paging, source inspection and annotated exports', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const rows = [advert('zero', { salary_raw: '£0 to £40,000 a year', salary_min: 0 }), advert('hour', { salary_raw: '£12 an hour', salary_period: 'hour', salary_min: 12, salary_max: 12 }), advert('missing', { salary_raw: 'Not stated', salary_min: null, salary_max: null }), advert('reversed', { salary_raw: '£40,000 to £30,000 a year', salary_min: 40000, salary_max: 30000 }), advert('one-bound', { salary_raw: 'Up to £40,000 a year', salary_min: null }), advert('single', { salary_raw: '£30,000 a year', salary_max: 30000, salary_basis: 'single' }), ...Array.from({ length: 20 }, (_, i) => advert(`extra-${i}`))]
  const requests: URL[] = []
  await page.route('**/api/v1/pay*', route => {
    const url = new URL(route.request().url()); requests.push(url)
    return route.fulfill({ json: response({ nhs_job_adverts: url.searchParams.get('pay_unit') === 'hourly' ? [rows[1]] : rows }) })
  })
  await page.goto('/#/pay?lens=adverts&source=advertised_roles&provider_key=example-recovery&year_from=2020')
  const chart = page.getByRole('region', { name: 'Annual advertised pay chart', exact: true })
  await expect(chart.locator('svg')).toBeVisible()
  await expect(chart.getByText('Bounds are reversed in the source:', { exact: false })).toBeVisible()
  await expect(chart.getByText('Minimum not supplied.', { exact: false })).toBeVisible()
  await expect(chart.getByText('Source period: hour.', { exact: false })).toBeVisible()
  await expect(page.getByRole('cell', { name: '0', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ source: 'advertised_roles', provider_key: provider.provider_key })
  await chart.getByRole('button', { name: '1. Recovery worker zero', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Recovery worker zero', exact: true })
  await expect(inspector.getByRole('link', { name: 'Open original advert', exact: true })).toHaveAttribute('href', 'https://example.invalid/advert/zero')
  await inspector.getByText('Source details', { exact: true }).click()
  await expect(inspector.getByText('Not supplied in this response', { exact: true })).toHaveCount(2)
  const requestCount = requests.length
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByText('Rows 26 to 26 of 26 returned', { exact: true })).toBeVisible()
  await expect(inspector).toBeVisible()
  expect(requests.length).toBe(requestCount)
  const exported = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download displayed rows JSON', exact: true }).click()
  const dataFile = await exported
  const data = JSON.parse(readFileSync((await dataFile.path())!, 'utf8'))
  expect(data.rows).toHaveLength(1)
  expect(data._provenance).toMatchObject({ scope: 'displayed-page-of-returned-array', returned_array_rows: 26, local_offset: 25, array: 'nhs_job_adverts' })
  const manifestDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download reference manifest', exact: true }).click()
  const manifest = JSON.parse(readFileSync((await (await manifestDownload).path())!, 'utf8'))
  expect(manifest.rows).toHaveLength(1)
  expect(manifest.rows[0]).toMatchObject({ record_identifiers: { job_reference: 'extra-19' }, source_url: 'https://example.invalid/source/extra-19', payload_sha256: null })
  expect(manifest._provenance.canonical_query).not.toContain('pay_offset')
  expect(manifest._provenance.canonical_query).not.toContain('year_from')
  const csvDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download displayed rows CSV', exact: true }).click()
  const csv = readFileSync((await (await csvDownload).path())!, 'utf8')
  expect(csv).toContain('extra-19')
  expect(csv).not.toContain('extra-18')
  await page.evaluate(() => { const meta = document.createElement('meta'); meta.httpEquiv = 'Content-Security-Policy'; meta.content = "img-src 'self' data:"; document.head.append(meta) })
  const svgDownload = page.waitForEvent('download')
  await chart.getByRole('button', { name: 'Download annotated chart SVG', exact: true }).click()
  const svg = readFileSync((await (await svgDownload).path())!, 'utf8').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')
  expect(svg).toContain('1 displayed rows of 26 returned adverts')
  expect(svg).toContain('No annualisation')
  expect(svg).toContain('extra-19')
  const pngDownload = page.waitForEvent('download')
  await chart.getByRole('button', { name: 'Download annotated chart PNG', exact: true }).click()
  const png = await pngDownload
  await png.saveAs(info.outputPath('annual-advert-range-annotated.png'))
  expect(readFileSync((await png.path())!).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
  await page.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(chart).toHaveCount(0)
  expect(requests.length).toBe(requestCount)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Data', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('combobox', { name: 'Pay unit', exact: true }).selectOption('hourly')
  await expect(page).not.toHaveURL(/pay_offset=/)
  await expect(page).not.toHaveURL(/record=/)
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ source: 'advertised_roles', provider_key: provider.provider_key, pay_unit: 'hourly' })
  await page.getByRole('button', { name: 'Chart', exact: true }).click()
  await expect(page.getByText('No displayed advert has annual bounds that can be plotted.', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '1. Recovery worker hour', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Recovery worker hour', exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('pay-advert-mobile.png'), animations: 'disabled' })
})

test('pay distinguishes failed, absent, empty and ambiguous source records', async ({ page }) => {
  let state: 'failed' | 'absent' | 'empty' | 'duplicate' = 'failed'
  await page.route('**/api/v1/pay*', route => {
    if (state === 'failed') return route.fulfill({ status: 503, json: { error: 'Synthetic pay failure' } })
    const body = response({ nhs_job_adverts: state === 'duplicate' ? [advert('same'), advert('same')] : [] })
    if (state === 'absent') delete body.nhs_job_adverts
    return route.fulfill({ json: body })
  })
  await page.goto('/#/pay?lens=adverts&source=advertised_roles&pay_view=data')
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
  state = 'absent'
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('The selected source array was not supplied.', { exact: false })).toBeVisible()
  state = 'empty'
  await page.reload()
  await expect(page.getByText('No observations returned for this question', { exact: true })).toBeVisible()
  state = 'duplicate'
  await page.reload()
  await page.getByRole('button', { name: 'Inspect Recovery worker same, displayed row 1', exact: true }).click()
  await expect(page.getByRole('complementary', { name: 'Observation unavailable or ambiguous', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open original advert', exact: true })).toHaveCount(0)
  state = 'empty'
  await page.reload()
  await expect(page.getByRole('complementary', { name: 'Observation unavailable or ambiguous', exact: true })).toBeVisible()
})
