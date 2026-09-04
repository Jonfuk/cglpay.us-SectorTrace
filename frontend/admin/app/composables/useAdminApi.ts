import { Transport, type TransportOptions } from '~/lib/transport'
import type {
  AnalysisOverviewResponse,
  CockpitResponse,
  CandidateCountsResponse,
  CandidatesListingResponse,
  AdminSearchResponse,
  ClaimCandidatesResponse,
  ClaimCountsResponse,
  ClaimEvidenceResponse,
  ClaimsResponse,
  CensusListingResponse,
  ExportsResponse,
  HealthResponse,
  MissionControlResponse,
  FreshnessRow,
  StorageRow,
  CoverageResponse,
  FailuresResponse,
  JobDetail,
  JobsResponse,
  RunsResponse,
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
  /** `/api/admin/cockpit` — prioritised operational actions. */
  cockpit(options?: TransportOptions): Promise<CockpitResponse>
  /** `/api/admin/mission-control` — module waves and run state. */
  missionControl(options?: TransportOptions): Promise<MissionControlResponse>
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
  /** `/api/admin/jobs` — in-process job heads. */
  jobs(options?: TransportOptions): Promise<JobsResponse>
  job(id: number, options?: TransportOptions): Promise<JobDetail>
  /** `/api/admin/runs` — the durable run ledger. */
  runs(options?: TransportOptions): Promise<RunsResponse>
  runLedger(options?: TransportOptions): Promise<RunsResponse>
  freshness(options?: TransportOptions): Promise<{ freshness: FreshnessRow[]; snapshot?: unknown }>
  storage(options?: TransportOptions): Promise<{ storage: StorageRow[]; snapshot?: unknown }>
  coverage(options?: TransportOptions): Promise<CoverageResponse>
  failures(options?: TransportOptions): Promise<FailuresResponse>
  /** `/api/admin/exports` — export files and staleness. */
  exports(options?: TransportOptions): Promise<ExportsResponse>
  /** `/api/admin/search` — operator semantic/lexical search. */
  search(options?: TransportOptions): Promise<AdminSearchResponse>
  /** `/api/admin/claim-candidates` — the claim adjudication queue. */
  claimCandidates(options?: TransportOptions): Promise<ClaimCandidatesResponse>
  /** `/api/admin/claims` — claims with resolved citation payloads. */
  claims(options?: TransportOptions): Promise<ClaimsResponse>
  /** `/api/admin/claims/counts` — claim lifecycle counts and decisions. */
  claimCounts(options?: TransportOptions): Promise<ClaimCountsResponse>
  /** `/api/admin/claims/evidence` — citable tables or matching rows. */
  claimEvidence(options?: TransportOptions): Promise<ClaimEvidenceResponse>

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
  /** Decide one claim candidate. */
  decideClaimCandidate(input: { claimCandidateId: string; decision: string; decidedBy: string }): Promise<unknown>
  /** Create one attributed draft claim. */
  createClaim(input: { claimText: string; caveats?: string; note?: string; createdBy: string }): Promise<unknown>
  /** Edit one draft claim. */
  updateClaim(input: { claimId: number; claimText: string; caveats?: string; note?: string }): Promise<unknown>
  /** Cite one citable evidence row. */
  citeClaim(input: { claimId: number; evidenceTable: string; evidenceKey: string; citedBy: string; note?: string }): Promise<unknown>
  /** Remove one citation from a draft. */
  unciteClaim(input: { claimId: number; evidenceTable: string; evidenceKey: string }): Promise<unknown>
  /** Decide one claim, preserving the server-side audit trail. */
  decideClaim(input: { claimId: number; decision: string; decidedBy: string; note?: string }): Promise<unknown>
  /** Return a decided claim to draft without deleting its history. */
  resetClaim(input: { claimId: number }): Promise<unknown>
  startRun(input: { module: string; since?: string; limit?: number; jobs?: number; dryRun?: boolean }): Promise<JobDetail>
  startIntegrityCheck(): Promise<JobDetail>
  startExport(target: string): Promise<JobDetail>
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
    cockpit: (options) => admin<CockpitResponse>('/cockpit', options),
    missionControl: (options) => admin<MissionControlResponse>('/mission-control', options),
    modules: (options) => admin<ModulesResponse>('/modules', options),
    candidateCounts: (options) => admin<CandidateCountsResponse>('/candidates/counts', options),
    candidates: (options) => admin<CandidatesListingResponse>('/candidates', options),
    analysisOverview: (options) => admin<AnalysisOverviewResponse>('/analysis/overview', options),
    reviewItems: (options) => api<ReviewItemsResponse>('/review', options),
    census: (options) => admin<CensusListingResponse>('/census', options),
    jobs: (options) => admin<JobsResponse>('/jobs', options),
    job: (id, options) => admin<JobDetail>(`/jobs/${id}`, options),
    runs: (options) => admin<RunsResponse>('/runs', options),
    runLedger: (options) => admin<RunsResponse>('/run-ledger', options),
    freshness: (options) => admin<{ freshness: FreshnessRow[]; snapshot?: unknown }>('/freshness', options),
    storage: (options) => admin<{ storage: StorageRow[]; snapshot?: unknown }>('/storage', options),
    coverage: (options) => admin<CoverageResponse>('/coverage', options),
    failures: (options) => admin<FailuresResponse>('/failures', options),
    exports: (options) => admin<ExportsResponse>('/exports', options),
    search: (options) => admin<AdminSearchResponse>('/search', options),
    claimCandidates: (options) => admin<ClaimCandidatesResponse>('/claim-candidates', options),
    claims: (options) => admin<ClaimsResponse>('/claims', options),
    claimCounts: (options) => admin<ClaimCountsResponse>('/claims/counts', options),
    claimEvidence: (options) => admin<ClaimEvidenceResponse>('/claims/evidence', options),

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
    decideClaimCandidate: (input) =>
      t.postJson('/api/admin/claim-candidates/decide', {
        claim_candidate_id: input.claimCandidateId,
        decision: input.decision,
        decided_by: input.decidedBy,
      }),
    createClaim: (input) =>
      t.postJson('/api/admin/claims/create', {
        claim_text: input.claimText,
        caveats: input.caveats || '',
        note: input.note || null,
        created_by: input.createdBy,
      }),
    updateClaim: (input) =>
      t.postJson('/api/admin/claims/update', {
        claim_id: input.claimId,
        claim_text: input.claimText,
        caveats: input.caveats || '',
        note: input.note || null,
      }),
    citeClaim: (input) =>
      t.postJson('/api/admin/claims/cite', {
        claim_id: input.claimId,
        evidence_table: input.evidenceTable,
        evidence_key: input.evidenceKey,
        cited_by: input.citedBy,
        note: input.note || null,
      }),
    unciteClaim: (input) =>
      t.postJson('/api/admin/claims/uncite', {
        claim_id: input.claimId,
        evidence_table: input.evidenceTable,
        evidence_key: input.evidenceKey,
      }),
    decideClaim: (input) =>
      t.postJson('/api/admin/claims/decide', {
        claim_id: input.claimId,
        decision: input.decision,
        decided_by: input.decidedBy,
        note: input.note || null,
      }),
    resetClaim: (input) =>
      t.postJson('/api/admin/claims/reset', { claim_id: input.claimId }),
    startRun: (input) =>
      t.postJson('/api/admin/run', {
        module: input.module,
        ...(input.since ? { since: input.since } : {}),
        ...(input.limit !== undefined ? { limit: input.limit } : {}),
        ...(input.jobs !== undefined ? { jobs: input.jobs } : {}),
        ...(input.dryRun ? { dry_run: true } : {}),
      }) as Promise<JobDetail>,
    startIntegrityCheck: () => t.postJson('/api/admin/check', {}) as Promise<JobDetail>,
    startExport: (target) => t.postJson('/api/admin/export', { target }) as Promise<JobDetail>,
  }
}
