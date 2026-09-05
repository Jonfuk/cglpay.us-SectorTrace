export type ReviewDecision = 'approved' | 'rejected' | 'pending'
export interface ReviewDecisionInput {
  ids: number[]
  decision: ReviewDecision
  decided_by: string
  note: string | null
}
export interface ReviewDecisionResult {
  updated: number[]
  unchanged: number[]
  missing: number[]
}
export interface PositionalResult {
  columns: string[]
  rows: unknown[][]
  truncated?: boolean
  total?: number
}
export interface MatchingDecisionInput {
  decision: ReviewDecision
  decided_by: string
  confirm_count: number
  note: string | null
  status?: string | number
  module?: string | number
  item_type?: string | number
  search?: string | number
}
