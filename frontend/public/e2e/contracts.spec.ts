import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const provider = { provider_key: 'example-recovery', canonical_name: 'Example Recovery' }
const authority = { ons_code: 'E00000001', name: 'Example Authority' }
const hash = 'd'.repeat(64)
const notice = { notice_id: 'N1', title: 'Synthetic treatment procurement', buyer_name: 'Example Authority', buyer_ons_code: 'E00000001', supplier_name_raw: 'Example Recovery', value_core: 0, value_max: 1200, currency: 'GBP', date_published: '2025-02-03', date_start: '2025-04-01', date_end: '2027-03-31', procedure_type: 'Open', ocid: 'ocds-example', source_url: 'https://example.invalid/ocds/source', retrieved_at: '2026-08-01T12:00:00Z', payload_sha256: hash, notice_link: 'https://example.invalid/notice/N1', notice_link_basis: 'constructed' }

test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://localhost:4173') throw new Error(`Unexpected external request: ${url.origin}`)
    if (url.pathname === '/api/v1/providers') return route.fulfill({ json: { providers: [provider] } })
    if (url.pathname === '/api/v1/authorities') return route.fulfill({ json: { authorities: [authority] } })
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/map/')) return route.fulfill({ status: 503, json: { error: 'No fixture for this request' } })
    return route.continue()
  })
})

test('procurement notices preserve source rows, filters, process pivots and export scope', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  let payments = 0
  await page.route('**/api/v1/council_spend*', route => { payments++; return route.fulfill({ json: { payments: [], files: [], total: 0 } }) })
  await page.route('**/api/v1/contracts?*', route => {
    const url = new URL(route.request().url()); requests.push(url)
    const offset = Number(url.searchParams.get('offset'))
    const rows = offset ? [{ ...notice, notice_id: 'N2', title: 'Later notice', supplier_name_raw: null }] : [notice, { ...notice, supplier_name_raw: 'Second named supplier' }]
    return route.fulfill({ json: { notices: rows, total: 325, total_value_gbp: 999999999999, value_concentration: { top_10_share: 94 }, page: { limit: 2, offset, returned: rows.length }, by_year: [{ year: '2025', count: 325 }], caveats: { value: 'Synthetic notice values are not payments.' } } })
  })
  await page.route('**/api/v1/contracts/process/ocds-example', route => route.fulfill({ json: { ocid: 'ocds-example', notice_count: 3, buyer: { name: authority.name, ons_code: authority.ons_code }, stages: [
    { stage: 'planning', present: false, notices: [] },
    { stage: 'tender', present: true, notices: [{ ...notice, payload_sha256: undefined, notice_link: undefined, notice_link_basis: undefined, notice_type_raw: 'tenderCancellation', ocds_tags: ['tenderCancellation'], notice_web_url: 'https://example.invalid/notice/N1', suppliers: [{ name: 'Example Recovery', is_tracked_provider: true }] }] },
    { stage: 'amendment', present: true, notices: [{ ...notice, notice_id: 'N2', title: 'Published amendment', date_published: '2025-03-01', notice_type_raw: 'contractAmendment' }] },
    { stage: 'other', present: true, notices: [{ ...notice, notice_id: 'N3', title: 'Undated record', date_published: null, notice_type_raw: null }] },
  ], caveat: 'This is one procurement process, not three separate awards.' } }))
  await page.goto('/#/contracts?provider_key=example-recovery&buyer_ons_code=E00000001&year_from=2024&year_to=2026&since_retrieved_at=2026-01-01&psr_only=true&q=Recovery&limit=2')
  await expect(page.getByRole('heading', { name: 'Published notices', exact: true })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toMatchObject({ provider_key: provider.provider_key, buyer_ons_code: authority.ons_code, year_from: '2024', year_to: '2026', q: 'Recovery', psr_only: 'true', since_retrieved_at: '2026-01-01', limit: '2', offset: '0' })
  expect(payments).toBe(0)
  await expect(page.getByText('999,999,999,999', { exact: false })).toHaveCount(0)
  await expect(page.getByText('Money-flow snapshot')).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Returned notice rows' }).getByRole('listitem')).toHaveCount(2)
  await expect(page.getByText('Published value: 0 GBP', { exact: true })).toHaveCount(2)
  const fullHref = await page.getByRole('link', { name: 'Download all matching notice rows CSV' }).getAttribute('href')
  const exportQuery = new URL(fullHref!, 'http://localhost:4173').searchParams
  expect(exportQuery.get('q')).toBe('Recovery'); expect(exportQuery.has('offset')).toBe(false); expect(exportQuery.has('limit')).toBe(false)
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download returned page JSON' }).click()
  const file = await downloaded
  const json = JSON.parse(readFileSync((await file.path())!, 'utf8'))
  expect(json.rows).toHaveLength(2); expect(json._provenance.scope).toBe('returned-page'); expect(json._provenance.total_matching).toBe(325); expect(json.rows[0].payload_sha256).toBe(hash)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Later notice', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Provider', exact: true }).selectOption('')
  await expect(page).not.toHaveURL(/offset=2/)
  await expect(page.getByRole('button', { name: 'Inspect notice N1 for Example Recovery', exact: true })).toBeVisible()
  const beforeInspect = requests.length
  await page.getByRole('button', { name: 'Inspect notice N1 for Example Recovery', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: notice.title, exact: true })
  await expect(inspector).toBeVisible()
  await expect(inspector.getByText('2 returned rows share this notice identifier.', { exact: false })).toBeVisible()
  await inspector.getByText('Source details', { exact: true }).first().click()
  await expect(inspector.getByText(hash, { exact: true }).first()).toBeVisible()
  await expect(inspector.getByText('Notice link basis: constructed from the notice identifier.', { exact: false })).toHaveCount(2)
  expect(requests.length).toBe(beforeInspect)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('notices-inspector-dark.png'), fullPage: true, animations: 'disabled' })
  await inspector.getByRole('link', { name: 'Open procurement process' }).first().click()
  await expect(page.getByRole('heading', { name: 'Procurement lifecycle', exact: true })).toBeVisible()
  await expect(page.getByText('No notice is held for this stage.', { exact: false })).toBeVisible()
  await expect(page.getByRole('complementary', { name: notice.title, exact: true })).toBeVisible()
  await expect(page.getByText('The process response does not supply a payload hash.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Publication timeline', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'No usable publication date' })).toBeVisible()
  await expect(page.locator('.st-process-timeline li')).toHaveCount(2)
  await expect(page.getByText('Amendment · contractAmendment', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Publication timeline' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('link', { name: 'Return to source view' }).click()
  await expect(page).toHaveURL(/notice_id=N1/)
  await expect(page.getByRole('searchbox', { name: 'Search buyer or supplier name' })).toHaveValue('Recovery')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('dialog', { name: notice.title, exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('notice-mobile.png'), animations: 'disabled' })
})

