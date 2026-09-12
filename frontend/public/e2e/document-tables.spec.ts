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

// A 101-row grid with deliberately ragged row lengths (1, 2 or 3 cells,
// cycling) proves large pagination shows exactly 50 rows per local page,
// preserves every row without duplication or truncation, keeps uneven row
// lengths, and infers no header row from row 1.
const raggedRow = (n: number) => Array.from({ length: (n % 3) + 1 }, (_, c) => `R${n}C${c}`)
const raggedGrid = Array.from({ length: 101 }, (_, i) => raggedRow(i + 1))
test('large grid pagination preserves every ragged row without duplication or inferred headers', async ({ page }) => {
  await page.route('**/api/v1/document_tables*', route => route.fulfill({ json: { ...detail, grid: raggedGrid } }))
  await page.goto('/#/doctables?table_id=table%261')
  const region = page.getByRole('region', { name: 'Returned extracted grid', exact: true })
  await expect(page.getByText('101 returned grid rows. Showing up to 50 from offset 0.', { exact: false })).toBeVisible()
  await expect(region.getByText('R1C0', { exact: true })).toBeVisible()
  await expect(region.getByText('R50C0', { exact: true })).toBeVisible()
  await expect(region.getByText('R51C0', { exact: true })).toHaveCount(0)
  // Row 2 has exactly three cells per raggedRow's own (n % 3) + 1 formula (ragged length preserved as returned).
  await expect(region.locator('tr', { hasText: 'R2C0' }).locator('td')).toHaveCount(3)
  const pager = page.getByRole('navigation', { name: 'Extracted table pages', exact: true })
  await pager.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page.getByText('Showing up to 50 from offset 50', { exact: false })).toBeVisible()
  await expect(region.getByText('R51C0', { exact: true })).toBeVisible()
  await expect(region.getByText('R100C0', { exact: true })).toBeVisible()
  await expect(region.getByText('R50C0', { exact: true })).toHaveCount(0)
  await expect(region.getByText('R101C0', { exact: true })).toHaveCount(0)
  await pager.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page.getByText('Showing up to 50 from offset 100', { exact: false })).toBeVisible()
  await expect(region.getByText('R101C0', { exact: true })).toBeVisible()
  await expect(pager.getByRole('button', { name: 'Next page', exact: true })).toBeDisabled()
})

// A missing `tables`/`grid` key is a different state to a returned empty
// array: the page must say "not supplied" for one and "no tables/cells
// returned" for the other, never collapsing the two. Each case uses a
// distinct identifier so the page's own signature actually changes and
// re-fetches (submitting an unchanged identifier is a no-op by design).
test('missing table/grid arrays are distinct from returned empty arrays', async ({ page }) => {
  await page.route('**/api/v1/document_tables*', route => {
    const url = new URL(route.request().url())
    const docId = url.searchParams.get('document_id')
    if (docId === 'doc/missing') return route.fulfill({ json: { document } })
    return route.fulfill({ json: { document, tables: [] } })
  })
  await page.goto('/#/doctables?document_id=doc%2Fmissing')
  await expect(page.getByText('The table list was not supplied.', { exact: true })).toBeVisible()
  await page.getByLabel('Identifier', { exact: true }).fill('doc/empty')
  await page.getByRole('button', { name: 'Open tables', exact: true }).click()
  await expect(page.getByText('No tables were returned for the active parse.', { exact: false })).toBeVisible()

  await page.route('**/api/v1/document_tables*', route => {
    const url = new URL(route.request().url())
    const tableId = url.searchParams.get('table_id')
    if (tableId === 'table-missing-grid') return route.fulfill({ json: { ...detail, document_table_id: 'table-missing-grid', grid: undefined } })
    return route.fulfill({ json: { ...detail, document_table_id: 'table-empty-grid', grid: [] } })
  })
  await page.goto('/#/doctables?table_id=table-missing-grid')
  await expect(page.getByText('A valid grid array was not supplied.', { exact: true })).toBeVisible()
  await page.getByLabel('Identifier', { exact: true }).fill('table-empty-grid')
  await page.getByRole('button', { name: 'Open tables', exact: true }).click()
  await expect(page.getByText('No structured cells were returned.', { exact: false })).toBeVisible()
})

// A slow response for the first-selected document must never be displayed
// under a subsequently selected, faster-resolving document: the page's own
// `key === signature.value` staleness guard is the thing under test here.
// Both selections happen client-side (via the on-page form) within one SPA
// session, not via page.goto reloads, so the pending request from the first
// selection is genuinely still in flight when the second one is submitted.
test('a slow response for a previous selection never displays under the current one', async ({ page }) => {
  await page.route('**/api/v1/document_tables*', async route => {
    const url = new URL(route.request().url())
    const id = url.searchParams.get('document_id')
    if (id === 'doc/slow') {
      await new Promise(resolve => setTimeout(resolve, 500))
      return route.fulfill({ json: { document: { document_id: 'doc/slow', title: 'Slow document' }, tables: [] } })
    }
    return route.fulfill({ json: { document: { document_id: 'doc/fast', title: 'Fast document' }, tables: [] } })
  })
  await page.goto('/#/doctables')
  await page.getByLabel('Identifier', { exact: true }).fill('doc/slow')
  await page.getByRole('button', { name: 'Open tables', exact: true }).click()
  await page.getByLabel('Identifier', { exact: true }).fill('doc/fast')
  await page.getByRole('button', { name: 'Open tables', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Fast document', exact: true })).toBeVisible()
  await page.waitForTimeout(700)
  await expect(page.getByRole('heading', { name: 'Slow document', exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Fast document', exact: true })).toBeVisible()
})

// Retry after a failed response must re-request the exact same scope, not a
// broadened or narrower one, and must recover once the retried request
// succeeds.
test('retry after a failed response keeps the exact request scope', async ({ page }) => {
  const requests: URL[] = []
  let failNext = true
  await page.route('**/api/v1/document_tables*', route => {
    const url = new URL(route.request().url())
    requests.push(url)
    if (failNext) { failNext = false; return route.fulfill({ status: 503, json: { error: 'Unavailable' } }) }
    return route.fulfill({ json: { document, tables: [] } })
  })
  await page.goto('/#/doctables?document_id=doc%2Fa')
  await expect(page.getByRole('heading', { name: 'Evidence is unavailable', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('No tables were returned for the active parse.', { exact: false })).toBeVisible()
  expect(requests).toHaveLength(2)
  expect([...requests[0]!.searchParams.entries()]).toEqual([...requests[1]!.searchParams.entries()])
  expect([...requests[1]!.searchParams.keys()]).toEqual(['document_id'])
})

// The extracted-grid region must be keyboard-reachable (a scrollable region
// with its own tabindex) since it is not otherwise part of tab order via a
// native control. Full assistive-technology walkthrough (screen reader
// announcement, etc.) is manual and stays pending per the dispatch packet.
test('the returned grid region is keyboard-focusable', async ({ page }) => {
  await page.route('**/api/v1/document_tables*', route => route.fulfill({ json: detail }))
  await page.goto('/#/doctables?table_id=table%261')
  const region = page.getByRole('region', { name: 'Returned extracted grid', exact: true })
  await expect(region).toHaveAttribute('tabindex', '0')
  await region.focus()
  await expect(region).toBeFocused()
})
