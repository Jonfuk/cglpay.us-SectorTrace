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
  modules?: ModuleRow[]
  waves?: number
  cursors?: Array<Record<string, unknown>>
  review_queue?: Array<{ module: string; n: number }>
  parse_failures?: Array<{ module: string; n: number }>
  [key: string]: unknown
}

export interface ModuleRow {
  name: string
  wave?: number | null
  supports_since?: boolean
  since_note?: string | null
  depends_on?: string[]
  depends_note?: string | null
  missing_dependencies?: string[]
  cursor_value?: string | null
  cursor_updated_at?: string | null
  pending_review?: number
  parse_failures?: number
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

/** A census metric row awaiting verification (`/api/admin/census` → `items[]`). */
export interface CensusItem {
  key: string
  census_year: number | null
  metric: string | null
  workforce_segment: string | null
  value: number | string | null
  unit: string | null
  raw_text: string | null
  verified: number
  rejected: number
  source?: { source_url?: string | null; retrieved_at?: string | null }
  [key: string]: unknown
}

export interface CensusListingResponse {
  status: string
  year: number | null
  total: number
  offset: number
  limit: number
  items: CensusItem[]
  [key: string]: unknown
}

/** A pipeline job head (`/api/admin/jobs` → `jobs[]`). */
export interface JobHead {
  id: number
  kind: string | null
  label: string | null
  state: string | null
  started_at: string | null
  finished_at: string | null
  error: string | null
  running: boolean
  [key: string]: unknown
}

export interface JobsResponse {
  jobs: JobHead[]
  running: number | null
  [key: string]: unknown
}

/** A run-ledger row (`/api/admin/runs` → `runs[]`). */
export interface RunRow {
  run_id: string | null
  origin: string | null
  status: string | null
  started_at: string | null
  finished_at: string | null
  modules_ok: number | null
  modules_failed: number | null
  [key: string]: unknown
}

export interface RunsResponse {
  runs: RunRow[]
  [key: string]: unknown
}

/** An export file (`/api/admin/exports` → `files[]`). */
export interface ExportFile {
  name?: string
  path?: string
  size?: number
  bytes?: number
  group?: string
  modified?: string
  provenance?: string | null
  [key: string]: unknown
}

export interface ExportsResponse {
  files: ExportFile[]
  staleness?: unknown
  [key: string]: unknown
}

/** `/api/admin/search` — operator semantic/lexical search results. */
export interface AdminSearchResponse {
  results?: Array<Record<string, unknown>>
  hits?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/** A claim candidate awaiting adjudication (`/api/admin/claim-candidates`). */
export interface ClaimCandidate {
  claim_candidate_id: string
  predicate: string | null
  subject_hint: string | null
  object_literal: string | null
  object_concept_id: string | null
  assertion_status: string | null
  evidence_span: string | null
  status: string | null
  created_at: string | null
  [key: string]: unknown
}

export interface ClaimCandidatesResponse {
  candidates: ClaimCandidate[]
  total: number
  caveat?: string
  [key: string]: unknown
}

/** A citation returned by the operator claims worklist. `resolved` is null
 * when a later module run replaced the cited evidence row. */
export interface ClaimCitation {
  id?: number
  claim_id?: number
  evidence_table: string
  evidence_key: string
  cited_by: string
  cited_at: string
  note?: string | null
  resolved?: {
    label?: string | null
    url?: string | null
    source_url?: string | null
    retrieved_at?: string | null
  } | null
  [key: string]: unknown
}

export interface ClaimDecision {
  id?: number
  claim_id?: number
  decision: string
  decided_by: string
  decided_at: string
  note?: string | null
  [key: string]: unknown
}

export interface Claim {
  id: number
  claim_text: string
  status: 'draft' | 'published' | 'rejected' | 'retracted' | string
  caveats: string | null
  created_by: string
  created_at: string
  note?: string | null
  citations: ClaimCitation[]
  decisions: ClaimDecision[]
  [key: string]: unknown
}

export interface ClaimsResponse {
  status: string
  total: number
  offset: number
  limit: number
  items: Claim[]
  [key: string]: unknown
}

export interface ClaimCountsResponse {
  draft: number
  published: number
  rejected: number
  retracted: number
  total: number
  decisions?: ClaimDecision[]
  [key: string]: unknown
}

export interface ClaimEvidenceRow {
  key: string
  label: string
  url?: string | null
  [key: string]: unknown
}

export interface ClaimEvidenceResponse {
  tables: string[]
  rows: ClaimEvidenceRow[]
  [key: string]: unknown
}

/** `/api/admin/cockpit` — prioritised, operational next actions. */
export interface CockpitCard {
  key: string
  title: string
  priority: number
  metric: number
  reason: string
  link: string
  [key: string]: unknown
}

export interface CockpitResponse {
  cards: CockpitCard[]
  priority_labels?: Record<string, string>
  top_priority?: number
  attention?: number
  note?: string
  [key: string]: unknown
}

/** `/api/admin/mission-control` — module waves and durable run state. */
export interface MissionControlModule {
  name: string
  depends_on?: string[]
  missing_dependencies?: string[]
  pending_review?: number
  parse_failures?: number
  cursor_updated_at?: string | null
  last_run?: { status?: string | null; [key: string]: unknown } | null
  [key: string]: unknown
}

export interface MissionControlResponse {
  wave_count?: number
  waves?: Array<{ wave: number; modules: MissionControlModule[] }>
  active?: JobHead | null
  queued?: JobHead[]
  last_run?: RunRow | null
  history?: RunRow[]
  failure_summary?: Array<{ module: string; parse_failures: number; pending_review: number; last_status?: string | null }>
  never_run?: string[]
  note?: string
  [key: string]: unknown
}

/** `/api/admin/jobs/{id}` — a job head plus its bounded log window. */
export interface JobDetail extends JobHead {
  log?: Array<{ at?: string; level?: string; text?: string }>
  next?: number
  summary?: Array<Record<string, unknown>>
  args?: Record<string, unknown>
  dropped?: number
}

export interface FreshnessRow {
  table: string
  rows: number
  newest?: string | null
  oldest?: string | null
  [key: string]: unknown
}

export interface StorageRow {
  path: string
  backend?: string | null
  files?: number
  bytes?: number
  exists?: boolean
  newest?: string | null
  mirror_lag?: { objects?: number; bytes?: number } | null
  note?: string
  [key: string]: unknown
}

export interface CoverageResponse {
  tier?: string
  authority_count?: number
  upper_tier_types?: string[]
  columns?: Array<{ label: string; table: string; module: string; covered?: number; missing?: boolean }>
  authorities?: Array<{ ons_code: string; name: string; region?: string | null; cells: Record<string, number> }>
  [key: string]: unknown
}

export interface FailuresResponse {
  modules?: string[]
  groups?: Array<{ n: number; module: string; field_name?: string | null; reason?: string | null }>
  rows?: Array<{ raw_fragment?: string | null; module: string; field_name?: string | null; reason?: string | null; source_url?: string | null }>
  [key: string]: unknown
}
