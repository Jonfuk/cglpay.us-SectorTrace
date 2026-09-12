import type { TreatmentMetric } from '~/types/api'
import type { TreatmentLane, TreatmentObservation, TreatmentRow } from '~/types/treatment'

export function treatmentTarget(metric: TreatmentMetric) {
  if (metric.source === 'fingertips' && typeof metric.indicator_id === 'number' && Number.isSafeInteger(metric.indicator_id) && metric.indicator_id > 0) return { endpoint: 'fingertips' as const, indicator_id: String(metric.indicator_id) }
  // treatment_metrics publishes this exact key format but no separate table_ref.
  // Decode only that source-defined prefix, never a human table label.
  if (metric.source === 'ndtms' && metric.key.startsWith('ndtms:') && metric.key.length > 6) return { endpoint: 'ndtms' as const, table_ref: metric.key.slice(6) }
  return null
}
export const treatmentNumber = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
export const treatmentText = (value: unknown) => value == null || value === '' ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value) : typeof value === 'number' ? value.toLocaleString('en-GB', { maximumSignificantDigits: 21 }) : String(value)
export const ndtmsCohort = (row: TreatmentRow) => JSON.stringify([row.measure ?? null, row.age_group ?? null])

export function treatmentObservation(row: TreatmentRow, lane: TreatmentLane): TreatmentObservation {
  const fingertips = lane === 'local' || lane === 'england'
  const value = treatmentNumber(row.value)
  const lower = treatmentNumber(fingertips ? row.lower_ci_95 : row.lower)
  const upper = treatmentNumber(fingertips ? row.upper_ci_95 : row.upper)
  const interval = lower !== null && upper !== null && lower <= upper
  const identifiers = fingertips ? ['indicator_id', 'ons_code', 'time_period', 'time_period_sortable', 'source_url'] : ['table_ref', 'measure', 'ons_code', 'time_period', 'age_group', 'published_in', 'source_url']
  let intervalNote = interval ? `Published 95% bounds: ${treatmentText(lower)} to ${treatmentText(upper)}.` : lower !== null && upper !== null ? 'The source bounds are reversed. No interval is drawn.' : 'Both numeric bounds are not supplied. No interval is drawn.'
  if (lane === 'england') intervalNote = 'The England response does not supply confidence bounds, source URL, retrieval date or hash.'
  if (!fingertips && row.has_interval === true && !interval) intervalNote += ' The source response marks a paired interval, but its numeric bounds cannot be plotted.'
  if (value === null) intervalNote += ' No numeric point value is supplied.'
  return { row, lane, key: JSON.stringify([lane, ...identifiers.map(key => row[key] ?? null)]), label: fingertips ? lane === 'england' ? 'England' : treatmentText(row.authority_name) : treatmentText(row.measure), period: treatmentText(row.time_period), value, lower, upper, interval, intervalNote }
}

export interface TreatmentSlot { label: string; observation: TreatmentObservation | null }
export function fingertipsSlots(observations: TreatmentObservation[], periods: unknown): { slots: TreatmentSlot[]; connect: boolean; scaffold: boolean } {
  const labels = observations.map(row => row.row.time_period)
  const unique = new Set(labels).size === labels.length
  const explicitPeriods = Array.isArray(periods) && periods.length > 0 && periods.every(period => typeof period === 'string' && period.length > 0) && new Set(periods).size === periods.length
  if (unique && explicitPeriods && labels.every(label => periods.includes(label))) {
    const byPeriod = new Map(observations.map(row => [row.row.time_period, row]))
    return { slots: periods.map(label => ({ label, observation: byPeriod.get(label) ?? null })), connect: true, scaffold: true }
  }
  // Duplicate/undated observations stay separate. They cannot choose a line's
  // chronology or replace each other simply because a period label matches.
  const sortValues = observations.map(row => treatmentNumber(row.row.time_period_sortable))
  const ordered = sortValues.every((value, index) => value !== null && (index === 0 || (sortValues[index - 1] !== null && value > sortValues[index - 1]!)))
  return { slots: observations.map(observation => ({ label: observation.period, observation })), connect: unique && ordered, scaffold: false }
}
