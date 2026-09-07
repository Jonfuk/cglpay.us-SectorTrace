import type { TreatmentMetric } from './api'

export type TreatmentRow = Record<string, unknown>
export interface TreatmentCatalogue { metrics?: TreatmentMetric[]; count?: number; caveat?: string | null }
export interface FingertipsPayload {
  indicators?: TreatmentRow[]
  series?: TreatmentRow[]
  england_series?: TreatmentRow[]
  caveat?: string | null
}
export interface NdtmsPayload {
  datasets?: TreatmentRow[]
  publications?: TreatmentRow[]
  estimates?: TreatmentRow[]
  other_rows?: TreatmentRow[]
  authority?: { ons_code?: string; name?: string | null } | null
  caveats?: Record<string, string | null>
}
export type TreatmentLane = 'local' | 'england' | 'estimates' | 'context'
export interface TreatmentObservation {
  row: TreatmentRow
  lane: TreatmentLane
  key: string
  label: string
  period: string
  value: number | null
  lower: number | null
  upper: number | null
  interval: boolean
  intervalNote: string
}
