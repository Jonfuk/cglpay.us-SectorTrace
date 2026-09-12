import { describe, expect, it } from 'vitest'
import { noticeCounts, selectedYears } from './notice-counts'
describe('notice count evidence', () => {
  it('retains supplied zero and missing values without filling years or summing values', () => {
    expect(noticeCounts([{ year: '2023', count: 0, value_gbp: 9000000 }, { year: '2025', count: null }, { year: '2026', count: '7' }], 'year')).toEqual([
      { key: '0:2023', label: '2023', value: 0 }, { key: '1:2025', label: '2025', value: null }, { key: '2:2026', label: '2026', value: null },
    ])
  })
  it('maps a year selection to supported publication bounds without making quarter filters', () => {
    const rows = noticeCounts([{ year: '2026', count: 2 }, { year: '2024', count: 1 }, { year: '2025-Q1', count: 4 }], 'year')
    expect(selectedYears(rows, [0, 1])).toEqual(['2024', '2026'])
    expect(selectedYears(rows, [2, 44])).toBeNull()
  })
})
