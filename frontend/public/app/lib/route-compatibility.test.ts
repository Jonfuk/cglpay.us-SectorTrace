import { describe, expect, it } from 'vitest'
import { canonicalResearchRoute, researchHref } from './route-compatibility'
describe('legacy research bookmarks', () => {
  it.each([
    ['/timeline', { provider: 'example' }, '/coverage', { provider_key: 'example', lens: 'history' }],
    ['/timeline', { authority: 'E00000001' }, '/coverage', { ons_code: 'E00000001', lens: 'history' }],
    ['/documents', { doc: 'doc-1', el: 'element-2', q: 'words' }, '/documents/doc-1', { element_id: 'element-2', q: 'words' }],
    ['/diary', { provider: 'example', buyer: 'E00000001' }, '/diary', { provider_key: 'example', buyer_ons_code: 'E00000001' }],
    ['/doctables', { doc: 'doc-1', table: 'table-1' }, '/doctables', { document_id: 'doc-1', table_id: 'table-1' }],
    ['/contracts', { ocid: 'ocds-1', provider: 'example' }, '/contracts/process/ocds-1', { provider_key: 'example' }],
    ['/pay', { provider: 'example', yearFrom: '2020', yearTo: '2023' }, '/pay', { provider_key: 'example', year_from: '2020', year_to: '2023' }],
    ['/geography', { layer: 'grant_total', selected: 'E00000001' }, '/geography', { metric: 'grant_total', inspect: 'E00000001' }],
  ] as const)('preserves %s query meaning', (path, query, expectedPath, expectedQuery) => {
    expect(canonicalResearchRoute(path, query)).toMatchObject({ path: expectedPath, query: expectedQuery, changed: true })
  })
  it('does not reinterpret current provider-event or repeated comparison URLs', () => {
    expect(canonicalResearchRoute('/timeline', { provider_key: 'example' }).changed).toBe(false)
    expect(canonicalResearchRoute('/compare', { provider_key: ['a', 'b'] }).query.provider_key).toEqual(['a', 'b'])
  })
  it('reports conflicting aliases without substituting the canonical identity', () => {
    const result = canonicalResearchRoute('/contracts', { provider: 'old', provider_key: 'chosen' })
    expect(result.query.provider_key).toBe('chosen')
    expect(result.messages).toHaveLength(1)
  })
  it('accepts public hash links and rejects executable or privileged destinations', () => {
    expect(researchHref('#/contracts?provider=example')).toBe('#/contracts?provider=example')
    for (const value of ['javascript:alert(1)', '/api/admin/secret', '#/admin', '#/providers/../admin', '#/providers/%2e%2e/admin', '#//evil.test']) expect(researchHref(value)).toBeNull()
  })
})
