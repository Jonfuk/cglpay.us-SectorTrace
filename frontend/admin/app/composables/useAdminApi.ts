import { Transport, type TransportOptions } from '~/lib/transport'
import type {
  AnalysisOverviewResponse,
  CandidateCountsResponse,
  CandidatesListingResponse,
  CensusListingResponse,
  HealthResponse,
  ModulesResponse,
  ReviewItemsResponse,
} from '~/types/admin'

// The typed admin API client. Separate from the public client by construction:
// it lives only in the admin app and may reach `/api/admin/*` (operator
// endpoints) as well as reading `/api/v1/*` and the admin-context `/api/*`
// endpoints. The public app has no access to this module.
//
// One Transport instance per app (module singleton) so the in-flight dedup map
// is shared across every caller.

let _transport: Transport | null = null

function transport(): Transport {
  if (!_transport) {
    const base = useRuntimeConfig().public.apiBase || ''
    _transport = new Transport(base)
  }
  return _transport
}

export interface AdminApi {
  /** Operator endpoints under `/api/admin`. */
  admin<T>(path: string, options?: TransportOptions): Promise<T>
  /** Read-only public endpoints the operator UI also consumes. */
  v1<T>(path: string, options?: TransportOptions): Promise<T>
  /** Admin-context top-level endpoints (e.g. `/api/review`). */
  api<T>(path: string, options?: TransportOptions): Promise<T>

  /** `/api/admin/health` — warehouse/extension/graph/document status. */
  health(options?: TransportOptions): Promise<HealthResponse>
  /** `/api/admin/modules` — module cursors and review/parse counts. */
  modules(options?: TransportOptions): Promise<ModulesResponse>
  /** `/api/admin/candidates/counts` — per-kind candidate counts. */
  candidateCounts(options?: TransportOptions): Promise<CandidateCountsResponse>
  /** `/api/admin/candidates` — one page of a candidate kind's items. */
  candidates(options?: TransportOptions): Promise<CandidatesListingResponse>
  /** `/api/admin/analysis/overview` — analysis platform overview. */
  analysisOverview(options?: TransportOptions): Promise<AnalysisOverviewResponse>
  /** `/api/review` — the review queue. */
  reviewItems(options?: TransportOptions): Promise<ReviewItemsResponse>
  /** `/api/admin/census` — census metric rows awaiting verification. */
  census(options?: TransportOptions): Promise<CensusListingResponse>

  // --- Writes. Each records a named human; nothing is promoted without one. ---

  /** Promote ONE candidate into the evidence base. One, never a list — the act
   *  recorded is that a person opened this document. This fetches the document
   *  from the open web, so it is never retried. */
  promoteCandidate(input: { kind: string; url: string; promotedBy: string; fields?: Record<string, unknown> }): Promise<unknown>
  /** Reject one candidate with a reason. */
  rejectCandidate(input: { kind: string; url: string; rejectedBy: string; note?: string }): Promise<unknown>
  /** Decide one review-queue item. */
  decideReview(input: { id: number; decision: string; decidedBy: string; note?: string }): Promise<unknown>
  /** Verify one census row. */
  verifyCensus(input: { key: string; verifiedBy: string; note?: string }): Promise<unknown>
  /** Reject one census row. */
  rejectCensus(input: { key: string; rejectedBy: string; note?: string }): Promise<unknown>
}

export function useAdminApi(): AdminApi {
  const t = transport()
  const admin = <T>(path: string, options?: TransportOptions) =>
    t.getJson<T>(`/api/admin${path}`, options)
  const v1 = <T>(path: string, options?: TransportOptions) =>
    t.getJson<T>(`/api/v1${path}`, options)
  const api = <T>(path: string, options?: TransportOptions) =>
    t.getJson<T>(`/api${path}`, options)

  return {
    admin,
    v1,
    api,
    health: (options) => admin<HealthResponse>('/health', options),
    modules: (options) => admin<ModulesResponse>('/modules', options),
    candidateCounts: (options) => admin<CandidateCountsResponse>('/candidates/counts', options),
    candidates: (options) => admin<CandidatesListingResponse>('/candidates', options),
    analysisOverview: (options) => admin<AnalysisOverviewResponse>('/analysis/overview', options),
    reviewItems: (options) => api<ReviewItemsResponse>('/review', options),
    census: (options) => admin<CensusListingResponse>('/census', options),

    promoteCandidate: (input) =>
      t.postJson('/api/admin/candidates/promote', {
        kind: input.kind,
        url: input.url,
        promoted_by: input.promotedBy,
        ...(input.fields ? { fields: input.fields } : {}),
      }),
    rejectCandidate: (input) =>
      t.postJson('/api/admin/candidates/reject', {
        kind: input.kind,
        url: input.url,
        rejected_by: input.rejectedBy,
        ...(input.note ? { note: input.note } : {}),
      }),
    decideReview: (input) =>
      t.postJson('/api/review/decide', {
        id: input.id,
        decision: input.decision,
        decided_by: input.decidedBy,
        ...(input.note ? { note: input.note } : {}),
      }),
    verifyCensus: (input) =>
      t.postJson('/api/admin/census/verify', {
        key: input.key,
        verified_by: input.verifiedBy,
        ...(input.note ? { note: input.note } : {}),
      }),
    rejectCensus: (input) =>
      t.postJson('/api/admin/census/reject', {
        key: input.key,
        rejected_by: input.rejectedBy,
        ...(input.note ? { note: input.note } : {}),
      }),
  }
}
