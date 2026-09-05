import { expect, test } from '@playwright/test'
import { mockApi } from './fixtures'

test('phone evidence detail returns to the preserved queue position', async ({page}) => {
  await mockApi(page)
  await page.setViewportSize({width:390,height:844})
  await page.goto('./#/review')
  const source = page.getByRole('button',{name:/Northshire committee/})
  await source.scrollIntoViewIfNeeded()
  const body=page.locator('.admin-workspace > [data-slot=body]')
  const position=await body.evaluate(el=>el.scrollTop)
  await source.click()
  await expect(page.getByRole('searchbox',{name:'Search',exact:true})).toBeHidden()
  await page.getByRole('button',{name:'Back to queue',exact:false}).click()
  await expect(source).toBeFocused()
  await expect.poll(()=>body.evaluate(el=>el.scrollTop)).toBe(position)
})

test('sidebar and admin appearance persist independently through browser history', async ({
  page,
}) => {
  await mockApi(page)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.addInitScript(() =>
    localStorage.setItem('nuxt-color-mode', 'light'),
  )
  await page.goto('./#/review?module=m10')
  await page
    .getByRole('combobox', { name: 'Theme', exact: true })
    .selectOption('dark')
  await page
    .getByRole('button', { name: 'Collapse sidebar', exact: true })
    .click()
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expect
    .poll(() =>
      page
        .locator('.admin-desktop-sidebar')
        .evaluate((el) => el.getBoundingClientRect().width),
    )
    .toBe(64)
  expect(
    await page.evaluate(() => localStorage.getItem('nuxt-color-mode')),
  ).toBe('light')
  await page.getByRole('link', { name: 'Pipeline', exact: true }).click()
  await expect(page.locator('main h1')).toHaveText('Pipeline')
  await page.goBack()
  await expect(page).toHaveURL(/#\/review\?module=m10$/)
  await expect(page.locator('main h1')).toHaveText('Review queue')
  await page.goForward()
  await expect(page.locator('main h1')).toHaveText('Pipeline')
})

test('failed claim drafting retains text, caveats and reviewer payload', async ({
  page,
}) => {
  await mockApi(page)
  let submitted: unknown
  await page.route('**/api/admin/claims/create', async (r) => {
    submitted = r.request().postDataJSON()
    await r.fulfill({
      status: 503,
      json: { error: 'Draft service unavailable' },
    })
  })
  await page.goto('./#/claims')
  await page
    .getByRole('textbox', { name: 'Reviewer name' })
    .fill('Claims reviewer')
  await page
    .getByRole('textbox', { name: 'New claim text' })
    .fill('Fixture claim <script>not markup</script>')
  await page
    .getByRole('textbox', { name: 'New claim caveats' })
    .fill('Source-specific limitation')
  await page
    .getByRole('textbox', { name: 'New claim internal note' })
    .fill('Retain on failure')
  await page.getByRole('button', { name: 'Create draft', exact: true }).click()
  await expect(
    page.getByText('Draft service unavailable', { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('textbox', { name: 'New claim caveats' }),
  ).toHaveValue('Source-specific limitation')
  expect(submitted).toMatchObject({
    claim_text: 'Fixture claim <script>not markup</script>',
    caveats: 'Source-specific limitation',
    note: 'Retain on failure',
    created_by: 'Claims reviewer',
  })
})

test('log reading pauses following and polling ends when leaving', async ({
  page,
}) => {
  await mockApi(page)
  let requests = 0
  await page.route('**/api/admin/jobs/9?**', (r) => {
    requests++
    return r.fulfill({
      json: {
        id: 9,
        running: true,
        state: 'running',
        label: 'Fixture run',
        next: requests,
        log: Array.from({ length: 80 }, (_, i) => ({
          at: '09:00',
          text: `Request ${requests}, archived log line ${i}`,
        })),
      },
    })
  })
  await page.goto('./#/pipeline?view=jobs')
  await page.getByRole('button', { name: 'Follow job', exact: true }).click()
  const log = page.getByLabel('Job log', { exact: true })
  await expect(log).toBeVisible()
  await log.evaluate((el) => {
    el.scrollTop = 0
    el.dispatchEvent(new Event('scroll'))
  })
  await expect(
    page.getByText('Reading earlier output', { exact: true }),
  ).toBeVisible()
  const before = requests
  await expect.poll(() => requests).toBeGreaterThan(before)
  await expect.poll(() => log.evaluate((el) => el.scrollTop)).toBe(0)
  await page.getByRole('button', { name: 'Follow latest', exact: true }).click()
  await expect(
    page.getByText('Following latest output', { exact: true }),
  ).toBeVisible()
  await page.goto('./#/database')
  await expect(page.locator('main h1')).toHaveText('Database')
  const stopped = requests
  await page.waitForTimeout(1600)
  expect(requests).toBe(stopped)
})

for (const scheme of ['light', 'dark'] as const)
  test(`200% equivalent viewport and semantic contrast: ${scheme}`, async ({
    page,
  }) => {
    await mockApi(page)
    // 720 CSS pixels is the layout viewport of a 1440-pixel window at 200%.
    await page.setViewportSize({ width: 720, height: 500 })
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' })
    await page.goto('./#/review')
    await expect(page.locator('main h1')).toHaveText('Review queue')
    await expect(
      page.getByRole('button', { name: 'Open navigation' }),
    ).toBeVisible()
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBeTruthy()
    const colors = await page.evaluate(() => {
      const s = getComputedStyle(document.documentElement)
      return Object.fromEntries(
        [
          'ink',
          'muted',
          'accent',
          'surface',
          'positive',
          'positive-bg',
          'error',
          'error-bg',
          'control',
          'focus',
        ].map((k) => [k, s.getPropertyValue('--st-' + k).trim()]),
      )
    })
    function luminance(hex: string) {
      const expanded =
        hex.length === 4
          ? '#' + [...hex.slice(1)].map((c) => c + c).join('')
          : hex
      const rgb = [1, 3, 5]
        .map((i) => parseInt(expanded.slice(i, i + 2), 16) / 255)
        .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
      return rgb[0]! * 0.2126 + rgb[1]! * 0.7152 + rgb[2]! * 0.0722
    }
    function contrast(a: string, b: string) {
      const x = luminance(a),
        y = luminance(b)
      return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
    }
    for (const foreground of ['ink', 'muted', 'accent'])
      expect(
        contrast(colors[foreground]!, colors.surface!),
      ).toBeGreaterThanOrEqual(4.5)
    for (const semantic of ['positive', 'error'])
      expect(
        contrast(colors[semantic]!, colors[semantic + '-bg']!),
      ).toBeGreaterThanOrEqual(4.5)
    for (const control of ['control', 'focus'])
      expect(
        contrast(colors[control]!, colors.surface!),
      ).toBeGreaterThanOrEqual(3)
  })

test('partial batch failures remain visible and selected for retry', async ({
  page,
}) => {
  await mockApi(page)
  await page.addInitScript(() =>
    localStorage.setItem(
      'st.admin.reviewer',
      JSON.stringify({ v: 1, data: 'Reviewer' }),
    ),
  )
  await page.route('**/api/admin/candidates?**', (r) =>
    r.fulfill({
      json: {
        requires: [],
        total: 2,
        items: [
          { url: 'https://example.invalid/one' },
          { url: 'https://example.invalid/two' },
        ],
      },
    }),
  )
  const attempts: string[] = []
  await page.route('**/api/admin/candidates/reject', async (r) => {
    const url = r.request().postDataJSON().urls[0]
    attempts.push(url)
    await r.fulfill(
      url.endsWith('two')
        ? { status: 503, json: { error: 'Fixture refusal' } }
        : { json: { rejected: 1 } },
    )
  })
  await page.goto('./#/candidates')
  await page.getByRole('checkbox', { name: 'Select page', exact: true }).check()
  await page
    .getByRole('textbox', { name: 'Batch note', exact: true })
    .fill('Batch context')
  await page
    .getByRole('button', { name: 'Reject selected', exact: true })
    .click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => attempts.length).toBe(2)
  await expect(page.getByText(/Fixture refusal/)).toBeVisible()
  await expect(
    page.getByRole('checkbox', {
      name: 'Select https://example.invalid/two',
      exact: true,
    }),
  ).toBeChecked()
  await expect(
    page.getByRole('checkbox', {
      name: 'Select https://example.invalid/one',
      exact: true,
    }),
  ).not.toBeChecked()
  await expect(
    page.getByRole('textbox', { name: 'Batch note', exact: true }),
  ).toHaveValue('Batch context')
})

test('pipeline conflicts follow the existing job and exports retain provenance', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.route('**/api/admin/run', (r) =>
    r.fulfill({ status: 409, json: { error: 'Already running', job_id: 9 } }),
  )
  await page.goto('./#/pipeline')
  await page
    .getByRole('button', { name: 'Dry run', exact: true })
    .first()
    .click()
  await expect(
    page.getByText('Fixture collection completed', { exact: false }),
  ).toBeVisible()
  await page.goto('./#/exports')
  await expect(
    page.getByRole('link', { name: 'Provenance', exact: true }),
  ).toHaveAttribute(
    'href',
    '/api/admin/exports/file?path=bundle%2Fprovenance.json',
  )
  await page.getByRole('button', { name: 'Generate', exact: true }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]).toEqual({
    path: '/api/admin/export',
    body: { target: 'all' },
  })
})

