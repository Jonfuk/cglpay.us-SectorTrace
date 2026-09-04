import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StStat from './StStat.vue'

// StStat encodes the project's most important display invariant: a null or
// undefined value is "we do not have this" and must render as an em dash, NEVER
// as 0 — the two are different claims.
describe('StStat', () => {
  it('renders null and undefined as an em dash, not zero', () => {
    for (const value of [null, undefined]) {
      const w = mount(StStat, { props: { label: 'X', value }, global: { stubs: { StCaveat: true } } })
      expect(w.text()).toContain('—')
      expect(w.text()).not.toContain('0')
    }
  })

  it('renders a real zero as 0', () => {
    const w = mount(StStat, { props: { label: 'X', value: 0 }, global: { stubs: { StCaveat: true } } })
    expect(w.text()).toContain('0')
    expect(w.text()).not.toContain('—')
  })

  it('formats a number through toLocaleString (grouped where the runtime has ICU)', () => {
    const w = mount(StStat, { props: { label: 'X', value: 1234567 }, global: { stubs: { StCaveat: true } } })
    // Grouping separators depend on the runtime's ICU data (present in browsers,
    // sometimes absent in a minimal Node build), so accept either form — the
    // invariant under test is that the number renders, not the em dash.
    expect(w.text()).toMatch(/1,?234,?567/)
  })

  it('passes strings through unformatted', () => {
    const w = mount(StStat, { props: { label: 'X', value: '2024/25', format: false }, global: { stubs: { StCaveat: true } } })
    expect(w.text()).toContain('2024/25')
  })
})
