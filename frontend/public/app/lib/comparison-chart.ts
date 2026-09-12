export interface ComparisonMeasure { key: string; label: string }
export interface ComparisonPoint { row: Record<string, unknown>; index: number; period: string; values: Array<number | null> }
export function comparisonMeasures(source: string): ComparisonMeasure[] {
  if (source === 'charity') return [{ key: 'total_income', label: 'Income' }, { key: 'total_expenditure', label: 'Expenditure' }]
  if (source === 'contracts' || source === 'provider_contracts') return [{ key: 'count', label: 'Published notices' }]
  if (source === 'grant') return [{ key: 'amount', label: 'Grant allocation' }]
  if (source === 'budget') return [{ key: 'amount', label: 'Budgeted public health spend' }]
  return []
}
export function comparisonPoints(rows: Record<string, unknown>[], source: string, peer: string): ComparisonPoint[] {
  const field = source === 'charity' || source === 'provider_contracts' ? 'provider_key' : 'ons_code'
  const period = source === 'charity' ? 'financial_year_end' : source === 'contracts' || source === 'provider_contracts' ? 'year' : 'financial_year'
  const measures = comparisonMeasures(source)
  // Each source row keeps its own slot, including repeated periods. Aggregating
  // duplicates here would invent an observation and lose its source identity.
  return rows.flatMap((row, index) => row[field] === peer ? [{ row, index, period: row[period] == null || row[period] === '' ? 'Period not supplied' : String(row[period]), values: measures.map(measure => typeof row[measure.key] === 'number' && Number.isFinite(row[measure.key]) ? row[measure.key] as number : null) }] : [])
}
