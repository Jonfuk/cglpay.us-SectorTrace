import { Transport, type TransportOptions } from '~/lib/transport'
import type { MetaResponse } from '~/types/api'

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
}

export function usePublicApi(): PublicApi {
  const t = transport()
  const get = <T>(path: string, options?: TransportOptions): Promise<T> =>
    t.getJson<T>(`/api/v1${path}`, options)

  return {
    get,
    meta: (options) => get<MetaResponse>('/meta', options),
  }
}
