import { expect, test } from '@playwright/test'
const providers = Array.from({ length: 5 }, (_, index) => ({ provider_key: `p${index + 1}`, canonical_name: `Provider ${index + 1}` }))
const authorities = [{ ons_code: 'E00000001', name: 'Authority 1', region: null }]
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('comparison preserves mixed selections and exact charity fields within the chosen type', async ({ page }, info) => {
  const requests: URL[] = []
  await page.route('**/api/v1/compare?*', route => { requests.push(new URL(route.request().url())); return route.fulfill({ json: { providers, authorities: [], series: { charity: { rows: [{ provider_key: 'p1', canonical_name: 'Provider 1', financial_year_end: '2024-03-31', total_income: 1234, total_expenditure: 0, source_url: 'https://example.invalid/accounts', retrieved_at: '2026-09-01', payload_sha256: 'fixture-hash' }], caveat: 'Synthetic charity caveat.' }, provider_contracts: { rows: [{ provider_key: 'p1', count: 99, value_gbp: 9999, year: 2025 }] } }, caveats: { cross_layer: 'Keep sources separate.' } } }) })
  await page.goto('/#/compare?ons_code=E00000001&provider_key=p1&provider_key=p2&year_from=2025')
  await expect(page.getByText('Choose authorities or providers for this comparison.', { exact: false })).toBeVisible()
  expect(requests).toHaveLength(0)
  await page.getByRole('button', { name: 'Compare providers', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'total income', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '1,234', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '0', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2024-03-31', exact: true })).toBeVisible()
  await expect(page.getByText('p2: no observations were returned in this source.', { exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'count', exact: true })).toHaveCount(0)
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ provider_key: 'p2' })
  expect(requests[0]!.searchParams.getAll('provider_key')).toEqual(['p1', 'p2'])
  await expect(page).toHaveURL(/ons_code=E00000001/)
  await page.getByRole('heading', { level: 1 }).evaluate(element => { element.setAttribute('tabindex', '-1'); (element as HTMLElement).focus({ preventScroll: true }) })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('compare-charity-foundation.png'), fullPage: true, animations: 'disabled' })
})
test('comparison never truncates oversized selections and preserves all provider pay rows', async ({ page }) => {
  let requests = 0
  await page.route('**/api/v1/provider_compare?*', route => { requests++; return route.fulfill({ json: { providers: providers.slice(0, 4), layers: { nhs_jobs: { unit: 'Original advertised periods', caveat: 'Synthetic advert caveat.', by_provider: { p1: Array.from({ length: 10 }, (_, index) => ({ provider_key: 'p1', job_title: `Role ${index + 1}`, salary_raw: '£15 per hour', salary_period: 'hourly', source_url: 'https://example.invalid/advert', retrieved_at: null })), p2: [], p3: [], p4: [] } }, living_wage: { by_provider: { p1: [{ accredited: null }] } } }, caveat: 'No rankings.' } }) })
  await page.goto('/#/compare?provider_key=p1&provider_key=p2&provider_key=p3&provider_key=p4&provider_key=p5&lens=nhs_jobs')
  await expect(page.getByText('Choose no more than four peers.', { exact: false })).toBeVisible()
  expect(requests).toBe(0)
  await page.getByRole('button', { name: 'Remove Provider 5', exact: true }).click()
  await expect(page.getByText('Role 10: £15 per hour', { exact: true })).toBeVisible()
  expect(requests).toBe(1)
  await expect(page.getByText('No matching entry was recorded', { exact: false })).toHaveCount(0)
})
test('one-peer comparison can request a source without unrelated filters', async ({ page }) => {
  let request: URL | undefined
  await page.route('**/api/v1/compare?*', route => { request = new URL(route.request().url()); return route.fulfill({ json: { authorities, providers: [], series: { grant: { rows: [], caveat: 'Synthetic grant caveat.' } } } }) })
  await page.goto('/#/compare?ons_code=E00000001&year_to=2025')
  await expect(page.getByText('One peer is selected.', { exact: false })).toBeVisible()
  await expect(page.getByText('E00000001: no observations were returned in this source.', { exact: true })).toBeVisible()
  expect(Object.fromEntries(request!.searchParams)).toEqual({ ons_code: 'E00000001' })
})
