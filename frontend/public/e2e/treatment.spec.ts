import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const authority = { ons_code: 'E00000001', name: 'Example Authority' }
const source = { source_url: 'https://example.invalid/treatment', retrieved_at: '2026-08-01T12:00:00Z' }
const ftMetric = { key: 'fingertips:123', source: 'fingertips', indicator_id: 123, name: 'Synthetic treatment measure', topic: 'numbers_in_treatment', substance: 'Alcohol', unit: 'people', definition: 'Published people in the stated treatment population.', periods: ['2018/19', '2019/20', '2020/21'], period_count: 3, authority_count: 1, england_available: true, has_confidence_interval: true, ...source }
const ndtmsMetric = { key: 'ndtms:Table_2_1', source: 'ndtms', name: 'Synthetic prevalence table', topic: 'prevalence', substance: null, unit: 'modelled estimate with 95% CI', definition: 'Synthetic publication-specific estimates.', periods: null, period_range: ['2016', '2020'], period_count: 2, authority_count: 1, england_available: false, has_confidence_interval: true, ...source }
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/treatment_metrics') return route.fulfill({ json: { metrics: [ftMetric, ndtmsMetric], count: 2, caveat: 'Synthetic measures must not be subtracted from each other.' } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities: [authority] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture for this request' } })
    return route.continue()
  })
})