test('analysis proposals and release rollback retain optional reasons', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.goto('./#/analysis?view=proposals')
  await page.getByRole('button', { name: 'Defer', exact: true }).click()
  await page
    .getByRole('textbox', { name: 'Your response' })
    .fill('Need a source check')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]).toEqual({
    path: '/api/admin/analysis/proposals/defer',
    body: { proposal_id: 'proposal-1', reason: 'Need a source check' },
  })
  await page
    .getByRole('link', { name: 'Releases & reports', exact: true })
    .click()
  await page.getByRole('button', { name: 'Rollback', exact: true }).click()
  await page
    .getByRole('textbox', { name: 'Your response' })
    .fill('Regression in fixture')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[1]).toEqual({
    path: '/api/admin/analysis/releases/rollback',
    body: { release_id: 'release-1', reason: 'Regression in fixture' },
  })
})

test('failed analysis decisions reopen with the entered reason', async ({
  page,
}) => {
  await mockApi(page)
  await page.route('**/api/admin/analysis/proposals/defer', (r) =>
    r.fulfill({ status: 503, json: { error: 'Decision unavailable' } }),
  )
  await page.goto('./#/analysis?view=proposals')
  await page.getByRole('button', { name: 'Defer', exact: true }).click()
  await page
    .getByRole('textbox', { name: 'Your response' })
    .fill('Keep this reasoning for retry')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(
    page.getByText('Decision unavailable', { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Defer', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Your response' }),
  ).toHaveValue('Keep this reasoning for retry')
})

