import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const document = { document_id: 'doc/a', title: 'Fixture extraction', source_url: 'https://example.invalid/source', retrieved_at: '2020-03-04' }
const detail = { document, document_table_id: 'table&1', element_id: 'element/a', page_number: 8, extraction_status: 'structured', grid: [['Cell; unchanged — text', '', '=1+1'], ['<script>literal</script>']], markdown: '<b>raw text</b>', context: [{ element_type: 'HEADING', text: 'Nearby heading' }], note: 'Original note.' }
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error('Unexpected external request')
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture' } })
    return route.continue()
  })
})
test('table previews open exact full grids and preserve cells in scoped downloads', async ({ page }, info) => {
  const requests: URL[] = []
  await page.route('**/api/v1/document_tables*', route => {
    const url = new URL(route.request().url())
    requests.push(url)
    return route.fulfill({ json: url.searchParams.has('table_id') ? detail : { document, tables: [{ document_table_id: 'table&1', page_number: 8, extraction_status: 'structured', preview: [['preview']], row_count: 2, column_count: 3 }] } })
  })
  await page.goto('/#/doctables?document_id=doc%2Fa&irrelevant=value')
  await expect(page.getByText('Preview only, up to three rows.', { exact: false })).toBeVisible()
  expect([...requests[0]!.searchParams.keys()]).toEqual(['document_id'])
  await page.getByRole('button', { name: 'Open exact table 1' }).click()
  const grid = page.getByRole('region', { name: 'Returned extracted grid', exact: true })
  await expect(grid.getByText('<script>literal</script>', { exact: true })).toBeVisible()
  await expect(grid.getByText('Empty cell', { exact: true })).toBeVisible()
  expect(requests[1]!.searchParams.get('table_id')).toBe('table&1')
  expect(requests[1]!.searchParams.has('document_id')).toBe(false)
  const readerHref = await page.getByRole('link', { name: 'Open document reader' }).getAttribute('href')
  expect(new URLSearchParams(readerHref!.split('?')[1]).get('element_id')).toBe('element/a')
  const jsonWait = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download returned tables JSON', exact: true }).click()
  const exported = JSON.parse(readFileSync((await (await jsonWait).path())!, 'utf8'))
  expect(exported.rows).toEqual([detail])
  const csvWait = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download full returned grid CSV' }).click()
  const csv = readFileSync((await (await csvWait).path())!, 'utf8')
  expect(csv.replace(/^\uFEFF/, '')).toBe('"Cell; unchanged — text","","\'=1+1"\r\n"<script>literal</script>"')
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.screenshot({ path: info.outputPath('document-table.png'), fullPage: true })
})
test('table parent mismatch prevents export and markdown-only extraction remains literal on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  let requests = 0
  await page.route('**/api/v1/document_tables*', route => { requests++; return route.fulfill({ json: { ...detail, grid: [], extraction_status: 'markdown_only' } }) })
  await page.goto('/#/doctables?table_id=table%261&document_id=wrong')
  await expect(page.getByRole('alert').filter({ hasText: 'does not establish a match' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download returned tables JSON' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Open tables', exact: true }).click()
  await expect(page.getByText('No structured cells were returned.', { exact: false })).toBeVisible()
  await page.getByText('Extraction text as returned', { exact: true }).click()
  await expect(page.getByText('<b>raw text</b>', { exact: true })).toBeVisible()
  expect(requests).toBe(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
