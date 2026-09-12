import { expect, test } from '@playwright/test'

function collectProblems(page: import('@playwright/test').Page) {
  const problems: string[] = []
  page.on('console', (msg) => {
    // The static harness has no backend, so Chromium reports the expected
    // API 404s as resource errors. JavaScript failures and Vue warnings remain
    // fatal; API-unavailable rendering is covered by the page assertions.
    if (
      msg.type() === 'error' &&
      !/Failed to load resource: the server responded with a status of 404/i.test(
        msg.text(),
      )
    ) {
      problems.push(`console.error: ${msg.text()}`)
    }
    if (msg.type() === 'warning' && /hydrat|vapor|interop/i.test(msg.text())) {
      problems.push(`console.warn: ${msg.text()}`)
    }
  })
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`))
  return problems
}

test('admin shell boots without console or hydration errors', async ({
  page,
}) => {
  const problems = collectProblems(page)
  await page.goto('./')
  await expect(
    page.getByRole('link', { name: /SectorTrace Operations/ }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Your operator desk', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Review queue', exact: true }),
  ).toBeVisible()
  await page.waitForTimeout(500)
  expect(problems, problems.join('\n')).toEqual([])
})

test('admin hash-history route mounts the claims authoring surface', async ({
  page,
}) => {
  const problems = collectProblems(page)
  await page.goto('./')
  await page.getByRole('link', { name: 'Claims', exact: true }).click()
  await expect(page).toHaveURL(/#\/claims$/)
  await expect(
    page.getByRole('heading', { name: 'Claims', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('New draft claim')).toBeVisible()
  await page.waitForTimeout(500)
  expect(problems, problems.join('\n')).toEqual([])
})
