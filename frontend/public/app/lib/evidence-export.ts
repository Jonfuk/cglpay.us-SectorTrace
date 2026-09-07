// Export exactly the supplied rows with their scope. In particular, a returned
// page must never acquire a filename or annotation claiming the full corpus.
export function downloadEvidenceJson(name: string, rows: unknown[], context: Record<string, unknown>) {
  const blob = new Blob([JSON.stringify({ _provenance: { ...context, exported_at: new Date().toISOString(), returned: rows.length }, rows }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${name}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function evidenceCsv(rows: Record<string, unknown>[]): string {
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))]
  function cell(value: unknown): string {
    if (value == null) return ''
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
    // Spreadsheet applications can execute text beginning with a formula
    // marker, even after whitespace. Numeric negatives remain numeric values.
    const firstContent = [...text].find(character => character.charCodeAt(0) > 32 && character.trim() !== '')
    const protectedText = (firstContent !== undefined && '=+@-'.includes(firstContent)) || /^[\t\r\n]/u.test(text) ? `'${text}` : text
    return `"${protectedText.replaceAll('"', '""')}"`
  }
  return [columns.map(cell).join(','), ...rows.map(row => columns.map(column => cell(row[column])).join(','))].join('\r\n')
}

export function downloadEvidenceCsv(name: string, rows: Record<string, unknown>[]) {
  const blob = new Blob(['\uFEFF', evidenceCsv(rows)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = `${name}.csv`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
