export interface DocumentElement {
  document_element_id: string
  sequence: number
  page_number: number | null
  element_type: string
  heading_level: number | null
  text: string | null
  is_anchor: boolean
}
export interface DocumentSearchHit {
  document_id: string
  document_element_id: string
  title: string | null
  title_basis: string | null
  source_title: string | null
  source_system: string | null
  document_type: string | null
  page_number: number | null
  snippet: string | null
  text: string | null
  published_at: string | null
  retrieved_at: string | null
  source_url: string | null
}
export interface DocumentSearchPayload {
  results: DocumentSearchHit[]
  total: number
  offset: number
  limit: number
  query: string
  facets: { source_system: Array<{ value: string; count: number }>; document_type: Array<{ value: string; count: number }> }
  caveat: string | null
}
export interface DocumentContextResponse {
  document_id: string
  document_type: string | null
  title: string | null
  title_basis: string | null
  source_title: string | null
  source_url: string | null
  retrieved_at: string | null
  published_at: string | null
  source_system: string | null
  parser: { name: string | null; version: string | null }
  anchor_element_id: string | null
  context: number
  element_count: number
  range: { from: number; to: number }
  has_more_before: boolean
  has_more_after: boolean
  elements: DocumentElement[]
  caveat: string | null
}
