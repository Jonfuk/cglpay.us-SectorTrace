import { describe, expect, it } from 'vitest'
import { connectionNode, connectionReferences, drawableConnections } from './connections'
const authority = { entity_id: 'graph-A', canonical_name: 'Authority', entity_type: 'LOCAL_AUTHORITY' }
const provider = { entity_id: 'graph-P', canonical_name: 'Provider', entity_type: 'PROVIDER' }
const edge = { relationship_id: 'edge-1', subject_entity_id: 'graph-A', object_entity_id: 'graph-P', valid_from: null, valid_to: null }
describe('commissioning graph identities', () => {
  it('shares only identical source tuples while keeping every plotted relationship reference', () => {
    const sourced = { ...edge, source_url: 'https://example.invalid/source', retrieved_at: '2026-09-07', source_system: 'source' }
    const text = connectionReferences([sourced, { ...sourced, relationship_id: 'edge-2' }, { ...sourced, relationship_id: 'edge-3', retrieved_at: null }, { ...sourced, relationship_id: 'unplaced', object_entity_id: 'missing' }], [authority, provider])
    expect(text).toContain('Diagram edge 2, relationship edge-2')
    expect(text).toContain('Diagram edge 3, relationship edge-3')
    expect(text).toContain('Source reference 2. URL https://example.invalid/source. Retrieved Not supplied.')
    expect(text.match(/URL https:/g)).toHaveLength(2)
    expect(text).not.toContain('unplaced')
  })
  it('does not place missing, ambiguous or wrong-type endpoints into guessed columns', () => {
    expect(drawableConnections([edge], [authority, provider])).toEqual([edge])
    expect(drawableConnections([edge], [authority])).toEqual([])
    expect(connectionNode([provider, { ...provider, canonical_name: 'Conflicting name' }], 'graph-P')).toBeUndefined()
    expect(drawableConnections([edge], [authority, { ...provider, entity_type: 'SUPPLIER' }])).toEqual([])
    expect(drawableConnections([{ ...edge, subject_entity_id: 'graph-P', object_entity_id: 'graph-A' }], [authority, provider])).toEqual([])
  })
  it('keeps repeated dated edges separate and excludes records without an inspection identifier', () => {
    const repeated = { ...edge, relationship_id: 'edge-2', valid_from: '2025-01-01' }
    expect(drawableConnections([edge, repeated, { ...edge, relationship_id: null }], [authority, provider])).toEqual([edge, repeated])
  })
})
