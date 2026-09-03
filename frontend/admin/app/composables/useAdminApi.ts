import { Transport, type TransportOptions } from '~/lib/transport'
import type {
  AnalysisOverviewResponse,
  CandidateCountsResponse,
  CandidatesListingResponse,
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
  }
}
