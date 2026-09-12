import type { Page } from '@playwright/test'
export const reviewItems = [
  {
    id: 41,
    raw_value: 'Northshire committee paper — source URL needs review',
    module: 'm10',
    item_type: 'unknown_committee_url',
    status: 'pending',
    context_json:
      '{"authority":"Northshire","source_url":"https://example.invalid/paper"}',
  },
  {
    id: 42,
    raw_value: 'Community treatment partnership annual report',
    module: 'm08',
    item_type: 'document_candidate',
    status: 'approved',
    context_json: '{}',
  },
  {
    id: 43,
    raw_value: '<img src=x onerror=alert(1)> Unparsed source text',
    module: 'm10',
    item_type: 'unknown_committee_url',
    status: 'pending',
    context_json: '{}',
  },
]
export const fixtures: Record<string, unknown> = {
  '/api/admin/cockpit': {
    cards: [
      {
        key: 'review',
        title: 'Review queue',
        metric: 2,
        priority: 2,
        reason:
          'Two items need a human judgement. Read their archived sources before deciding.',
        link: '#review',
      },
      {
        key: 'candidates',
        title: 'Candidate documents',
        metric: 8,
        priority: 1,
        reason: 'Documents discovered and awaiting source checks.',
        link: '#candidates',
      },
      {
        key: 'health',
        title: 'Source freshness',
        metric: null,
        priority: 1,
        reason:
          'Freshness check is unavailable. Inspect the last recorded response.',
        link: '#health',
      },
    ],
  },
  '/api/admin/mission-control': {
    active: null,
    last_run: {
      run_id: 'fixture-2026-09-05',
      status: 'partial',
      started_at: '2026-09-05T08:10:00Z',
      origin: 'operator',
    },
    failure_summary: [
      {
        module: 'm10',
        parse_failures: 2,
        pending_review: 2,
        last_status: 'partial',
      },
    ],
    waves: [
      { wave: 1, modules: [{ name: 'm00', last_run: { status: 'ok' } }] },
    ],
  },
  '/api/admin/health': {
    warehouse: { backend: 'PostgreSQL', unapplied: [], tables: 48 },
    extensions: [{ name: 'pg_trgm', installed: true }],
  },
  '/api/admin/jobs': {
    running: null,
    jobs: [
      {
        id: 9,
        kind: 'run',
        label: 'Fixture collection',
        state: 'complete',
        started_at: '2026-09-05T08:10:00Z',
      },
    ],
  },
  '/api/admin/jobs/9': {
    id: 9,
    label: 'Fixture collection',
    state: 'complete',
    log: [{ at: '08:10', text: 'Fixture collection completed' }],
    next: 1,
  },
  '/api/admin/modules': {
    modules: [
      {
        name: 'm00',
        wave: 1,
        cursor_value: null,
        pending_review: 0,
        parse_failures: 0,
      },
      {
        name: 'm10',
        wave: 2,
        cursor_value: '2026-09-04',
        pending_review: 2,
        parse_failures: 2,
      },
    ],
  },
  '/api/admin/run-ledger': {
    runs: [
      {
        run_id: 'fixture-2026-09-05',
        started_at: '2026-09-05T08:10:00Z',
        status: 'partial',
        origin: 'operator',
        modules_ok: 1,
        modules_failed: 1,
      },
    ],
  },
  '/api/review': { items: reviewItems, total: 3 },
  '/api/review/facets': {
    modules: [
      { module: 'm10', pending: 2 },
      { module: 'm08', pending: 0 },
    ],
    item_types: [
      { module: 'm10', item_type: 'unknown_committee_url', pending: 2 },
    ],
    resolvable: {
      unknown_committee_url: {
        label: 'Resolve source URL',
        help: 'Verify the authority source before saving.',
      },
    },
  },
  '/api/review/clusters': {
    clusters: [
      {
        module: 'm10',
        item_type: 'unknown_committee_url',
        count: 2,
        token: 'northshire',
        item_ids: [41, 43],
        sample_raw: 'Northshire',
      },
    ],
    caveat: 'Grouping is a reading aid, not a judgement.',
  },
  '/api/schema': {
    objects: [
      { name: 'documents', kind: 'table', rows: 12 },
      { name: 'restricted_contacts', kind: 'table', restricted: true },
    ],
  },
  '/api/admin/schema-graph': {
    tables: [
      {
        name: 'documents',
        description: 'Archived source documents',
        columns: [
          { name: 'id', type: 'text', pk: true },
          { name: 'title', type: 'text' },
        ],
      },
    ],
  },
  '/api/table/documents': {
    columns: ['id', 'title', 'title'],
    rows: [
      ['doc-01', 'Northshire annual report', 'Same named column retained'],
    ],
    total: 1,
  },
  '/api/admin/candidates': {
    kind: 'cdp_document',
    requires: ['document_type'],
    items: [
      {
        url: 'https://example.invalid/report',
        title: 'Partnership annual report',
        authority: 'E99999999',
        verified: false,
        rejected: false,
      },
    ],
    total: 1,
  },
  '/api/admin/candidates/counts': {
    kinds: { cdp_document: { undecided: 8, promoted: 3, rejected: 1 } },
    promotions: [],
  },
  '/api/admin/candidates/authorities': {
    authorities: [{ ons_code: 'E99999999', name: 'Northshire', candidates: 8 }],
  },
  '/api/admin/candidates/detail': {
    candidate: {
      title: 'Partnership annual report',
      document_type_guess: 'annual_report',
    },
    excerpt: 'Archived document preview',
  },
  '/api/admin/census': {
    items: [
      {
        key: 'census-2024-1',
        census_year: 2024,
        source_page: 0,
        metric: 'headcount',
        value: 120,
        verified: false,
        rejected: false,
      },
    ],
    total: 1,
  },
  '/api/admin/census/counts': {
    years: [{ census_year: 2024, unchecked: 1, verified: 0, rejected: 0 }],
    decisions: [],
    stale: [],
  },
  '/api/admin/census/page': {
    page_number: 0,
    page_text: 'Fixture census page. Headcount: 120.',
    metrics_on_page: [],
  },
  '/api/admin/analysis/overview': {
    latest_run: null,
    executor: 'worker_online',
    counts: { runs: 1 },
    quality_boundary:
      'Automated outputs require a separate human evidence decision.',
  },
  '/api/admin/analysis/domains': {
    domains: [
      { domain_id: 'documents', status: 'ready', prerequisite_status: 'ok' },
    ],
  },
  '/api/admin/analysis/operations': {
    runs: [],
    proposals: [
      {
        proposal_id: 'proposal-1',
        proposal_type: 'Review extraction threshold',
        domain_id: 'documents',
        status: 'pending',
        trigger_json: '{"fixture":true}',
      },
    ],
    model_calls: [],
  },
  '/api/admin/analysis/models': {
    releases: [
      {
        release_id: 'release-1',
        status: 'candidate',
        manifest_sha256: 'fixture-sha',
        created_at: '2026-09-05',
      },
    ],
  },
  '/api/admin/review-analytics': {
    min_group: 5,
    by_month: [{ month: '2026-09', approved: 12, rejected: 3 }],
    by_source: [{ source: 'm10', suppressed: true, total: 2 }],
    note: 'Suppressed groups must not be interpreted as zero.',
  },
  '/api/admin/claims': { items: [], total: 0 },
  '/api/admin/claims/counts': { total: 0 },
  '/api/admin/claims/evidence': { tables: [] },
  '/api/admin/exports': {
    files: [
      {
        name: 'evidence.csv',
        path: 'bundle/evidence.csv',
        bytes: 1024,
        modified: '2026-09-05',
        group: 'bundle',
        provenance: 'bundle/provenance.json',
      },
    ],
    staleness: { groups: [{ group: 'bundle', stale: true }] },
  },
  '/api/overrides': {
    overrides: [
      {
        ons_code: 'E99999999',
        base_url: 'https://example.invalid',
        verified_by: 'Fixture reviewer',
      },
    ],
  },
}
export async function mockApi(page: Page) {
  await page.context().route('https://example.invalid/**', (r) => r.abort())
  const posts: { path: string; body: any }[] = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      posts.push({ path, body })
      if (path === '/api/query')
        return route.fulfill({
          json: {
            columns: ['value', 'value'],
            rows: [[1, 2]],
            truncated: true,
          },
        })
      if (path === '/api/review/decide')
        return route.fulfill({
          json: { updated: body.ids, unchanged: [], missing: [] },
        })
      return route.fulfill({ json: { ok: true, id: 9, run_id: 'run-fixture' } })
    }
    if (/\/api\/review\/\d+\/sidecar$/.test(path))
      return route.fulfill({
        json: {
          source: {
            url: 'https://example.invalid/paper',
            excerpt:
              'The committee received the annual report. <script>unsafe()</script>',
            retrieved_at: '2026-09-04T12:00:00Z',
            payload_sha256: 'fixture-sha256',
          },
          candidates: { supported: false },
          caveat: 'This is an archived source excerpt.',
        },
      })
    if (/\/api\/review\/\d+$/.test(path))
      return route.fulfill({ json: { decisions: [] } })
    if (path === '/api/table/restricted_contacts')
      return route.fulfill(
        url.searchParams.get('reveal') === '1'
          ? {
              json: {
                columns: ['name'],
                rows: [['Restricted fixture']],
                total: 1,
              },
            }
          : {
              status: 403,
              json: { error: 'Restricted table requires reveal' },
            },
      )
    return route.fulfill(
      path in fixtures
        ? { json: fixtures[path] }
        : { status: 503, json: { error: 'Fixture: capability unavailable' } },
    )
  })
  return posts
}
