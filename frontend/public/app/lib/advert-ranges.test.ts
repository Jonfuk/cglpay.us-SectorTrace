import { describe, expect, it } from 'vitest'
import { advertRanges, drawableAdvert } from './advert-ranges'

describe('annual advert intervals', () => {
  it('preserves source order, periods, zero and missing bounds without conversions', () => {
    const rows = [
      { salary_period: 'year', salary_min: 0, salary_max: 30000 },
      { salary_period: 'hour', salary_min: 12, salary_max: 15 },
      { salary_period: null, salary_min: 30000, salary_max: 40000 },
      { salary_period: 'annum', salary_min: null, salary_max: 42000 },
      { salary_period: 'year', salary_min: 31000, salary_max: null },
    ]
    const result = advertRanges(rows)
    expect(result.map(row => row.state)).toEqual(['range', 'other-period', 'other-period', 'upper-only', 'lower-only'])
    expect(result[0]?.lower).toBe(0)
    expect(result[3]?.lower).toBeNull()
    expect(result[4]?.upper).toBeNull()
    expect(result.map(row => row.row)).toEqual(rows)
  })
  it('does not repair reversed bounds or coerce suppressed and malformed values', () => {
    const result = advertRanges([
      { salary_period: 'year', salary_min: 40000, salary_max: 30000 },
      { salary_period: 'year', salary_min: null, salary_max: '[suppressed]' },
      { salary_period: 'year', salary_min: Infinity, salary_max: '30000' },
      { salary_period: 'year', salary_min: 30000, salary_max: 30000 },
    ])
    expect(result.map(row => row.state)).toEqual(['reversed', 'missing', 'missing', 'single'])
    expect(result.map(drawableAdvert)).toEqual([false, false, false, true])
    expect(result[0]).toMatchObject({ lower: 40000, upper: 30000 })
  })
})
