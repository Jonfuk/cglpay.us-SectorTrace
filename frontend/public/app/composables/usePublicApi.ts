import { Transport, type TransportOptions } from '~/lib/transport'
import type {
  AuthorityResponse,
  CalendarResponse,
  CatalogueResponse,
  ChangesResponse,
  ClaimsResponse,
  CompareResponse,
  CooccurrenceResponse,
  DocumentTablesResponse,
  ContractsResponse,
  CoverageResponse,
  CqcResponse,
  DiaryResponse,
  DiscrepancyResponse,
  DocumentSearchResponse,
  GeographyResponse,
  MetaResponse,
  PathResponse,
  PayResponse,
  PfdResponse,
  ProviderRow,
  ProvidersResponse,
  ProviderTimelineResponse,
  RelationshipsResponse,
  SummaryResponse,
  TreatmentResponse,
} from '~/types/api'

// The typed public API client. It sits over the low-level same-origin
// Transport (dedup + cancellation) and exposes evidence-shaped, typed calls.
//
// Isolation rule (Phase 6 portal isolation, unchanged): this client speaks only
// to `/api/v1/*`. It must never reference `/api/admin/*`, restricted schemas, or
// operator-only endpoints. The admin app has its own separate client.
//
// One Transport instance per app (module singleton) so the in-flight dedup map
// is shared across every caller in the public surface.

let _transport: Transport | null = null

function transport(): Transport {
  if (!_transport) {
    const base = useRuntimeConfig().public.apiBase || ''
    _transport = new Transport(base)
  }
  return _transport
}

export interface PublicApi {
  /** Raw typed GET for endpoints not yet given a dedicated method. Path is
   *  relative to `/api/v1`. */
  get<T>(path: string, options?: TransportOptions): Promise<T>
  /** `/api/v1/meta` — release and data-version identity. */
  meta(options?: TransportOptions): Promise<MetaResponse>
  /** `/api/v1/summary` — landing-page figures with their caveats. */
  summary(options?: TransportOptions): Promise<SummaryResponse>
  /** `/api/v1/pay` — separate pay-evidence arrays with caveats. */
  pay(options?: TransportOptions): Promise<PayResponse>
  /** `/api/v1/contracts` — procurement notices and rollups. */
  contracts(options?: TransportOptions): Promise<ContractsResponse>
  /** `/api/v1/providers` — every provider with comparable counts. */
  providers(options?: TransportOptions): Promise<ProvidersResponse>
  /** `/api/v1/geography` — one value per authority for a chosen metric. */
  geography(options?: TransportOptions): Promise<GeographyResponse>
  /** `/api/v1/treatment_metrics` — the treatment metric catalogue. */
  treatment(options?: TransportOptions): Promise<TreatmentResponse>
  /** `/api/v1/catalogue` — every dataset served, with counts and freshness. */
  catalogue(options?: TransportOptions): Promise<CatalogueResponse>
  /** `/api/v1/document_search` — full-text document search (requires `q`). */
  documentSearch(options?: TransportOptions): Promise<DocumentSearchResponse>
  /** `/api/v1/pfd` — coroners' Prevention of Future Deaths corpus. */
  pfd(options?: TransportOptions): Promise<PfdResponse>
  /** `/api/v1/claims` — published claims with citations and caveats. */
  claims(options?: TransportOptions): Promise<ClaimsResponse>
  /** `/api/v1/cqc_locations` — CQC-registered locations. */
  cqc(options?: TransportOptions): Promise<CqcResponse>
  /** `/api/v1/relationships` — entity relationship neighbourhood. */
  relationships(options?: TransportOptions): Promise<RelationshipsResponse>
  /** `/api/v1/changes` — recorded warehouse change chronology. */
  changes(options?: TransportOptions): Promise<ChangesResponse>
  /** `/api/v1/publication_calendar` — per-source release cadence and status. */
  calendar(options?: TransportOptions): Promise<CalendarResponse>
  /** `/api/v1/providers/{key}/timeline` — a provider's dated event timeline. */
  providerTimeline(key: string, options?: TransportOptions): Promise<ProviderTimelineResponse>
  /** `/api/v1/coverage_timeline` — which datasets hold an entity, and when. */
  coverage(options?: TransportOptions): Promise<CoverageResponse>
  /** `/api/v1/contract_diary` — an entity's dated procurement events. */
  diary(options?: TransportOptions): Promise<DiaryResponse>
  /** `/api/v1/discrepancies` — identity-field differences across sources. */
  discrepancies(options?: TransportOptions): Promise<DiscrepancyResponse>
  /** `/api/v1/compare` — parallel series for two or more entities. */
  compare(options?: TransportOptions): Promise<CompareResponse>
  /** `/api/v1/relationship_path` — shortest verified path between two entities. */
  relationshipPath(options?: TransportOptions): Promise<PathResponse>
  /** `/api/v1/authorities/{ons_code}` — one authority's full payload. */
  authority(code: string, options?: TransportOptions): Promise<AuthorityResponse>
  /** `/api/v1/cooccurrence` — records naming selected entities together. */
  cooccurrence(options?: TransportOptions): Promise<CooccurrenceResponse>
  /** `/api/v1/document_tables` — extracted tables for one document. */
  documentTables(options?: TransportOptions): Promise<DocumentTablesResponse>
}

export function usePublicApi(): PublicApi {
  const t = transport()
  const get = <T>(path: string, options?: TransportOptions): Promise<T> =>
    t.getJson<T>(`/api/v1${path}`, options)

  return {
    get,
    meta: (options) => get<MetaResponse>('/meta', options),
    summary: (options) => get<SummaryResponse>('/summary', options),
    pay: (options) => get<PayResponse>('/pay', options),
    contracts: (options) => get<ContractsResponse>('/contracts', options),
    providers: (options) => get<ProvidersResponse>('/providers', options),
    geography: (options) => get<GeographyResponse>('/geography', options),
    treatment: (options) => get<TreatmentResponse>('/treatment_metrics', options),
    catalogue: (options) => get<CatalogueResponse>('/catalogue', options),
    documentSearch: (options) => get<DocumentSearchResponse>('/document_search', options),
    pfd: (options) => get<PfdResponse>('/pfd', options),
    claims: (options) => get<ClaimsResponse>('/claims', options),
    cqc: (options) => get<CqcResponse>('/cqc_locations', options),
    relationships: (options) => get<RelationshipsResponse>('/relationships', options),
    changes: (options) => get<ChangesResponse>('/changes', options),
    calendar: (options) => get<CalendarResponse>('/publication_calendar', options),
    providerTimeline: (key, options) =>
      get<ProviderTimelineResponse>(`/providers/${encodeURIComponent(key)}/timeline`, options),
    coverage: (options) => get<CoverageResponse>('/coverage_timeline', options),
    diary: (options) => get<DiaryResponse>('/contract_diary', options),
    discrepancies: (options) => get<DiscrepancyResponse>('/discrepancies', options),
    compare: (options) => get<CompareResponse>('/compare', options),
    authority: (code, options) =>
      get<AuthorityResponse>(`/authorities/${encodeURIComponent(code)}`, options),
    cooccurrence: (options) => get<CooccurrenceResponse>('/cooccurrence', options),
    documentTables: (options) => get<DocumentTablesResponse>('/document_tables', options),
    relationshipPath: (options) => get<PathResponse>('/relationship_path', options),
  }
}
