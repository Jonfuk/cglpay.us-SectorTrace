import { describe, expect, it } from 'vitest'
import { annotateCollection, collectionHref, mergeCollection, parseCollection } from './collections'
const entry = { id: 'one', label: 'Research', href: '#/compare?provider_key=a&provider_key=b', at: 1 }
describe('collection portability', () => {
  it('retains repeated URL state and accepts existing version-one envelopes', () => {
    expect(parseCollection(JSON.stringify({ v: 1, data: [entry] }), 'saved')).toEqual([entry])
    expect(collectionHref(entry.href)).toBe(entry.href)
    expect(collectionHref('/documents?id=old')).toBe('#/documents?id=old')
  })
  it('rejects the entire import when a link or collection type is invalid', () => {
    for (const href of ['javascript:alert(1)', '//outside.invalid', '/\\outside.invalid', '/admin', '#/api/v1/providers', '\n#/documents']) {
      expect(() => parseCollection(JSON.stringify({ v: 1, data: [entry, { ...entry, href }] }), 'saved')).toThrow()
    }
    expect(() => parseCollection(JSON.stringify({ format: 'sectortrace-collection', version: 2, kind: 'saved', entries: [entry] }), 'saved')).toThrow()
    expect(() => parseCollection(JSON.stringify({ format: 'sectortrace-collection', version: 2, kind: 'saved', v: 1, data: [entry] }), 'saved')).toThrow()
    expect(() => parseCollection(JSON.stringify({ v: 1, data: [entry] }), 'notebook')).toThrow()
  })
  it('preserves conflicting records and leaves the original collection untouched', () => {
    const existing = [entry]
    const result = mergeCollection(existing, [entry, { ...entry, label: 'Different research' }], () => 'new-id')
    expect(existing).toEqual([entry])
    expect(result).toEqual({ entries: [entry, { ...entry, id: 'new-id', label: 'Different research' }], added: 1, skipped: 1 })
  })
  it('edits only personal annotation while retaining the original reference and date', () => {
    const original = { id: 'note', title: 'Reference', href: '#/documents?id=old', at: 1, note: 'Exact source; text — unchanged.' }
    expect(annotateCollection([original], original.id, JSON.stringify(original), 'My analysis')).toEqual([{ ...original, annotation: 'My analysis' }])
    expect(original).not.toHaveProperty('annotation')
    expect(annotateCollection([original, original], original.id, JSON.stringify(original), 'My analysis')).toBeNull()
    expect(annotateCollection([{ ...original, note: 'Changed reference' }], original.id, JSON.stringify(original), 'My analysis')).toBeNull()
  })
})
