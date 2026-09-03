import { Transport, type TransportOptions } from '~/lib/transport'
import type {
  CatalogueResponse,
  ContractsResponse,
  DocumentSearchResponse,
  GeographyResponse,
  MetaResponse,
  PayResponse,
  ProviderRow,
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
  providers(options?: TransportOptions): Promise<ProviderRow[]>
  /** `/api/v1/geography` — one value per authority for a chosen metric. */
  geography(options?: TransportOptions): Promise<GeographyResponse>
  /** `/api/v1/treatment_metrics` — the treatment metric catalogue. */
  treatment(options?: TransportOptions): Promise<TreatmentResponse>
  /** `/api/v1/catalogue` — every dataset served, with counts and freshness. */
  catalogue(options?: TransportOptions): Promise<CatalogueResponse>
  /** `/api/v1/document_search` — full-text document search (requires `q`). */
  documentSearch(options?: TransportOptions): Promise<DocumentSearchResponse>
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
    providers: (options) => get<ProviderRow[]>('/providers', options),
    geography: (options) => get<GeographyResponse>('/geography', options),
    treatment: (options) => get<TreatmentResponse>('/treatment_metrics', options),
    catalogue: (options) => get<CatalogueResponse>('/catalogue', options),
    documentSearch: (options) => get<DocumentSearchResponse>('/document_search', options),
  }
}
