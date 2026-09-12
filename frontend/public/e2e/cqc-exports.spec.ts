import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const activity = 'Treatment of disease, disorder or injury'
const rows = [
  { location_id: 'location-1', location_name: 'Example registration', regulated_activities: activity, overall_rating: 'Good', rating_source: 'bulk_export', overall_rating_date: '2024-01-02', registration_date: '2020-01-01', latitude: 52, longitude: -1, source_url: 'https://example.invalid/location', retrieved_at: '2026-09-01' },
  { location_id: 'location-2', location_name: 'Unlocated registration', latitude: null, longitude: null, source_url: null, retrieved_at: null },
]
const response = { results: rows, total: 203, without_coordinate: 70, offset: 100, limit: 100, filters: { regulated_activity: activity }, facets: { registration_status: [], overall_rating: [], service_type: [] }, caveat: 'Synthetic CQC caveat.' }
test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers: [] } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities: [] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('CQC downloads preserve the complete returned page and distinct rating provenance', async ({ page }, info) => {
  let requests = 0
  await page.route('**/api/v1/cqc_locations?*', route => { requests++; return route.fulfill({ json: response }) })
  await page.goto(`/#/cqc?offset=100&regulated_activity=${encodeURIComponent(activity)}`)
  const jsonEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download result-window JSON', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await jsonEvent).path())!, 'utf8'))
  expect(exported.rows).toEqual(rows)
  expect(exported._provenance.request).toEqual({ regulated_activity: activity, offset: 100, limit: 100 })
  expect(exported._provenance.response_context).toEqual({ ...response, results: undefined })
  expect(exported._provenance.scope).toBe('complete-returned-page')
  expect(exported._provenance.mapped_records).toBe(1)
  expect(exported.rows[0].payload_sha256).toBeUndefined()
  expect(exported.rows[1].retrieved_at).toBeNull()
  const csvEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download loaded registrations CSV' }).click()
  const csv = readFileSync((await (await csvEvent).path())!, 'utf8')
  expect(csv).toContain(`"${activity}"`)
  expect(csv).toContain('Unlocated registration')
  await page.getByRole('button', { name: 'Inspect Example registration', exact: true }).click()
  const selectedEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download selected registration JSON' }).click()
  const selected = JSON.parse(readFileSync((await (await selectedEvent).path())!, 'utf8'))
  expect(selected.rows).toEqual([rows[0]])
  expect(selected._provenance.selected_location_id).toBe('location-1')
  expect(selected._provenance.provenance_limitations).toContain('no payload hash or separate bulk-rating source URL')
  expect(requests).toBe(1)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.screenshot({ path: info.outputPath('cqc-downloads.png'), fullPage: true })
})
test('CQC missing arrays and duplicate location identifiers do not create substitute exports', async ({ page }) => {
  await page.route('**/api/v1/cqc_locations?*', route => route.fulfill({ json: { ...response, results: null } }))
  await page.goto('/#/cqc?location_id=location-1')
  await expect(page.getByText('The response did not supply a registration array.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download result-window JSON' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retry registrations', exact: true })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Registration pages' })).toHaveCount(0)
  await page.route('**/api/v1/cqc_locations?*', route => route.fulfill({ json: { ...response, results: [rows[0], { ...rows[0], location_name: 'Conflicting registration' }] } }))
  await page.reload()
  await expect(page.getByText('Several returned records share location location-1.', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download selected registration JSON' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Download result-window JSON' })).toBeVisible()
})

test('CQC exports wait for the requested page and never reuse the previous result window', async ({ page }) => {
  let release: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/cqc_locations?*', async route => {
    const offset = Number(new URL(route.request().url()).searchParams.get('offset'))
    if (offset === 100) await gate
    return route.fulfill({ json: { ...response, offset, results: offset ? [rows[1]] : [rows[0]] } })
  })
  await page.goto('/#/cqc')
  await expect(page.getByRole('button', { name: 'Download result-window JSON' })).toBeVisible()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  try {
    await expect(page).toHaveURL(/offset=100/)
    await expect(page.getByRole('button', { name: 'Download result-window JSON' })).toHaveCount(0)
  } finally { release() }
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download result-window JSON' }).click()
  const exported = JSON.parse(readFileSync((await (await download).path())!, 'utf8'))
  expect(exported.rows).toEqual([rows[1]])
  expect(exported._provenance.request.offset).toBe(100)
  expect(exported._provenance.response_context.offset).toBe(100)
})
