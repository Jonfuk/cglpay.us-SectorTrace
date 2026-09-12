import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

test.beforeEach(async ({ page }) => {
  // All evidence is synthetic. Any non-local request fails the test rather
  // than quietly reaching a real source or an icon/font service.
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers: [
      { provider_key: 'example-recovery', canonical_name: 'Example Recovery', status: 'active', contract_count: 2, cqc_locations: 0, tribunal_count: null },
      { provider_key: 'other-provider', canonical_name: 'Other Provider', status: 'active' },
    ] } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities: [
      { ons_code: 'E00000001', name: 'Example Authority', type: 'Unitary authority', region: 'Example region' },
    ] } })
    if (url.pathname === '/api/v1/freshness') return route.fulfill({ json: { tables: [] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'Fixture unavailable' } })
    return route.continue()
  })
})

test('homepage remains useful without summary data and respects the theme choice', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Find sector evidence' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('combobox', { name: 'Colour theme' }).selectOption('light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.screenshot({ path: info.outputPath('homepage-light.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('combobox', { name: 'Search for' }).selectOption('authorities')
  await page.getByRole('searchbox', { name: 'Name or identifier' }).fill('E00000001')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Example Authority', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#\/authorities\?q=E00000001/)
  await page.screenshot({ path: info.outputPath('authority-directory-light.png'), fullPage: true })
})

test('directory inspection retains identity and missing holdings on refresh', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/#/providers?q=Example')
  await page.getByRole('button', { name: 'Inspect Example Recovery' }).click()
  await expect(page).toHaveURL(/inspect=example-recovery/)
  await expect(page.getByRole('complementary', { name: 'Example Recovery' })).toBeVisible()
  await expect(page.getByText('Not supplied', { exact: true })).toHaveCount(2)
  await page.reload()
  await expect(page.getByRole('complementary', { name: 'Example Recovery' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open profile', exact: true })).toHaveAttribute('href', /providers\/example-recovery/)
  await page.screenshot({ path: info.outputPath('provider-inspector-dark.png'), fullPage: true })
})

test('mobile drawer contains navigation and restores access to the page', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/search')
  await page.getByRole('button', { name: 'Sections', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Sections' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('link', { name: 'Authorities', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'Authorities', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Inspect Example Authority' }).click()
  await expect(page.getByRole('dialog', { name: 'Example Authority' })).toBeVisible()
  await expect.poll(async () => (await page.getByRole('dialog', { name: 'Example Authority' }).boundingBox())?.x).toBe(0)
  await page.screenshot({ path: info.outputPath('authority-inspector-mobile.png'), animations: 'disabled' })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('saving a view preserves earlier version-one entries and updates the collection immediately', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('st.saved', JSON.stringify({ v: 1, data: [{ id: 'old', label: 'Existing research', href: '#/documents?q=old', at: 1 }] })))
  await page.goto('/#/providers?q=Example')
  await page.getByRole('button', { name: 'Save view', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'View saved in this browser.' })).toBeVisible()
  await page.getByRole('navigation', { name: 'Main sections' }).getByRole('link', { name: 'Saved views', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Existing research', exact: true })).toBeVisible()
  await expect(page.locator('main a[href="#/providers?q=Example"]')).toBeVisible()
})

test('legacy coverage history preserves source periods and working evidence links', async ({ page }) => {
  await page.route('**/api/v1/coverage_timeline*', route => route.fulfill({ json: {
    entity: { kind: 'provider', id: 'example-recovery', name: 'Example Recovery' },
    years: [2020, 2021, 2022], span: { min: 2020, max: 2022 }, held_count: 1,
    sources: [
      { dataset_id: 'charity-finance', title: 'Charity accounts', period_kind: 'financial year', periods: ['2020/21', '2022/23'], held: true, link: '#/providers/example-recovery' },
      { dataset_id: 'procurement', title: 'Procurement notices', period_kind: 'year', periods: [], held: false, link: '#/contracts?provider=example-recovery' },
    ], note: 'Coverage periods are source-specific.', caveat: 'A gap is not zero activity.',
  } }))
  await page.goto('/#/timeline?provider=example-recovery')
  await expect(page).toHaveURL(/#\/coverage\?.*lens=history/)
  await expect(page.getByRole('heading', { name: 'Coverage history', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2020/21, 2022/23', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'No periods held in this response', exact: true })).toBeVisible()
  await page.getByRole('row').filter({ hasText: 'Procurement notices' }).getByRole('link', { name: 'Open evidence' }).click()
  await expect(page).toHaveURL(/#\/contracts\?provider_key=example-recovery/)
})

test('legacy passage links resolve exact text and retain search context after refresh', async ({ page }, info) => {
  await page.route('**/api/v1/documents/doc-fixture*', route => route.fulfill({ json: {
    document_id: 'doc-fixture', document_type: 'committee_paper', title: 'Example committee paper', title_basis: 'filename', source_title: null,
    source_url: 'https://example.invalid/paper.pdf', retrieved_at: '2026-09-01T10:00:00Z', published_at: '2026-08-01', source_system: 'committee_paper_promotion',
    parser: { name: 'fixture-parser', version: '1' }, anchor_element_id: 'p2', context: 8, element_count: 2, range: { from: 0, to: 2 }, has_more_before: false, has_more_after: false,
    elements: [
      { document_element_id: 'p1', sequence: 0, page_number: 1, element_type: 'heading', heading_level: 1, text: 'Committee record', is_anchor: false },
      { document_element_id: 'p2', sequence: 1, page_number: 2, element_type: 'paragraph', heading_level: null, text: 'Exact source text <script>window.untrusted = true</script>', is_anchor: true },
    ], caveat: 'Extracted text needs its source context.',
  } }))
  await page.goto('/#/documents?doc=doc-fixture&el=p2&q=words')
  await expect(page).toHaveURL(/#\/documents\/doc-fixture\?.*element_id=p2/)
  await expect(page.getByRole('heading', { name: 'Example committee paper', exact: true })).toBeVisible()
  await expect(page.getByText('Exact source text <script>window.untrusted = true</script>', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => 'untrusted' in window)).toBe(false)
  await page.reload()
  await expect(page.getByText('Page 2 · Selected passage', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Back to document search' })).toHaveAttribute('href', /documents\?q=words/)
  await page.screenshot({ path: info.outputPath('document-reader-dark.png'), fullPage: true, animations: 'disabled' })
  await page.locator('article').filter({ hasText: 'Exact source text' }).getByRole('button', { name: 'Save note' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Passage reference saved' })).toBeVisible()
})

test('a stale passage is explained without requesting a substitute element', async ({ page }) => {
  const requested: string[] = []
  await page.route('**/api/v1/documents/doc-stale*', route => {
    requested.push(new URL(route.request().url()).searchParams.get('element_id') ?? '')
    return route.fulfill({ status: 400, json: { error: 'Element is not in the active version.' } })
  })
  await page.goto('/#/documents/doc-stale?element_id=old-element')
  await expect(page.getByRole('heading', { name: 'Exact passage unavailable' })).toBeVisible()
  await expect(page.getByText(/No replacement passage has been selected/)).toBeVisible()
  expect(requested).toEqual(['old-element'])
  await expect(page).toHaveURL(/element_id=old-element/)
})

test('document results and reader share a URL without refetching search on pane changes', async ({ page }, info) => {
  let searches = 0
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.route('**/api/v1/document_search*', route => {
    searches += 1
    return route.fulfill({ json: {
      query: 'words', total: 1, limit: 50, offset: 0, caveat: 'Synthetic search fixture.', facets: { source_system: [], document_type: [] },
      results: [{ document_id: 'split-doc', document_element_id: 'split-passage', title: 'Selected paper', title_basis: 'source_label', source_title: 'Selected paper', source_system: 'committee_paper_promotion', document_type: 'committee_paper', page_number: 3, snippet: 'The matching words.', text: 'The matching words.', published_at: null, retrieved_at: '2026-09-01', source_url: 'https://example.invalid/source' }],
    } })
  })
  await page.route('**/api/v1/documents/split-doc*', route => route.fulfill({ json: {
    document_id: 'split-doc', title: 'Selected paper', title_basis: 'source_label', source_title: 'Selected paper', document_type: 'committee_paper', source_system: 'committee_paper_promotion', source_url: 'https://example.invalid/source', published_at: null, retrieved_at: '2026-09-01', parser: { name: 'fixture', version: '1' }, element_count: 1, range: { from: 0, to: 1 }, context: 8, anchor_element_id: 'split-passage', has_more_before: false, has_more_after: false, caveat: 'Synthetic passage fixture.',
    elements: [{ document_element_id: 'split-passage', sequence: 0, page_number: 3, element_type: 'paragraph', heading_level: null, text: 'The matching words in their source context.', is_anchor: true }],
  } }))
  await page.goto('/#/documents?q=words')
  await page.getByRole('button', { name: 'Read passage', exact: true }).click()
  await expect(page).toHaveURL(/document_id=split-doc/)
  await expect(page.getByText('The matching words in their source context.', { exact: true })).toBeVisible()
  const separator = page.getByRole('separator', { name: 'Resize Results and Reader' })
  const before = Number(await separator.getAttribute('aria-valuenow'))
  await separator.focus()
  await page.keyboard.press('ArrowLeft')
  await expect(separator).toHaveAttribute('aria-valuenow', String(before - 2))
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('document-search-split.png'), fullPage: true, animations: 'disabled' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Results', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Read passage', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Reader', exact: true }).click()
  await expect(page.getByText('The matching words in their source context.', { exact: true })).toBeVisible()
  expect(searches).toBe(1)
  await expect(page.getByRole('link', { name: 'Open reader', exact: true })).toHaveAttribute('href', /documents\/split-doc\?.*element_id=split-passage/)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await expect(separator).toHaveAttribute('aria-valuenow', String(before - 2))
})

test('a shared reader survives search failure and retry without changing the selected passage', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  let searches = 0
  await page.route('**/api/v1/document_search*', route => {
    searches += 1
    return searches === 1 ? route.fulfill({ status: 503, json: { error: 'Search unavailable' } }) : route.fulfill({ json: { results: [], total: 0 } })
  })
  await page.route('**/api/v1/documents/independent*', route => route.fulfill({ json: {
    document_id: 'independent', title: 'Independent reader', title_basis: 'source_label', parser: { name: 'fixture', version: '1' }, range: { from: 0, to: 1 }, element_count: 1,
    elements: [{ document_element_id: 'exact', text: 'This exact passage remains readable.', is_anchor: true }],
  } }))
  await page.goto('/#/documents?q=words&document_id=independent&element_id=exact&pane=reader')
  await expect(page.getByText('This exact passage remains readable.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Evidence is unavailable', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No matching evidence found' })).toBeVisible()
  await expect(page.getByText('This exact passage remains readable.', { exact: true })).toBeVisible()
  await expect(page).toHaveURL(/document_id=independent&element_id=exact/)
})

test('tablet navigation retains accessible names when labels are collapsed', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 })
  await page.goto('/#/search')
  const nav = page.getByRole('navigation', { name: 'Main sections' })
  await expect(nav.getByRole('link', { name: 'Providers', exact: true })).toBeVisible()
  await nav.getByRole('link', { name: 'Providers', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Providers', exact: true })).toBeVisible()
})

test('provider lenses retain independent holdings, disclosure states and lazy notice scope', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  let profiles = 0
  const noticeQueries: string[] = []
  await page.route('**/api/v1/providers/example-recovery/timeline', route => {
    profiles += 1
    return route.fulfill({ json: {
      provider: { provider_key: 'example-recovery', canonical_name: 'Example Recovery', status: null },
      events: [{ date: '2023-03-31', event_type: 'charity_accounts', label: 'Annual accounts', value_summary: 'Income £0' }],
      charity_finance: [{ financial_year_end: '2023-03-31', total_income: null }], cqc_locations: [], cqc_inspections: [],
      tribunal_cases: [{ case_number: 'ET-fixture', provider_match_basis: 'component' }],
      pfd_mentions: [{ report_ref: 'PFD-fixture', mention_type: 'named_in_text' }],
      disclosure: { gaps: [{ financial_year_end: '2022-03-31', topic: 'pay', search_terms: 'fixture' }], disclosed: [], not_searched: [{ financial_year_end: '2021-03-31', document_url: 'https://example.invalid/report' }], topics: ['pay'] },
    } })
  })
  await page.route('**/api/v1/providers/example-recovery/lineage', route => route.fulfill({ json: { identifiers: [{ scheme: 'charity_number', identifier: '1234567' }], edges: [], chain: [] } }))
  await page.route('**/api/v1/relationships?*', route => route.fulfill({ json: {
    center: { entity_id: 'graph-provider', canonical_name: 'Example Recovery' }, neighbours: [{ entity_id: 'graph-authority', canonical_name: 'Example Authority' }],
    edges: [{ relationship_id: 'relationship-fixture', subject_entity_id: 'graph-authority', object_entity_id: 'graph-provider', valid_from: '2024-01-01', valid_to: null, confidence: 'source_fact', source_url: 'https://example.invalid/notice' }],
  } }))
  await page.route('**/api/v1/contracts?*', route => {
    noticeQueries.push(new URL(route.request().url()).search)
    return route.fulfill({ json: { notices: [{ notice_id: 'fixture', title: 'Published notice', buyer_name: 'Example Authority', buyer_ons_code: 'E00000001', ocid: 'process-fixture', value_core: null }], total: 75 } })
  })
  await page.goto('/#/providers/example-recovery')
  await expect(page.getByRole('heading', { name: 'Evidence held', exact: true })).toBeVisible()
  await expect(page.getByText('Verified identifiers: charity_number 1234567', { exact: true })).toBeVisible()
  await expect(page.getByText('Active provider record', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('listitem').filter({ hasText: 'Company filing records' })).toContainText('Not supplied')
  const nav = page.getByRole('navigation', { name: 'Provider evidence views' })
  expect(noticeQueries).toEqual([])
  await nav.getByRole('link', { name: 'Finance and pay', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Reports not searched', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2021-03-31', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Employment tribunal cases', exact: true })).toHaveCount(0)
  await nav.getByRole('link', { name: 'Contracts', exact: true }).click()
  await expect(page.getByText('Showing 1 notices of 75 matching records.', { exact: false })).toBeVisible()
  expect(noticeQueries).toEqual(['?limit=50&provider_key=example-recovery'])
  await expect(page.getByRole('link', { name: 'Example Authority', exact: true })).toHaveAttribute('href', '#/authorities/E00000001')
  await nav.getByRole('link', { name: 'Connections', exact: true }).click()
  await page.getByText('Example Authority awarded to Example Recovery', { exact: true }).click()
  await expect(page.getByText('AWARDED_TO', { exact: true })).toBeVisible()
  await expect(page.locator('a[href="#/providers/graph-provider"]')).toHaveCount(0)
  await nav.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page).toHaveURL(/lens=history/)
  await expect(page.getByRole('heading', { name: 'Evidence timeline', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Income £0', exact: true })).toHaveCount(0)
  expect(profiles).toBe(1)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Evidence timeline', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'History', exact: true })).toHaveAttribute('aria-current', 'page')
  await nav.getByRole('link', { name: 'Overview', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Evidence held', exact: true })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('provider-overview-dark.png'), fullPage: true, animations: 'disabled' })
  await page.goto('/#/providers/example-recovery?lens=unknown')
  await expect(page.getByRole('link', { name: 'Open Overview', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Charity finance', exact: true })).toHaveCount(0)
})

test('authority profile renders a real offline boundary and keeps funding, context and date scope separate', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const manifest = JSON.parse(readFileSync(new URL('./fixtures/synthetic-boundaries.json', import.meta.url), 'utf8'))
  const archive = readFileSync(new URL('./fixtures/synthetic-boundaries.pmtiles', import.meta.url))
  let rangeReads = 0
  let profiles = 0
  const paymentQueries: string[] = []
  await page.route('**/map/boundaries.json', route => route.fulfill({ json: manifest }))
  await page.route('**/map/synthetic-boundaries.pmtiles', route => {
    const range = route.request().headers().range?.match(/^bytes=(\d+)-(\d+)$/)
    if (!range) throw new Error('The map must use bounded archive ranges')
    rangeReads += 1
    const start = Number(range[1]), end = Number(range[2])
    return route.fulfill({ status: 206, body: archive.subarray(start, end + 1), headers: { 'Content-Type': 'application/octet-stream', 'Content-Range': `bytes ${start}-${end}/${archive.length}` } })
  })
  await page.route('**/api/v1/authorities/E00000001', route => {
    profiles += 1
    return route.fulfill({ json: {
      authority: { ons_code: 'E00000001', name: 'Example Authority', type: 'Unitary authority', region: 'Example region' },
      coverage: { labels: ['Grant', 'Budget', 'Contracts'], cells: { Grant: 0, Contracts: 75 } },
      grant: { rows: [{ financial_year: '2024/25', grant_type: 'allocation', allocation_status: 'indicative', amount: 1000, unit: 'gbp', source_url: 'https://example.invalid/grant', payload_sha256: 'a'.repeat(64) }] },
      budget: { rows: [{ financial_year: '2024/25', amount: 900 }] },
      budget_detail: { rows: [{ financial_year: '2023/24', section: 'Older budget line', amount: null, value_text: '*' }, { financial_year: '2024/25', section: 'Recent budget line', amount: 900 }] },
      contracts: { total: 75, notices: [{ notice_id: 'notice-fixture', title: 'Authority notice', value_core: null, ocid: 'process-fixture' }] },
      comparators: { rough_sleeping: { rows: [{ snapshot_year: 2024, count: null, count_text: '*', source_url: 'https://example.invalid/rough' }] }, statutory_homelessness: { rows: [] }, temporary_accommodation: { rows: [{ quarter_label: '2024 Q4', total_households_ta: null, total_households_ta_text: '*', source_url: 'https://example.invalid/ta' }] } },
    } })
  })
  await page.route('**/api/v1/relationships?*', route => route.fulfill({ json: { center: { entity_id: 'authority-graph', canonical_name: 'Example Authority' }, neighbours: [], edges: [] } }))
  await page.route('**/api/v1/council_spend?*', route => {
    paymentQueries.push(new URL(route.request().url()).search)
    return route.fulfill({ json: { total: 125, payments: [{ period: 'August 2026', payee: 'Example payee', amount_text: '£250' }], files: [{ parse_status: 'unreadable', source_url: 'https://example.invalid/payments' }] } })
  })
  await page.goto('/#/authorities/E00000001')
  await expect(page.getByText('The selected authority boundary is outlined.', { exact: true })).toBeVisible()
  expect(rangeReads).toBeGreaterThan(0)
  const mapBox = await page.getByRole('region', { name: 'Authority boundary map' }).boundingBox()
  const connectionsBox = await page.getByRole('heading', { name: 'Commissioning connections', exact: true }).boundingBox()
  expect(mapBox!.y).toBeLessThan(connectionsBox!.y)
  await expect(page.getByRole('listitem').filter({ hasText: /^Budget/ })).toContainText('Not supplied')
  await expect(page.getByRole('listitem').filter({ hasText: /^Grant/ })).toContainText('0')
  expect(paymentQueries).toEqual([])
  await page.screenshot({ path: info.outputPath('authority-boundary-dark.png'), fullPage: true, animations: 'disabled' })
  const nav = page.getByRole('navigation', { name: 'Authority evidence views' })
  await nav.getByRole('link', { name: 'Funding', exact: true }).click()
  await expect(page.getByRole('cell', { name: 'Example payee', exact: true })).toBeVisible()
  expect(paymentQueries).toEqual(['?authority_ons_code=E00000001&limit=100'])
  await expect(page.getByText(/aggregated budget rows without row-level source URLs or hashes/)).toBeVisible()
  await page.getByRole('combobox', { name: 'Financial year', exact: true }).selectOption('2023/24')
  await expect(page).toHaveURL(/budget_year=2023(?:%2F|\/)24/)
  await expect(page.getByRole('cell', { name: 'Older budget line', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Recent budget line', exact: true })).toHaveCount(0)
  const grantTable = page.getByRole('region', { name: 'Public health grant allocations', exact: true })
  await grantTable.getByText('Source details', { exact: true }).click()
  await expect(grantTable.getByText('a'.repeat(64), { exact: true })).toBeVisible()
  await nav.getByRole('link', { name: 'Contracts', exact: true }).click()
  await expect(page.getByText(/1 notices returned of 75 matching records/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Explore matching notices', exact: true })).toHaveAttribute('href', '#/contracts?buyer_ons_code=E00000001')
  await nav.getByRole('link', { name: 'Context', exact: true }).click()
  await expect(page.getByText(/estimation method for each observation is not supplied/)).toBeVisible()
  await expect(page.getByRole('region', { name: 'Temporary accommodation observations', exact: true }).getByRole('cell', { name: '*', exact: true })).toBeVisible()
  expect(profiles).toBe(1)
  await nav.getByRole('link', { name: 'Funding', exact: true }).click()
  await expect(page.getByRole('cell', { name: 'Older budget line', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Financial year', exact: true })).toHaveValue('2023/24')
})

test('Places keeps a neutral start, routes all eight layers correctly and preserves unambiguous map state', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const keys = ['grant_drug_alcohol', 'grant_total', 'grant_per_head', 'budget_public_health', 'treatment_numbers', 'contract_value', 'cqc_locations', 'coverage']
  const labels: Record<string, string> = { grant_drug_alcohol: 'Public health grant ring-fenced for drug and alcohol treatment', grant_total: 'Public health grant allocation, total' }
  await page.route('**/api/v1/atlas_layers', route => route.fulfill({ json: { layers: keys.map(key => ({ key, label: labels[key] ?? key, kind: key === 'cqc_locations' ? 'points' : key === 'coverage' ? 'authority' : 'choropleth', unit: key === 'coverage' ? 'count of evidence kinds held' : 'fixture unit', legend: 'Synthetic layer definition', caveat: 'Synthetic layer caveat' })) } }))
  const requests: string[] = []
  await page.route('**/api/v1/geography?*', route => {
    const url = new URL(route.request().url())
    requests.push(url.search)
    const metric = url.searchParams.get('metric')
    const year = url.searchParams.get('year') ?? '2024/25'
    return route.fulfill({ json: { metric, metric_label: metric, year: metric === 'contract_value' ? null : year, unit: 'fixture unit', available_years: metric === 'contract_value' ? [] : ['2024/25', '2023/24'], features: metric === 'treatment_numbers' ? [{ ons_code: 'E00000001', authority_name: 'Example Authority', value: 12 }, { ons_code: 'E00000001', authority_name: 'Example Authority', value: 14 }] : [{ ons_code: 'E00000001', authority_name: 'Example Authority', value: year === '2023/24' ? null : 0, financial_year: year }] } })
  })
  let layerCalls = 0
  await page.route('**/api/v1/layers', route => {
    layerCalls += 1
    return route.fulfill({ json: { layers: { coverage: { features: [{ ons_code: 'E00000001', authority_name: 'Example Authority', kinds_held: 3 }], caveats: ['Coverage is not evidence quality.'] }, cqc_locations: { features: [{ location_id: 'cqc-fixture', location_name: 'Example registration', latitude: 52.5, longitude: -1.5, ons_code: 'E00000001', overall_rating: 'Good' }], caveats: ['Registration is not service coverage.'] } } } })
  })
  await page.route('**/api/v1/authorities/E00000001', route => route.fulfill({ json: { authority: { ons_code: 'E00000001', name: 'Example Authority' }, coverage: { cells: { Grant: 0 } } } }))
  const manifest = JSON.parse(readFileSync(new URL('./fixtures/synthetic-boundaries.json', import.meta.url), 'utf8'))
  const archive = readFileSync(new URL('./fixtures/synthetic-boundaries.pmtiles', import.meta.url))
  await page.route('**/map/boundaries.json', route => route.fulfill({ json: manifest }))
  await page.route('**/map/synthetic-boundaries.pmtiles', route => {
    const range = route.request().headers().range!.match(/bytes=(\d+)-(\d+)/)!
    return route.fulfill({ status: 206, body: archive.subarray(Number(range[1]), Number(range[2]) + 1), contentType: 'application/octet-stream' })
  })
  await page.goto('/#/geography')
  await expect(page.getByRole('combobox', { name: 'Evidence layer' })).toHaveValue('')
  await expect(page.getByRole('link', { name: 'Example Authority', exact: true })).toBeVisible()
  expect(requests).toEqual([])
  expect(layerCalls).toBe(0)
  const layerSelect = page.getByRole('combobox', { name: 'Evidence layer' })
  await expect(layerSelect.locator('option')).toHaveCount(9)
  for (const key of keys) {
    await layerSelect.selectOption(key)
    await expect(page.getByText('Preview only. Select Show layer to apply this choice.', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Show layer', exact: true }).click()
    await expect(page.getByText(`Active layer: ${labels[key] ?? key}`, { exact: true })).toBeVisible()
    if (key === 'cqc_locations') {
      await expect(page.getByText('Example registration', { exact: true })).toBeVisible()
      await expect.poll(async () => { await page.locator('.st-map-canvas').click(); return page.url() }).toContain('location_id=cqc-fixture')
      await expect(page.getByRole('complementary', { name: 'Example registration' })).toBeVisible()
      await expect(page.getByText('Rating origin and source dates are not supplied by this map response.', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Close', exact: true }).click()
    } else if (key === 'treatment_numbers') {
      await expect(page.getByText('1 authorities have multiple returned observations.', { exact: false })).toBeVisible()
      await expect(page.getByText('Multiple observations, no map value selected', { exact: true })).toBeVisible()
    } else if (key !== 'coverage') {
      await expect.poll(() => requests.some(query => query.includes(`metric=${key}`))).toBe(true)
      await expect(page.getByText('No observation returned', { exact: true })).toHaveCount(0)
    } else await expect(page.getByText('3 · Period not supplied', { exact: true })).toBeVisible()
  }
  expect(requests.some(query => /metric=(coverage|cqc_locations)/.test(query))).toBe(false)
  expect(layerCalls).toBe(2)
  await layerSelect.selectOption('grant_total')
  await page.getByRole('button', { name: 'Show layer', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Source period' })).toBeVisible()
  const canvas = page.getByRole('region', { name: labels.grant_total, exact: true })
  const box = await canvas.boundingBox()
  const clip = { x: box!.x + box!.width / 2 - 10, y: box!.y + box!.height / 2 - 10, width: 20, height: 20 }
  const zeroColour = await page.screenshot({ clip })
  await page.getByRole('combobox', { name: 'Source period' }).selectOption('2023/24')
  await expect(page.getByText('Missing value · 2023/24', { exact: true })).toBeVisible()
  await expect.poll(async () => (await page.screenshot({ clip })).equals(zeroColour)).toBe(false)
  const beforeLocal = requests.length
  await page.getByRole('searchbox', { name: 'Find an authority' }).fill('Example')
  await page.getByRole('button', { name: 'Inspect Example Authority' }).click()
  await expect(page.getByRole('complementary', { name: 'Example Authority', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/view=table/)
  await expect(page.getByRole('button', { name: 'Data', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('link', { name: 'Open profile', exact: true })).toBeVisible()
  expect(requests.length).toBe(beforeLocal)
  await page.reload()
  await expect(page.getByRole('complementary', { name: 'Example Authority', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Source period' })).toHaveValue('2023/24')
  await expect(page.locator('.st-map-canvas')).toHaveCount(0)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('places-data-inspector-dark.png'), fullPage: true, animations: 'disabled' })
  await page.setViewportSize({ width: 390, height: 844 })
  const dialog = page.getByRole('dialog', { name: 'Example Authority', exact: true })
  await expect(dialog).toBeVisible()
  await expect.poll(async () => (await dialog.boundingBox())?.x).toBe(0)
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('places-mobile.png'), fullPage: true, animations: 'disabled' })
})

test('a homepage boundary click opens its exact authority without navigating away', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const manifest = JSON.parse(readFileSync(new URL('./fixtures/synthetic-boundaries.json', import.meta.url), 'utf8'))
  const archive = readFileSync(new URL('./fixtures/synthetic-boundaries.pmtiles', import.meta.url))
  await page.route('**/map/boundaries.json', route => route.fulfill({ json: manifest }))
  await page.route('**/map/synthetic-boundaries.pmtiles', route => {
    const range = route.request().headers().range!.match(/bytes=(\d+)-(\d+)/)!
    return route.fulfill({ status: 206, body: archive.subarray(Number(range[1]), Number(range[2]) + 1), contentType: 'application/octet-stream' })
  })
  await page.route('**/api/v1/authorities/E00000001', route => route.fulfill({ json: { authority: { ons_code: 'E00000001', name: 'Example Authority' }, coverage: { cells: { Grant: 0 } } } }))
  await page.goto('/')
  const map = page.getByRole('region', { name: 'Authority boundary map' })
  await expect(map.locator('canvas')).toBeVisible()
  await expect.poll(async () => { await map.click(); return page.url() }).toContain('inspect=E00000001')
  await expect(page.getByRole('complementary', { name: 'Example Authority', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Find sector evidence', exact: true })).toBeVisible()
})

test('CQC filters preserve exact result windows and registration provenance', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  let stale = false
  const activity = 'Treatment of disease, disorder or injury'
  await page.route('**/api/v1/cqc_locations*', route => {
    const url = new URL(route.request().url())
    requests.push(url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const prefix = offset ? 'Later' : 'Example'
    const rows = [
      { location_id: 'cqc-exact', location_name: `${prefix} Registration`, provider_key: 'example-recovery', provider_name: 'Example Recovery', provider_id: 'cqc-provider-1', local_authority_raw: 'Example Authority', local_authority_ons_code: 'E00000001', registration_status: 'Registered', overall_rating: 'Good', rating_source: 'bulk_export', overall_rating_date: '2024-06-12', registration_date: '2020-01-02', last_inspection_date: '2024-05-03', regulated_activities: activity, service_types: 'Rehabilitation services', latitude: 52.5, longitude: -1.5, source_url: 'https://example.invalid/cqc/source', retrieved_at: '2026-08-01T12:00:00Z' },
      { location_id: 'cqc-missing', location_name: 'Missing Coordinate Registration', provider_key: 'example-recovery', provider_name: 'Example Recovery', registration_status: 'Registered', overall_rating: null, latitude: null, longitude: null },
      { location_id: 'cqc-invalid', location_name: 'Invalid Coordinate Registration', provider_key: 'example-recovery', provider_name: 'Example Recovery', registration_status: 'Registered', overall_rating: 'Good', rating_source: 'api', latitude: 200, longitude: -1.5 },
    ]
    return route.fulfill({ json: { results: stale ? rows.slice(1) : rows, total: 203, without_coordinate: 70, limit: 100, offset, caveat: 'Synthetic registration records.', facets: { registration_status: [{ value: 'Registered', count: 240 }], overall_rating: [{ value: 'Good', count: 180 }], service_type: [{ value: 'Rehabilitation services', count: 220 }], region: [{ value: 'Example region', count: 230 }] } } })
  })
  await page.goto('/#/cqc?offset=100')
  await expect(page.getByRole('heading', { name: 'CQC registrations', exact: true })).toBeVisible()
  await expect(page.getByText('Matching registrations: 203 · Loaded records: 3 · Mapped records: 1')).toBeVisible()
  await expect(page.getByText('70 matching registrations have a missing coordinate across all matching pages.')).toBeVisible()
  await expect(page.locator('.st-map-canvas')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Provider', exact: true }).selectOption('example-recovery')
  await expect(page.getByRole('heading', { name: 'Example Registration', exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/offset=100/)
  await page.getByRole('combobox', { name: 'Authority', exact: true }).selectOption('E00000001')
  await page.getByRole('searchbox', { name: 'Regulated activity contains' }).fill(activity)
  await page.getByRole('searchbox', { name: 'Regulated activity contains' }).press('Tab')
  await page.getByRole('combobox', { name: 'Registration status', exact: true }).selectOption('Registered')
  await page.getByRole('combobox', { name: 'Overall rating', exact: true }).selectOption('Good')
  await page.getByRole('combobox', { name: 'Service type', exact: true }).selectOption('Rehabilitation services')
  await expect(page.getByRole('button', { name: 'Inspect Example Registration', exact: true })).toBeVisible()
  await expect.poll(() => Object.fromEntries(requests.at(-1)!.searchParams)).toEqual({ provider_key: 'example-recovery', authority_ons_code: 'E00000001', registration_status: 'Registered', regulated_activity: activity, service_type: 'Rehabilitation services', rating: 'Good', limit: '100', offset: '0' })
  await expect(page.getByRole('combobox', { name: 'Overall rating', exact: true }).locator('option:checked')).toHaveText('Good (180)')
  await expect(page.getByRole('combobox', { name: 'Region', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Inspect Later Registration' })).toBeVisible()
  const beforeLocal = requests.length
  await page.getByRole('button', { name: 'Inspect Later Registration' }).click()
  const inspector = page.getByRole('complementary', { name: 'Later Registration', exact: true })
  await expect(inspector).toBeVisible()
  await expect(inspector.getByRole('heading', { name: 'Later Registration' })).toBeFocused()
  await expect(inspector.getByText(activity, { exact: true })).toHaveCount(1)
  await expect(inspector.getByText('CQC bulk export', { exact: true })).toBeVisible()
  await expect(inspector.getByText('2024-06-12', { exact: true })).toBeVisible()
  await inspector.getByText('Source details', { exact: true }).click()
  await expect(inspector.getByText('2026-08-01T12:00:00Z', { exact: true })).toBeVisible()
  await expect(inspector.getByRole('link', { name: 'Open provider profile' })).toHaveAttribute('href', /providers\/example-recovery/)
  await inspector.getByRole('button', { name: 'Save registration' }).click()
  await expect(inspector.getByText('Registration saved to this browser’s notebook.')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('st.notebook'))).toContain('location_id=cqc-exact')
  await page.getByRole('button', { name: 'Map', exact: true }).click()
  await expect(page.getByText('Map could not load. Use the registration list to continue.')).toBeVisible()
  expect(requests.length).toBe(beforeLocal)
  await page.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/view=data/)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('cqc-inspector-dark.png'), fullPage: true, animations: 'disabled' })
  await inspector.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Inspect Later Registration' })).toBeFocused()
  await page.getByRole('button', { name: 'Inspect Later Registration' }).click()
  await expect(page).toHaveURL(/location_id=cqc-exact/)
  await page.reload()
  await expect(inspector).toBeVisible()
  await expect(page).toHaveURL(/offset=100/)
  await page.setViewportSize({ width: 390, height: 844 })
  const dialog = page.getByRole('dialog', { name: 'Later Registration', exact: true })
  await expect(dialog).toBeVisible()
  await expect.poll(async () => (await dialog.boundingBox())?.x).toBe(0)
  await page.screenshot({ path: info.outputPath('cqc-inspector-mobile.png'), animations: 'disabled' })
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('cqc-mobile.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: 'Inspect Later Registration' }).click()
  await expect(page).toHaveURL(/location_id=cqc-exact/)
  stale = true
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Registration not in this result window' })).toBeVisible()
  await expect(page.getByText('No replacement record has been selected.', { exact: false })).toBeVisible()
  await expect(page).toHaveURL(/location_id=cqc-exact/)
  expect(requests.every(url => !url.searchParams.has('location_id') && !url.searchParams.has('view'))).toBe(true)
})

test('CQC failed and empty windows retain the exact selected identifier', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  let fail = true
  let count = 0
  await page.route('**/api/v1/cqc_locations*', route => {
    count++
    return fail ? route.fulfill({ status: 503, json: { error: 'Synthetic failure' } }) : route.fulfill({ json: { results: [], total: 0, without_coordinate: 0, limit: 100, offset: 100, facets: {}, caveat: null } })
  })
  await page.goto('/#/cqc?offset=100&location_id=absent')
  await expect(page.getByRole('heading', { name: 'Evidence is unavailable' })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Registration unavailable' })).toBeVisible()
  fail = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No records in this result window' })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Registration not in this result window' })).toBeVisible()
  expect(count).toBe(2)
  await expect(page).toHaveURL(/location_id=absent/)
})

test('CQC maps only located records in the loaded page and opens the exact point', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  let requests = 0
  const manifest = JSON.parse(readFileSync(new URL('./fixtures/synthetic-boundaries.json', import.meta.url), 'utf8'))
  const archive = readFileSync(new URL('./fixtures/synthetic-boundaries.pmtiles', import.meta.url))
  await page.route('**/map/boundaries.json', route => route.fulfill({ json: manifest }))
  await page.route('**/map/synthetic-boundaries.pmtiles', route => {
    const range = route.request().headers().range!.match(/bytes=(\d+)-(\d+)/)!
    return route.fulfill({ status: 206, body: archive.subarray(Number(range[1]), Number(range[2]) + 1), contentType: 'application/octet-stream' })
  })
  await page.route('**/api/v1/cqc_locations*', route => {
    requests++
    return route.fulfill({ json: { results: [
      { location_id: 'point-1', location_name: 'Located Registration', latitude: 52.5, longitude: -1.5, overall_rating: 'Good', rating_source: 'api', provider_key: 'example-recovery', provider_name: 'Example Recovery' },
      { location_id: 'point-2', location_name: 'Unlocated Registration', latitude: null, longitude: null },
    ], total: 900, limit: 100, offset: 0, without_coordinate: 300, facets: {}, caveat: null } })
  })
  await page.goto('/#/cqc?view=map')
  await expect(page.getByText('Matching registrations: 900 · Loaded records: 2 · Mapped records: 1')).toBeVisible()
  const map = page.getByRole('region', { name: 'Loaded CQC registration locations' })
  await expect(map.locator('canvas')).toBeVisible()
  await expect.poll(async () => { await map.click(); return page.url() }).toContain('location_id=point-1')
  await expect(page.getByRole('complementary', { name: 'Located Registration', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Inspect Unlocated Registration' }).click()
  await expect(page.getByRole('complementary', { name: 'Unlocated Registration', exact: true })).toBeVisible()
  expect(requests).toBe(1)
  await page.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/view=data/)
  await expect(page.locator('.st-map-canvas')).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Loaded registrations' }).getByRole('listitem')).toHaveCount(2)
})
