import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const source = 'https://example.invalid/report?edition=2020&part=2'
const digest = '0123456789abcdef'.repeat(4)
const detail = { url: source, state: 'gone_at_last_check', state_label: 'Gone at the recorded check.', last_checked: '2026-09-01', last_http_status: 404, archive: { held: true, verified: false, sha256: digest, computed_sha256: 'f'.repeat(64), bytes: 123, recorded_path: 'data/raw/old-copy' }, note: 'Original note; retained — exactly.', caveat: 'Synthetic source caveat.' }
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('source links retain full hashes, exact URL and separate archive limitations', async ({ page }, info) => {
  const requests: URL[] = []
  await page.route('**/api/v1/source_link*', route => { const url = new URL(route.request().url()); requests.push(url); return route.fulfill({ json: url.searchParams.has('url') ? detail : { states: ['not_recorded', 'unknown_url'], by_state: { not_recorded: 12 }, note: 'Cited rows, not URLs.' } }) })
  await page.goto(`/#/links?url=${encodeURIComponent(source)}`)
  const status = page.getByRole('region', { name: 'Recorded source status', exact: true })
  await expect(status.getByText(digest, { exact: true })).toBeVisible()
  await expect(status.getByText('Checksum mismatch reported by the API', { exact: true })).toBeVisible()
  await expect(status.getByText('2026-09-01', { exact: true })).toBeVisible()
  expect(requests).toHaveLength(1)
  expect(requests[0]!.searchParams.get('url')).toBe(source)
  await expect(page.getByRole('link', { name: /archive/i })).toHaveCount(0)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download recorded status JSON', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await download).path())!, 'utf8'))
  expect(exported.rows).toEqual([detail])
  expect(exported._provenance.limitations).toContain('separate retrieval date is not supplied')
  await page.getByText('Warehouse cited-row counts', { exact: true }).click()
  expect(requests).toHaveLength(1)
  await page.getByRole('button', { name: 'Load recorded counts' }).click()
  await expect(page.getByRole('cell', { name: 'Not supplied', exact: true })).toBeVisible()
  expect(requests).toHaveLength(2)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.screenshot({ path: info.outputPath('source-link-status.png'), fullPage: true })
})
test('source link queries reject repeated values and missing archive metadata stays unknown', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let requests = 0
  await page.route('**/api/v1/source_link*', route => { requests++; return route.fulfill({ json: { ...detail, archive: undefined } }) })
  await page.goto(`/#/links?url=${encodeURIComponent(source)}&url=${encodeURIComponent(source)}`)
  await expect(page.getByText('Supply exactly one valid HTTP or HTTPS source URL.', { exact: false })).toBeVisible()
  expect(requests).toBe(0)
  await page.getByRole('textbox', { name: 'Source URL', exact: true }).fill(source)
  await page.getByRole('button', { name: 'Check recorded status' }).click()
  await expect(page.getByRole('region', { name: 'Recorded source status', exact: true })).toBeVisible()
  await expect(page.getByText('Not held', { exact: true })).toHaveCount(0)
  await expect(page.getByText('No verification result supplied', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
