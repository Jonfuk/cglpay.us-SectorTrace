export interface CountObservation { key: string; label: string; value: number | null }
// Aggregate rows are already computed by the public API. Do not re-count the
// paginated notices, fill absent periods or turn an unparseable value into zero.
export function noticeCounts(rows: Record<string, unknown>[], field: string): CountObservation[] {
  return rows.map((row, index) => ({ key: `${index}:${String(row[field] ?? '')}`, label: row[field] == null ? 'Label not supplied' : String(row[field]), value: typeof row.count === 'number' && Number.isFinite(row.count) && row.count >= 0 ? row.count : null }))
}
export function selectedYears(rows: CountObservation[], indices: number[]): [string, string] | null {
  const years = indices.map(index => rows[index]?.label).filter((label): label is string => Boolean(label && /^\d{4}$/.test(label))).sort()
  return years.length ? [years[0]!, years.at(-1)!] : null
}