test('payment response keeps file scope, source amounts and local selection distinct', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const requests: URL[] = []
  await page.route('**/api/v1/council_spend*', route => {
    requests.push(new URL(route.request().url()))
    return route.fulfill({ json: { total: 602, payments: [
      { file_url: 'https://example.invalid/files/a.csv', row_index: 4, payee: 'Example Recovery', amount_text: '£1,234 (adjusted)', amount: null, period: 'April / correction', description: 'Published correction', provider_key: provider.provider_key, canonical_name: provider.canonical_name, authority_ons_code: authority.ons_code, authority_name: authority.name, source_url: 'https://example.invalid/files/a.csv', retrieved_at: '2026-01-02', payload_sha256: hash },
      { file_url: 'https://example.invalid/files/b.csv', row_index: 4, payee: 'Different supplier', amount_text: '0', amount: 0, period: 'April', description: null },
    ], files: [{ file_url: 'https://example.invalid/files/a.csv', authority_name: authority.name, file_format: 'CSV', parse_status: 'parsed', row_count: 4, source_url: 'https://example.invalid/files/a.csv', payload_sha256: hash }, { file_url: 'https://example.invalid/files/unreadable.xlsx', authority_name: authority.name, parse_status: 'failed', row_count: null }], caveats: { payments: 'Payment lines are never summed across files.' } } })
  })
  await page.goto('/#/contracts?lens=payments&provider_key=example-recovery&buyer_ons_code=E00000001&year_from=2020&q=Recovery&offset=100')
  await expect(page.getByRole('heading', { name: 'Published council payments' })).toBeVisible()
  expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({ provider_key: provider.provider_key, authority_ons_code: authority.ons_code, limit: '500' })
  await expect(page.getByText('Notice search, date and pagination selections are retained', { exact: false })).toBeVisible()
  await expect(page.getByText('File coverage is filtered by authority only.', { exact: false })).toBeVisible()
  await expect(page.getByText('failed', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Inspect payment 4 in https://example.invalid/files/a.csv', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Example Recovery', exact: true })
  await expect(inspector).toBeVisible()
  await expect(inspector.getByText('£1,234 (adjusted)', { exact: true })).toBeVisible()
  await expect(inspector.locator('.st-payment-details dd').nth(4)).toHaveText('Not supplied')
  await expect(page).toHaveURL(/payment_authority=E00000001/)
  await inspector.getByRole('button', { name: 'Save payment reference' }).click()
  await expect(inspector.getByText('Payment reference saved to this browser’s notebook.')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('st.notebook'))).toContain('£1,234 (adjusted)')
  await page.getByRole('searchbox', { name: 'Search returned payees, descriptions or periods' }).fill('Different')
  await page.getByRole('searchbox', { name: 'Search returned payees, descriptions or periods' }).press('Tab')
  await expect(page.getByRole('list', { name: 'Returned payment lines' }).getByRole('listitem')).toHaveCount(1)
  await expect(inspector).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download visible payment rows JSON' }).click()
  const file = await downloaded; const json = JSON.parse(readFileSync((await file.path())!, 'utf8'))
  expect(json.rows).toHaveLength(1); expect(json.rows[0].file_url).toBe('https://example.invalid/files/b.csv'); expect(json.rows[0].amount).toBe(0); expect(json._provenance.total_matching).toBe(602); expect(json._provenance.scope).toBe('local-selection-of-returned-response')
  expect(requests).toHaveLength(1)
  await page.reload()
  await expect(inspector).toBeVisible()
  await expect(page.getByRole('list', { name: 'Returned payment lines' }).getByRole('listitem')).toHaveCount(1)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('payments-dark.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('combobox', { name: 'Paying authority', exact: true }).selectOption('')
  await expect.poll(() => requests.at(-1)?.searchParams.has('authority_ons_code')).toBe(false)
  await expect(page.getByRole('combobox', { name: 'Paying authority', exact: true })).toHaveValue('')
})

test('notice patterns use returned aggregates, safe SVG text and supported year selection', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const policy = document.createElement('meta')
      policy.httpEquiv = 'Content-Security-Policy'
      policy.content = "img-src 'self' data:"
      document.head.append(policy)
    })
  })
  const requests: URL[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/v1/contracts?*', route => {
    requests.push(new URL(route.request().url()))
    return route.fulfill({ json: { notices: [notice], total: 80, page: { limit: 100, offset: 0, returned: 1 }, by_year: [{ year: '2023', count: 0 }, { year: '2024', count: 40 }, { year: '2025', count: 40 }], by_quarter: [{ quarter: '2025-Q1', count: 7 }], by_procedure_type: [{ procedure_type: 'Open <img src=x onerror=alert(1)>', count: 5 }, { procedure_type: 'Not stated', count: 75 }], value_bands: [{ band_label: 'Under £100k', count: 0 }, { band_label: '£100k and above', count: 78 }], caveats: { value: 'Notice values are not payments.', window: 'Synthetic publication window.' } } })
  })
  await page.goto('/#/contracts')
  await expect(page.getByRole('heading', { name: 'Published notices', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Patterns', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Published notice patterns' })).toBeVisible()
  expect(requests).toHaveLength(1)
  await expect(page.getByRole('region', { name: 'Notice count data' }).getByRole('cell', { name: '40', exact: true })).toHaveCount(2)
  await page.getByRole('button', { name: 'Chart', exact: true }).click()
  const chart = page.getByRole('img', { name: 'Notices by publication year.', exact: false })
  await expect(chart.locator('svg')).toBeVisible()
  await page.getByRole('button', { name: 'Inspect aggregate 2023', exact: true }).click()
  await expect(page.getByText('Published notices: 0.', { exact: false })).toBeVisible()
  expect(requests).toHaveLength(1)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download annotated chart SVG' }).click()
  const svg = readFileSync((await (await download).path())!, 'utf8')
  const svgText = await page.evaluate(value => Array.from(new DOMParser().parseFromString(value, 'image/svg+xml').querySelectorAll('text')).map(node => node.textContent).join(' '), svg)
  expect(svgText).toContain('Notices by publication year')
  expect(svgText).toContain('published notice counts, not awards')
  expect(svgText).toContain('Synthetic publication window.')
  const pngDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download annotated chart PNG' }).click()
  const pngFile = await pngDownload
  await pngFile.saveAs(info.outputPath('notice-counts-annotated.png'))
  const png = readFileSync((await pngFile.path())!)
  expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
  expect(png.readUInt32BE(16)).toBeGreaterThanOrEqual(1280)
  await page.getByRole('button', { name: 'Select year range on chart' }).click()
  const box = (await chart.boundingBox())!
  const plotWidth = box.width - 90
  await page.mouse.move(box.x + 60 + plotWidth / 3 + 5, box.y + 140)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width - 35, box.y + 220, { steps: 12 })
  await page.mouse.up()
  await expect.poll(() => requests.at(-1)?.searchParams.get('year_from')).toBe('2024')
  await expect.poll(() => requests.at(-1)?.searchParams.get('year_to')).toBe('2025')
  await expect(page.getByRole('textbox', { name: 'Publication year from', exact: true })).toHaveValue('2024')
  const beforeLocal = requests.length
  await page.getByRole('combobox', { name: 'Count notices by' }).selectOption('procedure')
  await expect(page.getByRole('img', { name: 'Notices by procedure.', exact: false }).locator('svg')).toBeVisible()
  await page.getByRole('button', { name: 'Inspect aggregate Open <img src=x onerror=alert(1)>', exact: true }).click()
  await expect(page.getByText('The notice list has not been filtered by this selection.', { exact: true })).toBeVisible()
  await expect(page.locator('main img')).toHaveCount(0)
  expect(requests).toHaveLength(beforeLocal)
  await page.getByRole('combobox', { name: 'Count notices by' }).selectOption('band')
  await expect(page.getByRole('button', { name: 'Inspect aggregate Under £100k' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Notice count data' }).getByRole('cell', { name: '0', exact: true })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('notice-patterns-dark.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('combobox', { name: 'Colour theme' }).selectOption('light')
  await page.screenshot({ path: info.outputPath('notice-patterns-light.png'), fullPage: true, animations: 'disabled' })
  await page.getByRole('combobox', { name: 'Count notices by' }).selectOption('quarter')
  await page.getByRole('button', { name: 'Inspect aggregate 2025-Q1', exact: true }).click()
  expect(requests).toHaveLength(beforeLocal)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Data', exact: true }).click()
  await expect(page).toHaveURL(/pattern_view=data/)
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Count notices by' })).toHaveValue('quarter')
  await expect(page.getByText('Published notices: 7.', { exact: false })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('a payment selection needs the authority when file and row are shared', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  let requests = 0
  const file = 'https://example.invalid/shared.csv'
  await page.route('**/api/v1/council_spend*', route => {
    requests++
    return route.fulfill({ json: { total: 2, payments: [
      { authority_ons_code: 'E00000001', authority_name: 'First authority', file_url: file, row_index: 4, payee: 'First payee', amount_text: '100' },
      { authority_ons_code: 'E00000002', authority_name: 'Second authority', file_url: file, row_index: 4, payee: 'Second payee', amount_text: '200' },
    ], files: [], caveats: {} } })
  })
  await page.goto(`/#/contracts?${new URLSearchParams({ lens: 'payments', file_url: file, row_index: '4' })}`)
  await expect(page.getByRole('complementary', { name: 'Payment not in this response' })).toBeVisible()
  await expect(page.getByText('The record may be absent or ambiguous.', { exact: false })).toBeVisible()
  const secondRow = page.getByRole('list', { name: 'Returned payment lines' }).getByRole('listitem').filter({ hasText: 'Second payee' })
  await secondRow.getByRole('button').click()
  await expect(page).toHaveURL(/payment_authority=E00000002/)
  const inspector = page.getByRole('complementary', { name: 'Second payee', exact: true })
  await expect(inspector).toBeVisible()
  await expect(inspector.getByText('200', { exact: true })).toBeVisible()
  expect(requests).toBe(1)
  await page.reload()
  await expect(inspector).toBeVisible()
  await expect(inspector.getByText('Second authority', { exact: true })).toBeVisible()
})
