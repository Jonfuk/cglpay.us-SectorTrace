import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error('Unexpected external request')
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('revision subject can be pinned without losing original fields or unknown identity', async ({ page }, info) => {
  const requests: URL[] = []
  const response = { kind: 'ocds', a: { notice_id: 'old/a', ocid: 'subject', source_url: 'https://example.invalid/a', retrieved_at: '2020-01-01' }, b: { notice_id: 'new&b', ocid: 'subject', retrieved_at: null }, fields: [{ field: 'title', class: 'source', changed: true, a: 'Original; text — preserved.', b: '<script>literal</script>' }], counts: { changed_source: 1, changed_derived: 0 } }
  await page.route('**/api/v1/record_diff*', route => { requests.push(new URL(route.request().url())); return route.fulfill({ json: response }) })
  await page.goto('/#/revisions?ocid=subject')
  await expect(page.getByText('Identity check: Not supplied.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Use this exact A/B pair' }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1]!.searchParams.get('a')).toBe('old/a')
  expect(requests[1]!.searchParams.get('b')).toBe('new&b')
  expect(requests[1]!.searchParams.has('ocid')).toBe(false)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download returned comparison JSON', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await download).path())!, 'utf8'))
  expect(exported.rows).toEqual([response])
  expect(exported._provenance.request.a).toBe('old/a')
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.screenshot({ path: info.outputPath('revisions.png'), fullPage: true })
})
test('repeated selectors make no request and incomplete document response cannot imply identical text', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let requests = 0
  await page.route('**/api/v1/record_diff*', route => { requests++; return route.fulfill({ json: { kind: 'document', a: { document_version_id: 'a' }, b: { document_version_id: 'b' }, counts: { changed: 0 }, truncated: true } }) })
  await page.goto('/#/revisions?kind=document&a=a&a=a&b=b')
  await expect(page.getByText('Supply one subject identifier', { exact: false })).toBeVisible()
  expect(requests).toBe(0)
  await page.getByRole('button', { name: 'Compare', exact: true }).click()
  await expect(page.getByText('The comparison is truncated.', { exact: false })).toBeVisible()
  expect(requests).toBe(1)
  await expect(page.getByText('The body text is identical', { exact: false })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
