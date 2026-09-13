import { expect, test } from '@playwright/test'

const observation = {
  quarter_start: '2026-01-01', quarter_label: 'January to March 2026',
  md_pct: 125.5, md_pct_text: '125.5%',
  assessed_md_total: 10, assessed_md_total_text: '10',
  assessed_substance_dependency_total: null, assessed_substance_dependency_total_text: '[x]',
  prevention_secured_md_total: 0, prevention_secured_md_total_text: '0',
  relief_secured_md_total: null, relief_secured_md_total_text: '[z]',
  source_url: 'https://example.invalid/md.xlsx',
  retrieved_at: '2026-09-12T00:00:00Z', payload_sha256: 'md-fixture-hash',
}

for (const width of [1440, 375]) {
  test('multiple disadvantage preserves published text at width ' + width, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 })
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => {
      const url = new URL(route.request().url())
      if (url.origin !== 'http://localhost:4173') throw new Error('Unexpected external request')
      if (url.pathname === '/api/v1/authorities/E08000025') return route.fulfill({ json: {
        authority: { ons_code: 'E08000025', name: 'Example Authority' },
        comparators: { multiple_disadvantage: { rows: [observation], caveat: 'Source-specific fixture caveat.' } },
      } })
      if (url.pathname.startsWith('/api/')) return route.fulfill({ json: {} })
      return route.continue()
    })
    await page.goto('/#/authorities/E08000025?lens=context')
    const card = page.getByRole('heading', { name: 'Multiple disadvantage', exact: true }).locator('..')
    await expect(card).toBeVisible()
    await expect(page.locator('#comparators h3')).toHaveText(['Rough sleeping', 'Statutory homelessness', 'Temporary accommodation', 'Multiple disadvantage'])
    const table = card.getByRole('table', { name: 'Multiple disadvantage observations', exact: true })
    await expect(table).toContainText('125.5%')
    await expect(table).toContainText('[z]')
    await expect(table.getByRole('cell', { name: '0', exact: true })).toBeVisible()
    await expect(card).toContainText('five category totals overlap')
    await expect(card).toContainText('not treatment episodes or diagnoses')
    await card.locator('summary').filter({ hasText: 'Published categories by duty stage' }).click()
    await expect(card.getByRole('table', { name: 'Assessed as owed a duty', exact: true })).toContainText('[x]')
    await expect(card).toContainText('Source-specific fixture caveat.')
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await card.screenshot({ path: info.outputPath('multiple-disadvantage.png') })
    expect(errors).toEqual([])
  })
}

for (const rows of [[], undefined]) {
  test('multiple disadvantage distinguishes ' + (rows ? 'empty' : 'missing') + ' data', async ({ page }) => {
    await page.route('**/*', route => {
      const url = new URL(route.request().url())
      if (url.origin !== 'http://localhost:4173') throw new Error('Unexpected external request')
      if (url.pathname === '/api/v1/authorities/E08000025') return route.fulfill({ json: {
        authority: { ons_code: 'E08000025', name: 'Example Authority' },
        comparators: { multiple_disadvantage: { rows } },
      } })
      if (url.pathname.startsWith('/api/')) return route.fulfill({ json: {} })
      return route.continue()
    })
    await page.goto('/#/authorities/E08000025?lens=context')
    await expect(page.getByText(rows ? 'No multiple-disadvantage rows collected' : 'Multiple-disadvantage data not supplied', { exact: true })).toBeVisible()
  })
}
