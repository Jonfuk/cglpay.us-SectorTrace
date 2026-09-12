import { describe, expect, it } from 'vitest'
import { safetyCell, safetyChronology, safetyDate, safetyDateGroup, safetyLane, safetyRecordKey } from './safety'
describe('separate safety source records', () => {
  it('does not collapse a report addressed to and naming the same organisation', () => {
    const row = { source: 'pfd', entity_type: 'provider', entity_key: 'example', title: 'Report 1', date: '2026-03-12', source_url: 'https://example.invalid/report' }
    expect(safetyRecordKey(safetyLane('pfd'), { ...row, relationship: 'addressed_to' })).not.toBe(safetyRecordKey(safetyLane('pfd'), { ...row, relationship: 'named_in' }))
  })
  it('orders only complete valid dates and never dates a SAR by its library year', () => {
    expect(safetyDate('12 March 2026')).toBe(safetyDate('12/03/2026'))
    expect(safetyDate('31/02/2026')).toBeNull()
    expect(safetyDate('March 2026')).toBeNull()
    expect(safetyDate('2026')).toBeNull()
    expect(safetyDateGroup({ library_year: 2026 })).toBe('undated')
    const rows = [{ date: null, id: 'undated' }, { date: 'March 2026', id: 'partial' }, { date: '2025-12-31', id: 'older' }, { date: '12 March 2026', id: 'newer' }]
    expect(safetyChronology(rows, 'date').map(row => row.id)).toEqual(['newer', 'older', 'partial', 'undated'])
    expect(rows[0]?.id).toBe('undated')
  })
  it('preserves withdrawal text and distinguishes a stub from absence of concern', () => {
    expect(safetyCell('result', { result: 'Withdrawn following appeal' })).toBe('Withdrawn following appeal')
    expect(safetyCell('has_concerns', { has_concerns: 0 })).toBe('Metadata stub without concern text')
    expect(safetyCell('has_concerns', {})).toBe('Text availability not supplied')
    expect(safetyCell('library_year', { library_year: 2025 })).toBe('2025')
  })
})
