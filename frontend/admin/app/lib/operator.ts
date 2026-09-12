import { Transport } from './transport'
// Catalogue, parser and provenance records have server-defined columns. Keep
// their shape intact at this boundary; only renderers turn their values to text.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AdminRecord = Record<string, any>
export const operator = new Transport('')
export const getOperator = <T = AdminRecord>(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  signal?: AbortSignal,
) => operator.getJson<T>(path, { query, signal })
export const postOperator = <T = AdminRecord>(path: string, body: unknown) =>
  operator.postJson<T>(path, body)
export function textValue(value: unknown): string {
  return value == null
    ? '—'
    : typeof value === 'object'
      ? JSON.stringify(value, null, 2)
      : String(value)
}
export function labelFor(key: string) {
  return key.replaceAll('_', ' ')
}
export function safeUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}
export function downloadCsv(
  columns: string[],
  rows: unknown[][],
  name = 'query-result.csv',
) {
  const cell = (value: unknown) =>
    `"${(value == null ? '' : textValue(value)).replaceAll('"', '""')}"`
  const body = [columns, ...rows]
    .map((row) => row.map(cell).join(','))
    .join('\r\n')
  const url = URL.createObjectURL(
    new Blob([body], { type: 'text/csv;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