test('quality and lineage workspaces expose records and explicit actions', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.addInitScript(() =>
    localStorage.setItem(
      'st.admin.reviewer',
      JSON.stringify({ v: 1, data: 'Quality reviewer' }),
    ),
  )
  await page.route('**/api/admin/aliases?**', (r) =>
    r.fulfill({
      json: {
        items: [
          {
            unmatched_name: 'Fixture partnership',
            resolved: false,
            decisions: [],
          },
        ],
      },
    }),
  )
  await page.route('**/api/admin/coverage?**', (r) =>
    r.fulfill({
      json: {
        authority_count: 1,
        authorities: [
          {
            ons_code: 'E99999999',
            name: 'Northshire',
            region: 'Fixture region',
            cells: { Documents: 3 },
          },
        ],
        columns: [
          {
            label: 'Documents',
            table: 'documents',
            covered: 1,
            missing: false,
          },
          { label: 'Accounts', table: 'accounts', missing: true },
        ],
      },
    }),
  )
  await page.route('**/api/admin/lineage', (r) =>
    r.fulfill({
      json: {
        node_kinds: ['module', 'table'],
        nodes: [
          { id: 'module:m10', label: 'Collection m10', kind: 'module' },
          { id: 'table:documents', label: 'Archived documents', kind: 'table' },
        ],
        edges: [
          { source: 'module:m10', target: 'table:documents', rel: 'writes' },
        ],
      },
    }),
  )
  await page.route('**/api/admin/parser-replay?**', (r) =>
    r.fulfill({
      json: {
        available: true,
        stored: { text: 'Stored fixture' },
        proposed: { text: 'Proposed fixture' },
        diff: { added: ['One source line'] },
        archive: { sha256: 'fixture-archive-hash' },
      },
    }),
  )
  await page.goto('./#/health?view=coverage')
  await expect(
    page.getByRole('cell', { name: 'No recorded rows', exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('cell', { name: 'Unavailable', exact: true }),
  ).toBeVisible()
  await page.route('**/api/admin/validation-rules', (r) =>
    r.fulfill({
      json: {
        kinds: ['trigger', 'provenance'],
        schema_rules: [
          {
            id: 'human-review',
            kind: 'trigger',
            title: 'Human review required',
            purpose: 'Promotions need an attributed decision.',
          },
          {
            id: 'source-hash',
            kind: 'provenance',
            title: 'Source hash required',
            enforced: true,
          },
        ],
        observed_rules: [],
      },
    }),
  )
  await page.goto('./#/health?view=rules')
  await expect(
    page.getByRole('heading', { name: 'Human review required', exact: true }),
  ).toBeVisible()
  await page.getByRole('checkbox', { name: 'trigger', exact: true }).uncheck()
  await expect(
    page.getByRole('heading', { name: 'Human review required', exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole('heading', { name: 'Source hash required', exact: true }),
  ).toBeVisible()
  await page.goto('./#/aliases')
  await page
    .getByRole('textbox', { name: 'Authority ONS code' })
    .fill('E99999999')
  await page
    .getByRole('textbox', { name: 'Reason', exact: true })
    .fill('Explicit source mapping')
  await page
    .getByRole('button', { name: 'Accept mapping', exact: true })
    .click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]!.body).toMatchObject({
    unmatched_name: 'Fixture partnership',
    canonical_id: 'E99999999',
    target_scheme: 'buyer',
    status: 'accepted',
    decided_by: 'Quality reviewer',
    reason: 'Explicit source mapping',
  })
  await expect(
    page.getByRole('textbox', { name: 'Reason', exact: true }),
  ).toHaveValue('')
  await page.goto('./#/parser-replay')
  await page.getByRole('textbox', { name: 'Document ID' }).fill('fixture-doc')
  await page.getByRole('button', { name: 'Replay', exact: true }).click()
  await expect(
    page.getByText('Proposed fixture', { exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText('fixture-archive-hash', { exact: true }),
  ).toBeVisible()
  await page.goto('./#/lineage')
  await page
    .getByRole('button', { name: 'Collection m10 module', exact: true })
    .click()
  await page
    .getByRole('button', { name: 'Follow relationship', exact: true })
    .click()
  await expect(page.locator('main h2')).toHaveText('Archived documents')
})

test('candidate and census verification require fresh source interaction', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.addInitScript(() => {
    localStorage.setItem(
      'st.admin.reviewer',
      JSON.stringify({ v: 1, data: 'Reviewer' }),
    )
  })
  await page.goto('./#/candidates')
  await page
    .getByRole('button', { name: /https:\/\/example.invalid\/report/ })
    .click()
  await expect(
    page.getByRole('button', { name: 'Promote document', exact: true }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Preview record' }).click()
  await page
    .getByRole('textbox', { name: 'Confirmed document_type', exact: true })
    .fill('annual_report')
  await expect(
    page.getByRole('button', { name: 'Promote document', exact: true }),
  ).toBeDisabled()
  const popup = page.waitForEvent('popup')
  await page.getByRole('button', { name: 'Open document ↗' }).click()
  await (await popup).close()
  await page
    .getByRole('button', { name: 'Promote document', exact: true })
    .click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]!.body).toMatchObject({
    kind: 'cdp_document',
    url: 'https://example.invalid/report',
    promoted_by: 'Reviewer',
    fields: { document_type: 'annual_report' },
  })
  await expect(
    page.getByRole('button', { name: 'Reject', exact: true }),
  ).toBeEnabled()
  await page.goto('./#/census')
  await page.getByRole('button', { name: /headcount/ }).click()
  await expect(
    page.getByRole('button', { name: 'Verify against source' }),
  ).toBeDisabled()
  await page.getByRole('button', { name: 'Read extracted page 0' }).click()
  await page.getByRole('button', { name: 'Verify against source' }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(2)
  expect(posts[1]!.body).toMatchObject({
    key: 'census-2024-1',
    verified_by: 'Reviewer',
  })
})

test('claim corrections send the selected ontology fields', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.addInitScript(() =>
    localStorage.setItem(
      'st.admin.reviewer',
      JSON.stringify({ v: 1, data: 'Reviewer' }),
    ),
  )
  await page.route('**/api/admin/claim-candidates?**', (r) =>
    r.fulfill({
      json: {
        candidates: [
          {
            claim_candidate_id: 'c-1',
            subject_hint: 'Partnership',
            predicate: 'supports',
            evidence_span: 'Quoted source',
            status: 'queued',
          },
        ],
        total: 1,
      },
    }),
  )
  await page.route('**/api/admin/claim-ontology', (r) =>
    r.fulfill({
      json: {
        predicates: [{ id: 'supports', label: 'Supports' }],
        concepts: [{ id: 'workforce', label: 'Workforce' }],
        reason_codes: ['wrong_object'],
      },
    }),
  )
  await page.goto('./#/claimreview')
  await page.getByRole('button', { name: /Partnership/ }).click()
  await page
    .getByRole('combobox', { name: 'Decision', exact: true })
    .selectOption('corrected')
  await page
    .getByRole('combobox', { name: 'Reason code', exact: true })
    .selectOption('wrong_object')
  await page
    .getByRole('combobox', { name: 'Corrected object concept', exact: true })
    .selectOption('workforce')
  await page
    .getByLabel('Corrected object literal')
    .fill('Correct source wording')
  await page.getByRole('button', { name: 'Record decision' }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]!.body).toMatchObject({
    claim_candidate_id: 'c-1',
    decision: 'corrected',
    reason_code: 'wrong_object',
    corrected_object_concept_id: 'workforce',
    corrected_object_literal: 'Correct source wording',
  })
})

test('keyboard commands, drawer focus and blocked storage remain usable', async ({
  page,
}) => {
  await mockApi(page)
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new Error('blocked')
      },
    })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('./#/review')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(
    page.getByRole('button', { name: 'Open navigation' }),
  ).toBeFocused()
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await page
    .getByRole('textbox', { name: 'Decision note' })
    .fill('a r u are ordinary text here')
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('review decisions and mixed-status audited undo retain exact payloads', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.goto('./#/review?status=all')
  await page
    .getByRole('textbox', { name: 'Reviewer name' })
    .fill('Fixture reviewer')
  await page.getByRole('textbox', { name: 'Reviewer name' }).blur()
  await page
    .getByRole('checkbox', { name: 'Select item 41', exact: true })
    .check()
  await page
    .getByRole('checkbox', { name: 'Select item 42', exact: true })
    .check()
  await page
    .getByRole('textbox', { name: 'Decision note' })
    .fill('Checked source')
  await page
    .getByRole('button', { name: 'Reject selected', exact: true })
    .click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]).toEqual({
    path: '/api/review/decide',
    body: {
      ids: [41, 42],
      decision: 'rejected',
      decided_by: 'Fixture reviewer',
      note: 'Checked source',
    },
  })
  await page.getByRole('button', { name: 'Undo', exact: true }).click()
  await expect.poll(() => posts.length).toBe(3)
  expect(posts.slice(1).map((p) => [p.body.ids, p.body.decision])).toEqual([
    [[41], 'pending'],
    [[42], 'approved'],
  ])
})

