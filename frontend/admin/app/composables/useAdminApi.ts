import { Transport, type TransportOptions } from '~/lib/transport'

// The typed admin API client. Separate from the public client by construction:
// it lives only in the admin app and may reach `/api/admin/*` (operator
// endpoints) as well as reading `/api/v1/*`. The public app has no access to
// this module. Admin health responses may carry extra performance/snapshot
// fields that the public `/api/v1` shapes do not.

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
}

export function useAdminApi(): AdminApi {
  const t = transport()
  return {
    admin: <T>(path: string, options?: TransportOptions) =>
      t.getJson<T>(`/api/admin${path}`, options),
    v1: <T>(path: string, options?: TransportOptions) =>
      t.getJson<T>(`/api/v1${path}`, options),
  }
}
