import { describe, expect, it } from 'vitest'
import { coMentionDestination, coMentionIdentity, coMentionKeyError } from './co-mentions'
describe('co-mention source scope', () => {
  it('requires two to five distinct exact keys without shortening saved selections', () => {
    expect(coMentionKeyError(['a', 'b'])).toBe('')
    expect(coMentionKeyError(['a', 'a'])).toContain('distinct')
    expect(coMentionKeyError(['a', ''])).toContain('exact key')
    expect(coMentionKeyError(['a', 'b', 'c', 'd', 'e', 'f'])).toContain('not been silently shortened')
  })
  it('keeps document elements distinct and derives only supported destinations from explicit fields', () => {
    const row = { record_type: 'document', record_id: 'doc&1', element_id: 'el=1', link: 'javascript:alert(1)' }
    expect(coMentionIdentity(row)).not.toBe(coMentionIdentity({ ...row, element_id: 'el=2' }))
    expect(coMentionDestination(row)).toEqual({ path: '/documents', query: { doc: 'doc&1', el: 'el=1' } })
    expect(coMentionDestination({ record_type: 'procurement_notice', record_id: 'notice' })).toEqual({ path: '/contracts' })
    expect(coMentionIdentity({ record_id: 'missing-type' })).toBeUndefined()
  })
})
