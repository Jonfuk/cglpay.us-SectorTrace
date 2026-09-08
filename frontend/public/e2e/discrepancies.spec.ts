import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const observations = [{ source: 'CQC syndication API', value: 'Good', as_of: '2024-01-01', source_url: 'https://example.invalid/location' }, { source: 'CQC bulk export', value: 'Requires improvement', as_of: '2023-01-01', source_url: 'https://example.invalid/location' }]
const response = { entity: { kind: 'provider', id: 'p1', name: 'Provider one' }, checked: 3, discrepancies: [{ id: 'cqc_rating:l1', label: 'CQC rating', observations, distinct_values: ['Good', 'Requires improvement'] }], agreed: [{ id: 'name', label: 'Name', value: 'Provider one', sources: ['One source'] }, { id: 'number', label: 'Number', value: null, sources: [] }], caveat: 'Synthetic scope caveat.', note: 'Original note — unchanged; text.' }
test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers: [{ provider_key: 'p1', canonical_name: 'Provider one' }] } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities: [{ ons_code: 'E00000001', name: 'Authority one' }] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('source comparison preserves paired dates, original references and exact entity scope', async ({ page }, info) => {
  const requests: URL[] = []
  await page.route('**/api/v1/discrepancies?*', route => { requests.push(new URL(route.request().url())); return route.fulfill({ json: response }) })
  await page.goto('/#/discrepancies?provider_key=p1&ons_code=E00000001')
  await expect(page.getByRole('navigation', { name: 'Main sections' }).getByRole('link', { name: 'Verification tools', exact: true })).toHaveClass(/router-link-active/)
  await expect(page.getByText('Choose exactly one provider or authority.', { exact: false })).toBeVisible()
  expect(requests).toHaveLength(0)
  await page.getByRole('combobox', { name: 'Provider', exact: true }).selectOption('p1')
  await expect(page.getByRole('cell', { name: '2024-01-01', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2023-01-01', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ provider_key: 'p1' })
  const rows = page.getByRole('region', { name: 'CQC rating records', exact: true })
  await rows.getByRole('button', { name: 'Inspect record 2', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Comparison record', exact: true })
  await expect(inspector).toContainText('CQC bulk export')
  await expect(inspector).toContainText('2023-01-01')
  expect(requests).toHaveLength(1)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download returned comparison JSON', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await download).path())!, 'utf8'))
  expect(exported.rows).toEqual([response])
  expect(exported._provenance.limitations).toContain('CQC comparisons use rating dates')
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.screenshot({ path: info.outputPath('source-comparison.png'), fullPage: true })
})
test('empty and absent comparisons never imply that all sources agree', async ({ page }) => {
  await page.route('**/api/v1/discrepancies?*', route => route.fulfill({ json: { ...response, discrepancies: [] } }))
  await page.goto('/#/discrepancies?provider_key=p1')
  await expect(page.getByText('No differing observations were returned.', { exact: false })).toBeVisible()
  await expect(page.getByText('One named source does not establish agreement between sources.', { exact: false })).toBeVisible()
  await expect(page.getByText('Every source that reports these fields agrees.', { exact: true })).toHaveCount(0)
  await page.route('**/api/v1/discrepancies?*', route => route.fulfill({ json: { ...response, discrepancies: null, agreed: null } }))
  await page.reload()
  await expect(page.getByText('The differing-observation array was not supplied.', { exact: true })).toBeVisible()
  await expect(page.getByText('The source did not supply a row array for this table.', { exact: true })).toBeVisible()
})

test('source comparisons can retry on mobile without broadening the entity request', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let fail = true
  const requests: URL[] = []
  await page.route('**/api/v1/discrepancies?*', route => {
    requests.push(new URL(route.request().url()))
    return route.fulfill(fail ? { status: 503, json: { error: 'Fixture unavailable' } } : { json: response })
  })
  await page.goto('/#/discrepancies?provider_key=p1')
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download returned comparison JSON' })).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('cell', { name: '2024-01-01', exact: true })).toBeAttached()
  expect(requests.every(url => url.searchParams.toString() === 'provider_key=p1')).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
