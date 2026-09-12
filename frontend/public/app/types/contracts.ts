import type { ContractNotice, ContractsResponse } from './api'
export type EvidenceRow = Record<string, unknown>
export interface Notice extends ContractNotice {
  buyer_ons_code?: string | null
  value_max?: number | null
  date_start?: string | null
  payload_sha256?: string | null
  notice_link?: string | null
  notice_link_basis?: string | null
  notice_web_url?: string | null
  notice_type_raw?: string | null
  ocds_tags?: string[]
  suppliers?: Array<{ name: string; is_tracked_provider: boolean }>
}
export interface ContractPayload extends ContractsResponse {
  notices: Notice[]
  total?: number
  by_year?: EvidenceRow[]
  by_quarter?: EvidenceRow[]
  by_procedure_type?: EvidenceRow[]
  value_bands?: EvidenceRow[]
  by_provider?: EvidenceRow[]
  date_range?: { earliest?: string | null; latest?: string | null }
}
export interface Payment extends EvidenceRow {
  authority_ons_code?: string | null
  authority_name?: string | null
  file_url?: string | null
  row_index?: number | null
  period?: string | null
  payee?: string | null
  amount?: number | null
  amount_text?: string | null
  description?: string | null
  provider_key?: string | null
  canonical_name?: string | null
  source_url?: string | null
  retrieved_at?: string | null
  payload_sha256?: string | null
}
export interface PaymentPayload { total?: number; payments?: Payment[]; files?: EvidenceRow[]; caveats?: Record<string, string | null> }
export interface ProcessStage { stage: string; present: boolean; notices: Notice[] }
export interface ProcessPayload { ocid: string; buyer?: { name?: string | null; ons_code?: string | null }; stages?: ProcessStage[]; notice_count?: number; date_range?: { earliest?: string | null; latest?: string | null }; caveat?: string | null }
