import type { PayRow } from './pay-lenses'

export interface AdvertRange {
  row: PayRow
  index: number
  lower: number | null
  upper: number | null
  state: 'range' | 'single' | 'lower-only' | 'upper-only' | 'missing' | 'reversed' | 'other-period'
  explanation: string
}
const numeric = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
const amount = (value: number) => value.toLocaleString('en-GB', { maximumSignificantDigits: 21 })

// Only the collector's explicit annual periods share this axis. In particular,
// no hours assumption, zero default or repaired interval enters the drawing.
export function advertRanges(rows: PayRow[]): AdvertRange[] {
  return rows.map((row, index) => {
    const lower = numeric(row.salary_min)
    const upper = numeric(row.salary_max)
    const common = { row, index, lower, upper }
    if (row.salary_period !== 'year' && row.salary_period !== 'annum') return { ...common, state: 'other-period', explanation: `Not plotted on the annual axis. Source period: ${row.salary_period ?? 'not supplied'}.` }
    if (lower === null && upper === null) return { ...common, state: 'missing', explanation: 'No numeric bounds supplied. No mark is drawn.' }
    if (lower !== null && upper !== null && lower > upper) return { ...common, state: 'reversed', explanation: `Bounds are reversed in the source: minimum ${amount(lower)}, maximum ${amount(upper)}. No interval is drawn.` }
    if (lower === null) return { ...common, state: 'upper-only', explanation: `Maximum ${amount(upper!)}. Minimum not supplied. An open diamond marks the maximum only.` }
    if (upper === null) return { ...common, state: 'lower-only', explanation: `Minimum ${amount(lower)}. Maximum not supplied. An open diamond marks the minimum only.` }
    if (lower === upper) return { ...common, state: 'single', explanation: `Published amount ${amount(lower)}. A filled dot marks the equal bounds.` }
    return { ...common, state: 'range', explanation: `Published minimum ${amount(lower)} to maximum ${amount(upper)}.` }
  })
}
export function drawableAdvert(range: AdvertRange) { return ['range', 'single', 'lower-only', 'upper-only'].includes(range.state) }
