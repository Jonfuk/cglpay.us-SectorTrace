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
    metrics?: Array<{
      metric?: string
      workforce_segment?: string | null
      value?: number | null
      unit?: string | null
      verified?: number
    }>
  }
  fingertips: {
    latest_period: string | null
    indicators_collected: number
  }
  pipeline?: {
    last_run?: string | null
    sources?: Array<{
      source_system?: string | null
      last_retrieved?: string | null
    }>
  }
  funnel?: {
    discovered?: number | null
    undecided?: number | null
    promoted?: number | null
    rejected?: number | null
    evidence_rows?: number | null
    caveat?: string | null
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
  /** Stable OCDS process key, when the notice publisher supplied one. */
  ocid?: string | null
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

/** `/api/v1/providers` — the list endpoint wraps rows with a named key. */
export interface ProvidersResponse {
  providers: ProviderRow[]
  [key: string]: unknown
}

/** One authority value for the choropleth (`/api/v1/geography` → `features[]`).
 *  Geometry is deliberately NOT included here — the map loads its separate,
 *  content-addressed PMTiles archive. */
export interface GeographyFeature {
  ons_code: string | null
  authority_name: string | null
  region: string | null
  value: number | null
  financial_year: string | null
  [key: string]: unknown
}

/** `/api/v1/geography` — one value per authority for a chosen metric. */
export interface GeographyResponse {
  metric: string
  metric_label: string
  year: string | number | null
  unit: string | null
  features: GeographyFeature[]
  authority_mean: number | null
  min: number | null
  max: number | null
  caveat: string | null
  [key: string]: unknown
}

/** A treatment metric catalogue row (`/api/v1/treatment_metrics` → `metrics[]`).
 *  Shown before any chart is drawn: definition, periods held, CI availability. */
export interface TreatmentMetric {
  key: string
  name: string | null
  topic: string | null
  substance: string | null
  unit: string | null
  definition: string | null
  has_confidence_interval: boolean
  period_count: number
  authority_count: number
  england_available: boolean
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

export interface TreatmentResponse {
  metrics: TreatmentMetric[]
  count: number
  caveat: string | null
  [key: string]: unknown
}

/** A catalogue dataset row (`/api/v1/catalogue` → `datasets[]`). */
export interface CatalogueDataset {
  dataset_id: string
  title: string | null
  publisher: string | null
  official_url: string | null
  evidence_layer_label: string | null
  geography: string | null
  cadence: string | null
  row_count: number
  last_retrieved_at: string | null
  [key: string]: unknown
}

export interface CatalogueResponse {
  datasets: CatalogueDataset[]
  evidence_layers: Record<string, string>
  count: number
  caveat: string | null
  [key: string]: unknown
}

/** `/api/v1/document_search` — requires a `query`. Result rows carry their own
 *  provenance; only the rendered columns are named. */
export interface DocumentHit {
  document_id?: string | number | null
  title: string | null
  source_system: string | null
  document_type: string | null
  published_date?: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

export interface DocumentSearchResponse {
  results?: DocumentHit[]
  hits?: DocumentHit[]
  [key: string]: unknown
}

/** A Prevention of Future Deaths report row (`/api/v1/pfd` → `recent[]`). */
export interface PfdReport {
  report_ref: string | null
  report_date: string | null
  coroner_area: string | null
  categories: string | null
  report_url: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

export interface PfdResponse {
  recent?: PfdReport[]
  totals?: Record<string, unknown>
  caveats?: Record<string, string | null>
  [key: string]: unknown
}

/** A published claim with its citations and caveats (`/api/v1/claims`). */
  export interface ClaimRow {
    id: number | string
    claim_text: string | null
    caveats: string[]
    citations: Array<{
      table?: string | null
      key?: string | null
      resolved?: {
        label?: string | null
        url?: string | null
        source_url?: string | null
        retrieved_at?: string | null
      } | null
      [key: string]: unknown
    }>
    created_by: string | null
    created_at: string | null
    published_by?: string | null
    published_at?: string | null
    note?: string | null
  [key: string]: unknown
}

export interface ClaimsResponse {
  claims: ClaimRow[]
  caveat: string | null
  [key: string]: unknown
}

/** A CQC location row (`/api/v1/cqc_locations` → `results[]`). */
export interface CqcLocation {
  location_id: string | null
  location_name: string | null
  provider_name: string | null
  postal_code: string | null
  region: string | null
  registration_status: string | null
  overall_rating: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

export interface CqcResponse {
  results: CqcLocation[]
  total: number
  without_coordinate?: number
  caveat: string | null
  [key: string]: unknown
}

/** A relationship edge (`/api/v1/relationships` → `edges[]`). */
export interface RelationshipEdge {
  relationship_id: string | null
  subject_entity_id: string | null
  object_entity_id: string | null
  valid_from: string | null
  valid_to: string | null
  [key: string]: unknown
}

export interface RelationshipsResponse {
  center: Record<string, unknown>
  neighbours: Array<Record<string, unknown>>
  edges: RelationshipEdge[]
  [key: string]: unknown
}

/** A recorded change event (`/api/v1/changes` → `events[]`). */
export interface ChangeEvent {
  kind: string | null
  at: string | null
  source: string | null
  evidence_type: string | null
  entity: unknown
  detail: unknown
  [key: string]: unknown
}

export interface ChangesResponse {
  events: ChangeEvent[]
  [key: string]: unknown
}

/** A publication-calendar row (`/api/v1/publication_calendar` → `datasets[]`).
 *  Stated cadence is registry metadata; observed cadence is measured — the two
 *  are separate fields and never combined. */
export interface CalendarRow {
  dataset_id: string
  title: string | null
  publisher: string | null
  stated_cadence: string | null
  cadence_basis: string | null
  last_publication: string | null
  next_expected: string | null
  status: string | null
  official_url: string | null
  [key: string]: unknown
}

export interface CalendarResponse {
  as_of: string
  datasets: CalendarRow[]
  counts?: { by_status?: Record<string, number>; by_basis?: Record<string, number> }
  note?: string
  caveat?: string
  [key: string]: unknown
}

/** A provider-timeline event (`/api/v1/providers/{key}/timeline` → `events[]`).
 *  Each event keeps its own dated provenance. */
export interface TimelineEvent {
  date: string | null
  event_type: string | null
  label: string | null
  value_summary?: string | null
  source_url: string | null
  retrieved_at: string | null
  [key: string]: unknown
}

export interface ProviderTimelineResponse {
  provider: Record<string, unknown> | null
  events: TimelineEvent[]
  [key: string]: unknown
}

/** A coverage-timeline dataset probe (`/api/v1/coverage_timeline` → `datasets[]`). */
export interface CoverageDataset {
  dataset_id: string
  title: string | null
  period_kind: string | null
  periods: string[]
  held: boolean
  link: string | null
  [key: string]: unknown
}

export interface CoverageResponse {
  entity: { kind?: string; id?: string | null; name?: string | null } | null
  datasets: CoverageDataset[]
  span?: { min: number; max: number } | null
  [key: string]: unknown
}

/** A contract-diary event (`/api/v1/contract_diary` → `events[]`). */
export interface DiaryEvent {
  date: string | null
  kind: string | null
  kind_label: string | null
  title: string | null
  buyer_name: string | null
  supplier: string | null
  value_core: number | null
  source_url: string | null
  [key: string]: unknown
}

export interface DiaryResponse {
  scope: { kind?: string; id?: string | null } | null
  events: DiaryEvent[]
  span?: { min: string; max: string } | null
  caveat?: string
  [key: string]: unknown
}

/** A discrepancy check (`/api/v1/discrepancies`). Only identity-level fields are
 *  compared; a discrepancy is a difference between sources, not an error claim. */
export interface DiscrepancyRow {
  id: string
  label: string
  observations?: Array<Record<string, unknown>>
  distinct_values?: unknown[]
  value?: unknown
  sources?: string[]
  [key: string]: unknown
}

export interface DiscrepancyResponse {
  entity: { kind?: string; id?: string | null; name?: string | null } | null
  discrepancies: DiscrepancyRow[]
  agreed: DiscrepancyRow[]
  checked: number
  caveat?: string
  [key: string]: unknown
}

/** `/api/v1/compare` — parallel series for two or more entities. */
export interface CompareResponse {
  authorities?: Array<Record<string, unknown>>
  providers?: Array<Record<string, unknown>>
  series?: Record<string, unknown>
  [key: string]: unknown
}

/** `/api/v1/authorities/{ons_code}` — everything held about one authority. */
export interface AuthorityResponse {
  authority: {
    ons_code: string | null
    name: string | null
    type: string | null
    region: string | null
  } | null
  grant?: { rows: Array<Record<string, unknown>>; unit?: string }
  budget?: { rows: Array<Record<string, unknown>>; unit?: string }
  contracts?: Record<string, unknown>
  caveats?: Record<string, string | null>
  [key: string]: unknown
}

/** A co-occurrence record (`/api/v1/cooccurrence` → `results[]`). Co-occurrence
 *  is location in one record, never an asserted relationship. */
export interface CooccurrenceRecord {
  record_type: string | null
  record_id: string | null
  title: string | null
  source_system: string | null
  text: string | null
  link: string | null
  [key: string]: unknown
}

export interface CooccurrenceResponse {
  entities: Array<{ key: string; name: string | null; variant_count: number }>
  results: CooccurrenceRecord[]
  caveat?: string
  [key: string]: unknown
}

/** A document table (`/api/v1/document_tables` → `tables[]`). */
export interface DocumentTable {
  document_table_id: string
  page_number: number | null
  row_count: number | null
  column_count: number | null
  extraction_status: string | null
  preview: string[][]
  [key: string]: unknown
}

export interface DocumentTablesResponse {
  document: { document_id: string; title: string | null; source_url: string | null; retrieved_at: string | null } | null
  tables: DocumentTable[]
  note?: string
  [key: string]: unknown
}

/** `/api/v1/relationship_path` — the shortest verified path between two
 *  entities. Unconfirmed name-match edges are excluded; a path is a chain of
 *  verified edges, not an asserted relationship strength. */
export interface PathNode {
  node: string
  type: string | null
  id: string | null
  [key: string]: unknown
}

export interface PathResponse {
  found: boolean
  hops: number
  path: Array<Record<string, unknown>>
  nodes: PathNode[]
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
