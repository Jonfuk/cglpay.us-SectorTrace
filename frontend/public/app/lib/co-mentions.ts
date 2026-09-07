export interface CoMention { record_type?: string; record_id?: string; element_id?: string; title?: string; text?: string; date?: string | null; source_system?: string; matched?: Record<string, unknown>; [key: string]: unknown }
export interface CoMentions { entities?: Array<{ key?: string; name?: string; variant_count?: number }>; results?: CoMention[]; note?: string; caveat?: string; counts?: unknown; record_types?: string[] }
export const coMentionLimitations = 'Documents must match a confirmed name variant for every selected key within one document element. Structured records can match two or more selected keys. Appearing in the same record does not establish a commissioning, ownership or other relationship. Results are capped at 200 and are not an exhaustive census.'
export function coMentionKeyError(keys: string[]) {
  if (keys.length < 2 || keys.length > 5) return 'Choose between 2 and 5 provider or supplier keys. Saved selections have not been silently shortened.'
  if (keys.some(key => !key)) return 'Every selected organisation needs an exact key.'
  if (new Set(keys).size !== keys.length) return 'Choose distinct keys. A repeated key does not represent another organisation.'
  return ''
}
export function coMentionIdentity(row: CoMention) { return row.record_type && row.record_id ? JSON.stringify([row.record_type, row.record_id, row.element_id ?? null]) : undefined }
export function coMentionDestination(row: CoMention) {
  if (row.record_type === 'document' && row.record_id && row.element_id) return { path: '/documents', query: { doc: row.record_id, el: row.element_id } }
  if (['coroner_report', 'tribunal_case'].includes(row.record_type ?? '')) return { path: '/pfd' }
  if (row.record_type === 'procurement_notice') return { path: '/contracts' }
  return undefined
}
