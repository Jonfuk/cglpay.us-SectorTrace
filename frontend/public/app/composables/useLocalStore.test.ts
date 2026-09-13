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
    // Restored explicitly rather than relying on the afterEach's
    // restoreAllMocks: a spy on the Storage host object's own method
    // survives into the next test under Vitest 5 unless mockRestore() is
    // called before the test ends, so the next test's own setItem call
    // (line 17 below) would otherwise inherit this throw.
    const setItem = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new DOMException('Quota exceeded') })
    try {
      expect(useLocalStore('st.saved', 1, () => []).write([])).toBe(false)
    } finally {
      setItem.mockRestore()
    }
  })
  it('does not overwrite an unreadable saved record when reading', () => {
    localStorage.setItem('st.saved', 'broken JSON')
    expect(useLocalStore('st.saved', 1, () => []).read()).toEqual([])
    expect(localStorage.getItem('st.saved')).toBe('broken JSON')
  })
})
