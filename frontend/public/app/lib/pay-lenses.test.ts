import { describe, expect, it } from 'vitest'
import { payCell, payLenses, payQuery, payRecordKey, payRows } from './pay-lenses'
const lens = (key: string) => payLenses.find(row => row.key === key)!
const filters = { provider_key: 'example', year_from: '2020', year_to: '2025', role: 'worker', pay_unit: 'hourly', source: 'published_statutory' }
describe('pay source boundaries', () => {
  it('keeps provider and account-year filters out of national evidence', () => {
    expect(payQuery(lens('census'), filters)).toEqual({ source: 'workforce_census', provider_key: undefined, year_from: undefined, year_to: undefined, role: 'worker', pay_unit: undefined })
    expect(payQuery(lens('adverts'), filters)).toEqual({ source: 'advertised_roles', provider_key: 'example', year_from: undefined, year_to: undefined, role: 'worker', pay_unit: 'hourly' })
    expect(payQuery(lens('charity'), filters)).toEqual({ source: 'indicative_wage', provider_key: 'example', year_from: '2020', year_to: '2025', role: undefined, pay_unit: undefined })
  })
  it('distinguishes absent arrays, absent values, supplied zero and suppression text', () => {
    expect(payRows({}, 'statutory_pay_rates')).toBeNull()
    expect(payRows({ statutory_pay_rates: [] }, 'statutory_pay_rates')).toEqual([])
    const column = { key: 'value', label: 'Published value', numeric: true }
    expect(payCell(column, { value: 0 })).toBe('0')
    expect(payCell(column, { value: null })).toBe('Not supplied')
    expect(payCell(column, { value: '[suppressed]' })).toBe('[suppressed]')
    expect(payCell(column, { value: 1e-22 })).not.toBe('0')
  })
  it('uses published field names and gives name checks and verification their limited meaning', () => {
    expect(lens('gender-gap').columns.map(row => row.key)).toContain('diff_mean_hourly_percent')
    expect(lens('ashe').columns.map(row => row.key)).toContain('unit_of_measure')
    expect(lens('published').columns.map(row => row.key)).toContain('mention_text')
    expect(payCell({ key: 'accredited', label: 'Check' }, { accredited: 0 })).toBe('No name match in this check')
    expect(payCell({ key: 'verified', label: 'Verification' }, { verified: 1 })).toBe('Transcription verified')
    expect(payCell({ key: 'source_page', label: 'Source page' }, { source_page: 0 })).toBe('1')
  })
  it('keeps employers with different source identifiers distinct even with the same provider name', () => {
    const common = { provider_key: 'example', reporting_year: 2025, source_url: 'https://example.invalid/source' }
    expect(payRecordKey(lens('gender-gap'), { ...common, employer_id: '1' })).not.toBe(payRecordKey(lens('gender-gap'), { ...common, employer_id: '2' }))
  })
})
