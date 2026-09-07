import { describe, expect, it } from 'vitest'
import { publicQuery } from './public-query'
describe('public endpoint query boundaries', () => {
  it('does not turn UI state or an unsupported chart category into a notice filter', () => {
    expect(publicQuery('/contracts', { provider_key: 'example', year_from: '2020', lens: 'patterns', inspect: 'notice-1', procedure_type: 'open' }))
      .toEqual({ provider_key: 'example', year_from: '2020' })
  })
  it('retains repeated comparison identities and does not invent payment dates', () => {
    expect(publicQuery('/compare', { provider_key: ['a', 'b'], lens: 'charity' })).toEqual({ provider_key: ['a', 'b'] })
    expect(publicQuery('/council_spend', { provider_key: 'a', year_from: '2022', offset: 500 })).toEqual({ provider_key: 'a' })
  })
  it('separates passage context, full-text search and directory search', () => {
    expect(publicQuery('/documents/document-1', { q: 'word', element_id: 'exact-element', context: 8 })).toEqual({ element_id: 'exact-element', context: 8 })
    expect(publicQuery('/document_search', { q: 'word', provider_key: 'a' })).toEqual({ q: 'word' })
    expect(publicQuery('/providers', { q: 'a' })).toEqual({})
  })
})
