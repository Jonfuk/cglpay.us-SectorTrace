import { describe, expect, it } from 'vitest'
import { pathInputError, verifiedNode, verifiedProfile } from './verified-path'
describe('verified path scope', () => {
  it('requires supported endpoints and the agreed hop bound', () => {
    const query = { from_type: 'supplier', from_id: 'exact-key', to_type: 'authority', to_id: 'E00000001', max_hops: '6' }
    expect(pathInputError(query)).toBe('')
    expect(pathInputError({ ...query, max_hops: '8' })).toContain('1 to 6')
    expect(pathInputError({ ...query, from_type: 'company' })).toContain('supported type')
    expect(pathInputError({ ...query, from_id: '' })).toContain('start and an end')
  })
  it('uses explicit node types and public ids, never parses composite strings', () => {
    const node = { node: 'provider:misleading-id', type: 'provider', id: 'actual-public-id' }
    expect(verifiedProfile(verifiedNode([node], node.node))).toBe('/providers/actual-public-id')
    expect(verifiedProfile(verifiedNode([node, node], node.node))).toBeUndefined()
    expect(verifiedProfile({ node: 'provider:guessed' })).toBeUndefined()
    expect(verifiedProfile({ ...node, type: 'supplier' })).toBeUndefined()
  })
})
