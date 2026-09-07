import { afterEach, describe, expect, it, vi } from 'vitest'
import { useLocalStore } from './useLocalStore'
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })
describe('browser persistence', () => {
  it('preserves the version-one envelope and reports a successful write', () => {
    localStorage.setItem('st.saved', JSON.stringify({ v: 1, data: [{ label: 'Existing view' }] }))
    const store = useLocalStore('st.saved', 1, () => [] as { label: string }[])
    expect(store.read()).toEqual([{ label: 'Existing view' }])
    expect(store.write([{ label: 'New view' }])).toBe(true)
    expect(JSON.parse(localStorage.getItem('st.saved')!)).toEqual({ v: 1, data: [{ label: 'New view' }] })
  })
  it('does not claim success when browser storage rejects writes', () => {
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new DOMException('Quota exceeded') })
    expect(useLocalStore('st.saved', 1, () => []).write([])).toBe(false)
  })
  it('does not overwrite an unreadable saved record when reading', () => {
    localStorage.setItem('st.saved', 'broken JSON')
    expect(useLocalStore('st.saved', 1, () => []).read()).toEqual([])
    expect(localStorage.getItem('st.saved')).toBe('broken JSON')
  })
})
