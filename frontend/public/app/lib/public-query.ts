import type { TransportOptions } from './transport'

// Only API-defined parameters reach a request. Pane, selection and local
// display state may share the URL, but cannot silently become evidence filters.
const parameters: Record<string, readonly string[]> = {
  contracts: ['provider_key', 'buyer_ons_code', 'year_from', 'year_to', 'psr_only', 'q', 'since_retrieved_at', 'limit', 'offset'],
  pay: ['provider_key', 'year_from', 'year_to', 'role', 'source', 'pay_unit'],
  council_spend: ['authority_ons_code', 'provider_key', 'limit'],
  geography: ['metric', 'year'],
  ndtms: ['ons_code', 'table_ref'],
  fingertips: ['indicator_id', 'topic', 'ons_code', 'substance'],
  cqc_locations: ['provider_key', 'authority_ons_code', 'registration_status', 'regulated_activity', 'service_type', 'rating', 'limit', 'offset'],
  safety_legal: ['source', 'relationship', 'provider_key', 'year_from', 'year_to'],
  compare: ['ons_code', 'provider_key'],
  provider_compare: ['provider_key'],
  relationships: ['ons_code', 'provider_key'],
  document_tables: ['table_id', 'document_id'],
  source_link: ['url'],
  contract_diary: ['provider_key', 'buyer_ons_code', 'year', 'ocid'],
  discrepancies: ['provider_key', 'ons_code'],
  cooccurrence: ['key'],
  coverage_timeline: ['provider_key', 'ons_code'],
  relationship_path: ['from_type', 'from_id', 'to_type', 'to_id', 'max_hops'],
  document_search: ['q', 'source_system', 'document_type', 'year_from', 'year_to', 'since_retrieved_at', 'limit', 'offset'],
  publication_calendar: ['today'],
  record_diff: ['kind', 'a', 'b', 'ocid', 'document_id'],
  changes: ['kind', 'source', 'evidence_type', 'since', 'limit'],
}

export function publicQuery(path: string, query: TransportOptions['query']): TransportOptions['query'] {
  const route = path.replace(/^\//, '').replace(/\/$/, '')
  const allowed = /^documents\/[^/]+$/.test(route) ? ['element_id', 'context'] : parameters[route] ?? []
  return Object.fromEntries(Object.entries(query ?? {}).filter(([key]) => allowed.includes(key)))
}
