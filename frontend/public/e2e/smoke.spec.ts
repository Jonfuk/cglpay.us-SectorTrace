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
