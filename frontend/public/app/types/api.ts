// Typed shapes for the public `/api/v1` surface.
//
// These MUST match the Python server's actual responses (pipeline/web/openapi.py
// and public_queries.py) and are verified against `/api/openapi.json` and
// representative fixtures in Phase 7. Public `/api/v1` success shapes are frozen
// by the roadmap: this file tracks them, it does not get to redefine them.
//
// The foundation stage types the endpoints the shell itself needs. Route
// payload types are added here as each route is ported, so the map of typed
// endpoints grows with real, verified coverage rather than speculative shapes.

/** `/api/v1/meta` — release + data identity. The public cache is kept
 *  subordinate to this: `schema.latest_migration` and `data.last_fetch_at`
 *  together form the data-version key that invalidates client caches. */
export interface MetaResponse {
  service: string
  environment: string
  revision: string | null
  revision_source: 'deployment' | 'checkout'
  build_time: string | null
  backend: string
  schema: {
    latest_migration: number | null
    applied_count: number
    migrated_at: string | null
  }
  data: {
    last_fetch_at: string | null
    per_source: string
    last_run: Record<string, unknown> | null
  }
  capabilities: {
    admin_ui: boolean
    api_response_cache: boolean
    api_rate_limit: boolean
    document_analysis: boolean
    semantic_search: boolean
    postgres_extensions: Record<string, boolean>
    [key: string]: unknown
  }
  [key: string]: unknown
}

/** The public API commonly wraps list payloads with provenance/meta envelopes.
 *  Concrete envelopes are typed per route as routes are ported; this is the
 *  minimal common shape the shell relies on. */
export interface Provenance {
  source_url?: string | null
  retrieved_at?: string | null
  content_sha256?: string | null
}
