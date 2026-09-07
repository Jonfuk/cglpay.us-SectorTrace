export type SafetyRow = Record<string, unknown>
export const safetySources = [
  { key: 'pfd', label: 'Coroners’ reports', date: 'Report date as published. A report being sent to a provider and naming that provider are different relationships.' },
  { key: 'sar', label: 'Safeguarding Adult Reviews', date: 'No structured report date is returned. A library year is not a publication date.' },
  { key: 'hse', label: 'HSE enforcement notices', date: 'Notice issue date. Published appeal, withdrawal and compliance results remain attached to the notice.' },
  { key: 'tribunal', label: 'Employment tribunal cases', date: 'Decision date. Published judgments cover only part of the case population. Outcomes are extracted from judgment text, not structured tribunal findings.' },
  { key: 'cqc', label: 'CQC inspection and rating entries', date: 'The date may be the last inspection date or the overall rating date. This response does not identify which supplied it. These are current location entries, not an inspection history.' },
] as const
export const safetyRelationships: Record<string, string> = { addressed_to: 'Addressed to', named_in: 'Named in', matched_to: 'Matched to', regulated_by: 'Regulated by' }
export interface SafetyDefinition { key: string; title: string; dateKey?: string; identity: string[]; columns: Array<[string, string]>; description: string; endpoint: string; array: string; chronology?: boolean }
export function safetyLane(source: string): SafetyDefinition {
  const definition = safetySources.find(item => item.key === source)
  return { key: `${source}-events`, title: definition?.label ?? `Source: ${source}`, dateKey: 'date', identity: ['source', 'relationship', 'entity_type', 'entity_key', 'title', 'date', 'source_url'], columns: [['date', 'Source date'], ['relationship', 'Relationship'], ['entity_name', 'Organisation'], ['title', 'Source record'], ['result', 'Published or extracted result'], ['detail', 'Source detail']], description: definition?.date ?? 'The response does not describe this source.', endpoint: 'safety_legal', array: `events[source=${source}]`, chronology: true }
}
export const safetySupporting: Record<string, SafetyDefinition> = {
  pfd: { key: 'pfd-reports', title: 'PFD report records', dateKey: 'report_date', identity: ['report_ref', 'source_url'], columns: [['report_ref', 'Report reference'], ['report_date', 'Published report date'], ['coroner_area', 'Coroner area'], ['categories', 'Published categories'], ['has_concerns', 'Concern text available']], description: 'Up to 50 reports returned in descending report-reference order. Coroner areas are not local authority boundaries. Missing concern text does not mean there were no concerns.', endpoint: 'pfd', array: 'recent' },
  sar: { key: 'sar-reports', title: 'SAR library records', identity: ['document_url', 'source_url'], columns: [['sab_name', 'Board as supplied'], ['library_year', 'Library year'], ['document_ext', 'Document format'], ['has_body_text', 'Extracted text available']], description: 'Up to 50 records returned by library year. Library year is not a report date, and a missing board name is not a geographic attribution.', endpoint: 'pfd', array: 'sar.recent' },
  hse: { key: 'hse-notices', title: 'HSE register records', dateKey: 'issue_date', identity: ['notice_number', 'provider_key', 'source_url'], columns: [['notice_number', 'Notice number'], ['recipient_name', 'Published recipient'], ['provider_name', 'Matched provider'], ['notice_type', 'Notice type'], ['issue_date', 'Issued'], ['compliance_date', 'Original compliance date'], ['revised_compliance_date', 'Revised compliance date'], ['result', 'Published result'], ['legislation', 'Legislation'], ['contravention_text', 'Published contravention']], description: 'The returned register records are matched to tracked providers. A notice can be appealed, withdrawn or changed. Read the published result and dates together.', endpoint: 'safety', array: 'notices' },
}
export function safetyRecordKey(definition: SafetyDefinition, row: SafetyRow) { return JSON.stringify([definition.key, ...definition.identity.map(key => row[key] ?? null)]) }
export function safetyText(value: unknown) { return value == null || value === '' ? 'Not supplied' : typeof value === 'number' ? value.toLocaleString('en-GB', { maximumSignificantDigits: 21 }) : typeof value === 'object' ? JSON.stringify(value) : String(value) }
export function safetyCell(key: string, row: SafetyRow) {
  if (key === 'library_year') return row[key] == null || row[key] === '' ? 'Not supplied' : String(row[key])
  if (key === 'relationship') return safetyRelationships[String(row[key])] ?? safetyText(row[key])
  if (key === 'has_concerns') return row[key] === true || row[key] === 1 ? 'Concern text held' : row[key] === false || row[key] === 0 ? 'Metadata stub without concern text' : 'Text availability not supplied'
  if (key === 'has_body_text') return row[key] === true || row[key] === 1 ? 'Extracted text held' : row[key] === false || row[key] === 0 ? 'No extracted text held' : 'Text availability not supplied'
  return safetyText(row[key])
}
const months = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
// Source dates remain untouched. Only complete, recognised calendar dates may
// determine chronology. Partial dates never acquire an invented day or month.
export function safetyDate(value: unknown): number | null {
  if (typeof value !== 'string') return null
  const text = value.trim()
  let year: number, month: number, day: number
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  const british = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(text)
  const written = /^(\d{1,2}) ([a-z]+) (\d{4})$/i.exec(text)
  if (iso) [year, month, day] = [Number(iso[1]), Number(iso[2]), Number(iso[3])]
  else if (british) [year, month, day] = [Number(british[3]), Number(british[2]), Number(british[1])]
  else if (written) [year, month, day] = [Number(written[3]), months.indexOf(written[2]!.toLowerCase()) + 1, Number(written[1])]
  else return null
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day)
  date.setUTCHours(0, 0, 0, 0)
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? date.getTime() : null
}
export function safetyDateGroup(row: SafetyRow, key?: string): 'dated' | 'other-date' | 'undated' {
  const value = key ? row[key] : null
  return value == null || value === '' ? 'undated' : safetyDate(value) === null ? 'other-date' : 'dated'
}
export function safetyChronology(rows: SafetyRow[], key?: string) {
  const dated = rows.filter(row => safetyDateGroup(row, key) === 'dated').sort((a, b) => safetyDate(b[key!])! - safetyDate(a[key!])!)
  return [...dated, ...rows.filter(row => safetyDateGroup(row, key) === 'other-date'), ...rows.filter(row => safetyDateGroup(row, key) === 'undated')]
}
