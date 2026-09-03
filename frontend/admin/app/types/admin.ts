// Typed shapes for the admin `/api/admin` and admin-context read endpoints.
// These live ONLY in the admin app — the public app has no access to them.
// Only the fields the admin routes render are named; the rest survive on the
// index signatures, and are verified against the server in Phase 7.

/** `/api/admin/health` — operator warehouse/extension/graph/document status. */
export interface HealthResponse {
  warehouse?: {
    backend?: string
    path?: string
    bytes?: number
    applied_migrations?: string[]
    unapplied?: string[]
    [key: string]: unknown
  }
  extensions?: Array<{ name: string; installed: boolean; [key: string]: unknown }>
  graph?: Record<string, unknown>
  documents?: Record<string, unknown>
  [key: string]: unknown
}

/** `/api/admin/modules` — module cursors and review/parse-failure counts. */
export interface ModulesResponse {
  cursors?: Array<Record<string, unknown>>
  review_queue?: Array<{ module: string; n: number }>
  parse_failures?: Array<{ module: string; n: number }>
  [key: string]: unknown
}

/** One candidate kind's counts (`/api/admin/candidates/counts` → `kinds[]`). */
export interface CandidateKindCount {
  candidate_table: string
  target_table: string
  total: number
  promoted: number
  rejected: number
  undecided: number
  [key: string]: unknown
}

export interface CandidateCountsResponse {
  kinds: Record<string, CandidateKindCount>
  promotions?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/** A candidate listing item (`/api/admin/candidates` → `items[]`). */
export interface CandidateItem {
  url: string | null
  authority_ons_code: string | null
  authority_name: string | null
  verified: number
  rejected: number
  summary?: Record<string, unknown>
  discovered?: Record<string, unknown>
  [key: string]: unknown
}

export interface CandidatesListingResponse {
  kind: string
  status: string
  total: number
  offset: number
  limit: number
  items: CandidateItem[]
  requires?: string[]
  [key: string]: unknown
}

/** `/api/admin/analysis/overview` — the analysis platform overview. */
export interface AnalysisOverviewResponse {
  active_release: Record<string, unknown> | null
  counts?: Record<string, unknown>
  domains?: Array<Record<string, unknown>>
  latest_run?: Record<string, unknown> | null
  executor?: string
  worker?: Record<string, unknown>
  quality_boundary?: string
  [key: string]: unknown
}

/** A review-queue item (`/api/review` → `items[]`). */
export interface ReviewItem {
  id: number
  module: string | null
  item_type: string | null
  raw_value: string | null
  status: string | null
  [key: string]: unknown
}

export interface ReviewItemsResponse {
  items: ReviewItem[]
  total: number
  status?: string
  [key: string]: unknown
}
