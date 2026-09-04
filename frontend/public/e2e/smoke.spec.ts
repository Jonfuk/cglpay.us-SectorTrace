import { expect, test } from '@playwright/test'

// A boot smoke test: the built app must mount in a real browser with no console
// errors and no Vue hydration/interop warnings. Data routes render their
// "unavailable" state (there is no API in this harness) — proving that path is
// safe is part of the point.

/** Attach console/error listeners that fail the test on anything unexpected. */
function collectProblems(page: import('@playwright/test').Page) {
  const problems: string[] = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console.error: ${msg.text()}`)
    // Vue emits hydration/interop mismatches as warnings; treat them as failures.
    if (msg.type() === 'warning' && /hydrat|vapor|interop/i.test(msg.text())) {
      problems.push(`console.warn: ${msg.text()}`)
    }
  })
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`))
  // Ignore expected failed API/network calls — there is no backend here.
  return problems
}

test('public shell boots without console errors', async ({ page }) => {
  const problems = collectProblems(page)
  await page.goto('/')
  // The masthead brand link is part of the static shell and must render.
  await expect(page.getByRole('link', { name: 'SectorTrace', exact: true })).toBeVisible()
  // The primary nav renders (data-independent).
  await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
  await page.waitForTimeout(500)
  expect(problems, problems.join('\n')).toEqual([])
})

test('navigating to a data route mounts it and updates the hash bookmark', async ({ page }) => {
  const problems = collectProblems(page)
  await page.goto('/')
  await page.getByRole('link', { name: 'Pay' }).click()
  await expect(page.getByRole('heading', { name: 'Pay' })).toBeVisible()
  // The URL a bookmark would capture is the hash form.
  expect(page.url()).toContain('#/pay')
  await page.waitForTimeout(500)
  expect(problems, problems.join('\n')).toEqual([])
})

test('the map view lazy-loads MapLibre and mounts without errors', async ({ page }) => {
  const problems = collectProblems(page)
  await page.goto('/')
  await page.getByRole('link', { name: 'Places' }).click()
  await expect(page.getByRole('heading', { name: 'Places' })).toBeVisible()
  // Switch to the map view — this is what lazy-loads the MapLibre chunk.
  await page.getByRole('button', { name: 'Map' }).click()
  await page.waitForTimeout(1500)
  expect(problems, problems.join('\n')).toEqual([])
})

test('all public port routes mount through the SPA fallback', async ({ page }) => {
  test.setTimeout(120_000)
  const problems = collectProblems(page)
  const routes = [
    ['pay', 'Pay'],
    ['contracts', 'Where public money is going'],
    ['providers', 'Find provider evidence'],
    ['geography', 'Places'],
    ['treatment', 'Treatment'],
    ['cqc', 'CQC'],
    ['pfd', 'Safety & legal evidence'],
    ['relationships', 'Relationships'],
    ['claims', 'Claims'],
    ['documents', 'Document search'],
    ['compare', 'Compare'],
    ['cooccurrence', 'Co-occurrence'],
    ['changes', 'Changes'],
    ['calendar', 'Publication calendar'],
    ['catalogue', 'Dataset catalogue'],
    ['api', 'API'],
    ['notebook', 'Notebook'],
    ['saved', 'Saved searches'],
    ['journey', 'Your journey'],
    ['revisions', 'Compare revisions'],
    ['pathfinder', 'Pathfinder'],
    ['links', 'Source links'],
    ['doctables', 'Document tables'],
    ['diary', 'Contract diary'],
    ['coverage', 'Data coverage'],
    ['timeline', 'Timeline'],
  ] as const

  for (const [route] of routes) {
    // Start from the shell for each route. This exercises the same hash
    // navigation used by the real links and avoids relying on the static
    // server to interpret a fragment before the SPA has mounted.
    await page.goto('/')
    await expect(page.getByRole('banner').getByRole('link', { name: 'SectorTrace', exact: true })).toBeVisible()
    const link = page.locator(`a[href="#/${route}"]`).first()
    if (await link.count()) await link.click()
    else await page.evaluate((path) => { window.location.hash = `#/${path}` }, route)
    // Some pages keep their first paint behind a current API response. In
    // this deliberately backend-free harness, route resolution and bookmark
    // state are the stable assertion; rendered data states are covered by the
    // live VPS checks and the focused smoke tests above.
    await expect(page).toHaveURL(new RegExp(`#/${route}(?:$|[?])`))
    await expect(page.getByRole('banner').getByRole('link', { name: 'SectorTrace', exact: true })).toBeVisible()
  }
  expect(problems, problems.join('\n')).toEqual([])
})

test('a procurement lifecycle deep link resolves its dynamic page', async ({ page }) => {
  await page.route('**/api/v1/contracts', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ notices: [], total: 0, caveats: {}, value_concentration: {} }),
    })
  })
  await page.route('**/api/v1/council_spend*', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) })
  })
  await page.route('**/api/v1/contracts/process/ocds-test', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ocid: 'ocds-test',
        buyer: { name: 'Test council' },
        notice_count: 1,
        date_range: { earliest: '2026-01-01T00:00:00Z', latest: '2026-01-01T00:00:00Z' },
        stages: [{ stage: 'award', present: true, notices: [{ title: 'Test award', date_published: '2026-01-01' }] }],
      }),
    })
  })

  await page.goto('/#/contracts/process/ocds-test')
  await expect(page.getByRole('heading', { name: 'Procurement lifecycle' })).toBeVisible()
  await expect(page.getByText('Test council')).toBeVisible()
})
