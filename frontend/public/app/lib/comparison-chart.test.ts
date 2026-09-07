import { describe, expect, it } from 'vitest'
import { comparisonMeasures, comparisonPoints } from './comparison-chart'
describe('comparison chart source fields', () => {
  it('keeps charity income and expenditure separate with source dates and duplicate periods', () => {
    const rows = [{ provider_key: 'a', financial_year_end: '2024-03-31', total_income: 0, total_expenditure: '20', amount: 999 }, { provider_key: 'b', total_income: 400 }, { provider_key: 'a', financial_year_end: '2024-03-31', total_income: 30, total_expenditure: null }]
    const points = comparisonPoints(rows, 'charity', 'a')
    expect(points.map(point => point.values)).toEqual([[0, null], [30, null]])
    expect(points.map(point => point.index)).toEqual([0, 2])
    expect(points[0]!.row).toBe(rows[0])
  })
  it('uses notice counts and never contract values as chart amounts', () => {
    expect(comparisonPoints([{ ons_code: 'a', year: 2025, count: 2, value_gbp: 9000 }], 'contracts', 'a')[0]).toMatchObject({ period: '2025', values: [2] })
    expect(comparisonPoints([{ provider_key: 'a', total_income: Number.POSITIVE_INFINITY }], 'charity', 'a')[0]!.values).toEqual([null, null])
    expect(comparisonMeasures('treatment')).toEqual([])
    expect(comparisonMeasures('nhs_jobs')).toEqual([])
  })
})
