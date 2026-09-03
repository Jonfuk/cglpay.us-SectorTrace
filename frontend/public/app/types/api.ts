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

/** `/api/v1/summary` — the landing-page figures. Each block carries the caveat
 *  that bounds how its figures may be read. Only the fields the overview route
 *  consumes are typed here; the rest are preserved by the index signature. */
export interface SummaryResponse {
  providers: {
    total: number
    target: string | null
  }
  authorities: {
    total: number
    with_contracts: number
    regions: Array<Record<string, unknown>>
    regions_caveat: string | null
  }
  contracts: {
    total_notices: number
    total_value_gbp: number
    direct_awards: number
    psr_notices: number
    matched_to_provider: number
    value_is_concentrated?: boolean
    caveat: string | null
    sum_caveat: string | null
  }
  workforce: {
    latest_census_year: number | null
    all_unverified?: boolean
    caveat: string | null
  }
  fingertips: {
    latest_period: string | null
    indicators_collected: number
  }
  [key: string]: unknown
}

/** A contract notice row (`/api/v1/contracts` → `notices[]`). Carries its own
 *  provenance columns. Only the rendered columns are named; the rest survive on
 *  the index signature. */
export interface ContractNotice {
  notice_id: string | null
  title: string | null
  buyer_name: string | null
  supplier_name_raw: string | null
  value_core: number | null
  currency: string | null
  date_published: string | null
  date_end: string | null
  procedure_type: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

/** `/api/v1/contracts`. Rich payload; the route consumes `notices` and the
 *  caveats, with the rest available on the index signature. */
export interface ContractsResponse {
  notices: ContractNotice[]
  page?: { limit: number; offset: number; returned: number; [k: string]: unknown }
  caveats?: Record<string, string | null>
  [key: string]: unknown
}

/** A statutory pay-rate row (`/api/v1/pay` → `statutory_pay_rates[]`). */
export interface StatutoryPayRate {
  period_label: string | null
  effective_from: string | null
  band_label: string | null
  band_role: string | null
  amount: number | null
  value_text: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

/** `/api/v1/pay` — the most caveat-heavy payload. Evidence layers stay separate
 *  arrays and are never combined into a rate; the route renders them as such. */
export interface PayResponse {
  statutory_pay_rates?: StatutoryPayRate[]
  nhs_job_adverts?: Array<Record<string, unknown>>
  living_wage_accreditations?: Array<Record<string, unknown>>
  gender_pay_gap_reports?: Array<Record<string, unknown>>
  caveats?: Record<string, string | null>
  [key: string]: unknown
}

/** A provider row (`/api/v1/providers`). */
export interface ProviderRow {
  provider_key: string | null
  canonical_name: string | null
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