test('keyboard cancellation returns focus and refresh preserves review notes', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('./#/review')
  await page
    .getByRole('textbox', { name: 'Reviewer name' })
    .fill('Keyboard reviewer')
  await page
    .getByRole('checkbox', { name: 'Select item 41', exact: true })
    .check()
  const reject = page.getByRole('button', {
    name: 'Reject selected',
    exact: true,
  })
  await reject.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(reject).toBeFocused()
  await page
    .getByRole('textbox', { name: 'Decision note' })
    .fill('Keep this note through refresh')
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(
    page.getByRole('textbox', { name: 'Decision note' }),
  ).toHaveValue('Keep this note through refresh')
  await page.getByRole('link', { name: 'Pipeline', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.locator('main h1')).toHaveText('Review queue')
})

test('SQL preserves duplicate columns and Explain never adds Analyze', async ({
  page,
}) => {
  const posts = await mockApi(page)
  await page.goto('./#/sql')
  await expect(page.getByRole('textbox', { name: 'SQL statement' })).toHaveCSS('font-family', /monospace/)
  await page.getByRole('textbox', { name: 'SQL statement' }).fill('SELECT 1, 2')
  await page.getByRole('button', { name: 'Explain', exact: true }).click()
  await expect.poll(() => posts.length).toBe(1)
  expect(posts[0]!.body.sql).toBe('EXPLAIN SELECT 1, 2')
  await expect(page.locator('th').filter({ hasText: 'value' })).toHaveCount(2)
})