test('treatment chooses one measure and retains local uncertainty and England provenance limits', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  let ndtmsRequests = 0
  await page.route('**/api/v1/ndtms*', route => { ndtmsRequests++; return route.fulfill({ json: {} }) })
  await page.route('**/api/v1/fingertips*', route => {
    requests.push(new URL(route.request().url()))
    return route.fulfill({ json: { indicators: [{ ...ftMetric, indicator_name: ftMetric.name }], series: [
      { ...source, indicator_id: 123, ons_code: authority.ons_code, authority_name: authority.name, time_period: '2018/19', time_period_sortable: 2018, value: 0, lower_ci_95: 0, upper_ci_95: 2, value_note: 'Synthetic zero retained' },
      { ...source, indicator_id: 123, ons_code: authority.ons_code, authority_name: authority.name, time_period: '2020/21', time_period_sortable: 2020, value: null, lower_ci_95: null, upper_ci_95: null, value_note: '[suppressed]' },
    ], england_series: [{ indicator_id: 123, time_period: '2018/19', time_period_sortable: 2018, value: 100 }], caveat: 'Different source measures do not form an unmet-need calculation.' } })
  })
  await page.goto('/#/treatment?ons_code=E00000001&provider_key=retained&year_from=2020')
  await expect(page.getByRole('heading', { name: 'Choose a treatment measure', exact: true })).toBeVisible()
  expect(requests).toHaveLength(0)
  await page.getByRole('button', { name: `Choose ${ftMetric.name}`, exact: true }).click()
  const local = page.getByRole('region', { name: 'Selected authority observations', exact: true })
  const england = page.getByRole('region', { name: 'England observations', exact: true })
  await expect(local.locator('svg')).toBeVisible()
  await expect(local.getByRole('cell', { name: '0', exact: true })).toHaveCount(2)
  await expect(local.getByRole('cell', { name: '[suppressed]', exact: true })).toBeVisible()
  await expect(england.getByText('England values belong to this indicator', { exact: false })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ indicator_id: '123', ons_code: authority.ons_code })
  expect(ndtmsRequests).toBe(0)
  await local.getByRole('button', { name: 'Inspect Example Authority, 2018/19, displayed row 1', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Example Authority: 2018/19', exact: true })
  await expect(inspector.getByText('Published 95% bounds: 0 to 2.', { exact: true })).toBeVisible()
  await inspector.getByRole('button', { name: 'Save evidence reference', exact: true }).click()
  await expect(inspector.getByText('Evidence reference saved', { exact: false })).toBeVisible()
  const before = requests.length
  await local.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/local_view=data/)
  await expect(local.getByRole('button', { name: 'Data', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(requests.length).toBe(before)
  await page.reload()
  await expect(page.getByRole('complementary', { name: 'Example Authority: 2018/19', exact: true })).toBeVisible()
  await expect(local.getByRole('button', { name: 'Data', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const download = page.waitForEvent('download')
  await england.getByRole('button', { name: 'Download reference manifest', exact: true }).click()
  const manifest = JSON.parse(readFileSync((await (await download).path())!, 'utf8'))
  expect(manifest.rows[0]).toMatchObject({ source_url: null, retrieved_at: null, payload_sha256: null, value: 100 })
  expect(manifest._provenance.filters_applied_to_this_array).toEqual({ indicator_id: '123' })
  await page.screenshot({ path: info.outputPath('treatment-local-england-dark.png'), fullPage: true })
})

test('NDTMS keeps table catalogue, publication editions, numeric cohorts and suppressed rows distinct', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  const estimate = { ...source, table_ref: 'Table_2_1', dataset: 'Synthetic prevalence table', measure: 'Point estimate (number)', ons_code: authority.ons_code, authority_name: authority.name, age_group: '15 to 64', time_period: null, published_in: '2020/21', value: 1, value_text: '1', lower: 0, upper: 2, has_interval: true }
  await page.route('**/api/v1/ndtms*', route => {
    const url = new URL(route.request().url()); requests.push(url)
    return route.fulfill({ json: { datasets: [{ table_ref: 'Table_2_1', label: ndtmsMetric.name, rows: 120, authorities: 5, publications: 3 }], publications: [{ publication_slug: 'synthetic-2020', title: 'Synthetic publication', financial_year: '2020/21', cohort: 'Adult', document_url: 'https://example.invalid/publication', ...source }], estimates: url.searchParams.has('ons_code') ? [estimate, { ...estimate, published_in: '2021/22', value: 3, value_text: '3', lower: 2, upper: null, has_interval: true }, { ...estimate, measure: 'Mid-year population', value: 1000, value_text: '1000', lower: null, upper: null, has_interval: false }] : [], other_rows: url.searchParams.has('ons_code') ? [{ ...source, table_ref: 'Table_2_1', dataset: ndtmsMetric.name, measure: 'Suppressed source cell', ons_code: authority.ons_code, authority_name: authority.name, time_period: '2016', published_in: '2020/21', age_group: '15 to 64', value_text: 'c' }] : [], authority: url.searchParams.has('ons_code') ? authority : null, caveats: { suppressed: 'Synthetic marker c is not zero.', estimates: 'Read both published bounds.' } } })
  })
  await page.goto('/#/treatment?metric=ndtms%3ATable_2_1')
  await expect(page.getByRole('heading', { name: 'NDTMS publication and table catalogue', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({})
  await expect(page.getByRole('heading', { name: 'NDTMS numeric observations', exact: true })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Local authority', exact: true }).selectOption(authority.ons_code)
  await expect(page.getByRole('heading', { name: 'NDTMS numeric observations', exact: true })).toBeVisible()
  const cohort = JSON.stringify(['Point estimate (number)', '15 to 64'])
  const count = requests.length
  await page.getByRole('combobox', { name: 'Published measure and age group', exact: true }).selectOption(cohort)
  const numeric = page.getByRole('region', { name: 'Point estimate (number) · Age group: 15 to 64', exact: true })
  const context = page.getByRole('region', { name: 'NDTMS context and suppressed rows', exact: true })
  await expect(numeric.locator('svg')).toBeVisible()
  await expect(numeric.getByRole('cell', { name: '2020/21', exact: true })).toBeVisible()
  await expect(numeric.getByRole('cell', { name: '2021/22', exact: true })).toBeVisible()
  await expect(numeric.getByText('marks a paired interval', { exact: false })).toBeVisible()
  await expect(context.getByRole('cell', { name: 'c', exact: true })).toBeVisible()
  expect(requests.length).toBe(count)
  expect(Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ ons_code: authority.ons_code, table_ref: 'Table_2_1' })
  const downloaded = page.waitForEvent('download')
  await numeric.getByRole('button', { name: 'Download displayed rows JSON', exact: true }).click()
  const data = JSON.parse(readFileSync((await (await downloaded).path())!, 'utf8'))
  expect(data.rows).toHaveLength(2)
  expect(data.rows[0]).toMatchObject({ time_period: null, published_in: '2020/21', lower: 0 })
  await numeric.getByRole('button', { name: 'Inspect Point estimate (number), Not supplied, displayed row 2', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('dialog', { name: 'Point estimate (number): Not supplied', exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('treatment-ndtms-mobile.png'), animations: 'disabled' })
})