test('reveal is never restored from an explicit URL or reload', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('./#/database?table=restricted_contacts&reveal=1')
  await expect(
    page.getByText('Restricted fixture', { exact: true }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: /Reveal/ }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(
    page.getByText('Restricted fixture', { exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(
    page.getByText('Restricted fixture', { exact: true }),
  ).toHaveCount(0)
})

test('legacy migration preserves Nuxt values and explicit links win', async ({
  page,
}) => {
  await mockApi(page)
  await page.addInitScript(() => {
    localStorage.setItem('cglpay.reviewer', 'Old reviewer')
    localStorage.setItem('cglpay.dense', '1')
    localStorage.setItem(
      'cglpay.location',
      '#database?table=documents&reveal=1',
    )
    localStorage.setItem(
      'st.admin.reviewer',
      JSON.stringify({ v: 1, data: 'Current reviewer' }),
    )
  })
  await page.goto('./#review?module=m10')
  await expect(page).toHaveURL(/#\/review\?module=m10$/)
  await expect(
    page.getByRole('textbox', { name: 'Reviewer name' }),
  ).toHaveValue('Current reviewer')
  await expect(page.locator('[data-density]')).toHaveAttribute(
    'data-density',
    'compact',
  )
  await page.goto('./')
  await expect(page).toHaveURL(/#\/review\?module=m10$/)
  await page.goto('/admin/analysis')
  await expect(page).toHaveURL(/#\/analysis$/)
})

for (const theme of ['light', 'dark'] as const)
  for (const width of [1440, 1024, 390]) {
    test(`operational screens render offline: ${theme}, ${width}px`, async ({
      page,
    }, info) => {
      await mockApi(page)
      const errors: string[] = []
      page.on('pageerror', (e) => errors.push(e.message))
      await page.route(/^https?:\/\/(?!localhost|127\.0\.0\.1)/, (r) =>
        r.abort(),
      )
      await page.setViewportSize({ width, height: 1000 })
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      for (const [path, heading] of [
        ['', 'Your operator desk'],
        ['review', 'Review queue'],
        ['pipeline', 'Pipeline'],
        ['analysis', 'Analysis platform'],
        ['database?table=documents', 'Database'],
        ['sql', 'Read-only SQL'],
      ]) {
        await page.goto('./#/' + path)
        await expect(page.locator('main h1')).toHaveText(heading!)
        if (path === 'review')
          await page
            .getByRole('button', { name: /Northshire committee/ })
            .click()
        if (path === 'sql') {
          await page
            .getByRole('textbox', { name: 'SQL statement' })
            .fill('SELECT 1 AS value, 2 AS value')
          await page
            .getByRole('button', { name: 'Run query', exact: true })
            .click()
          await expect(
            page.getByRole('heading', { name: 'Query results', exact: true }),
          ).toBeVisible()
        }
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBeTruthy()
        if (info.project.name === 'chromium')
          await page.screenshot({
            path: info.outputPath(`${path!.split('?')[0] || 'overview'}.png`),
            fullPage: true,
          })
      }
      expect(errors).toEqual([])
    })
  }
