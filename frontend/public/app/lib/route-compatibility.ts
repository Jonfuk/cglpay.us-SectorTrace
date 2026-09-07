export type ResearchQuery = Record<string, string | (string | null)[] | null | undefined>

// These aliases come from the legacy filter readers, not guessed entity names.
// Canonical keys win visibly when an old bookmark supplies both spellings.
export function canonicalResearchRoute(path: string, input: ResearchQuery) {
  let query = { ...input }
  const messages: string[] = []
  let changed = false
  function alias(oldKey: string, key: string) {
    if (query[oldKey] == null) return
    if (query[key] != null && JSON.stringify(query[key]) !== JSON.stringify(query[oldKey])) messages.push(`The link supplied conflicting ${oldKey} and ${key} filters. The ${key} selection is being used.`)
    else if (query[key] == null) query[key] = query[oldKey]
    const { [oldKey]: _removed, ...rest } = query
    query = rest
    changed = true
  }
  if (['/contracts', '/pay', '/pfd'].includes(path)) {
    alias('provider', 'provider_key'); alias('yearFrom', 'year_from'); alias('yearTo', 'year_to')
  }
  if (path === '/diary') { alias('provider', 'provider_key'); alias('buyer', 'buyer_ons_code') }
  if (path === '/discrepancies') { alias('provider', 'provider_key'); alias('authority', 'ons_code') }
  if (path === '/doctables') { alias('doc', 'document_id'); alias('table', 'table_id') }
  if (path === '/geography') { alias('layer', 'metric'); alias('selected', 'inspect') }
  if (path === '/timeline' && (query.provider || query.authority)) {
    alias('provider', 'provider_key'); alias('authority', 'ons_code')
    path = '/coverage'; query.lens = 'history'; changed = true
  }
  if (path === '/documents' && typeof query.doc === 'string' && query.doc) {
    path = `/documents/${encodeURIComponent(query.doc)}`
    delete query.doc; alias('el', 'element_id'); alias('element', 'element_id'); changed = true
  }
  if (path === '/contracts' && typeof query.ocid === 'string' && query.ocid) {
    path = `/contracts/process/${encodeURIComponent(query.ocid)}`
    delete query.ocid; changed = true
  }
  return { path, query, messages, changed }
}

// Source APIs and browser collections can supply hash links. Keep them inside
// public research routes and never turn an arbitrary stored URL into navigation.
const publicRoots = new Set(['', 'providers', 'authorities', 'geography', 'contracts', 'pay', 'treatment', 'cqc', 'pfd', 'claims', 'documents', 'relationships', 'pathfinder', 'cooccurrence', 'compare', 'timeline', 'coverage', 'diary', 'catalogue', 'calendar', 'changes', 'discrepancies', 'revisions', 'doctables', 'links', 'research-tools', 'saved', 'notebook', 'journey', 'search', 'about', 'api'])
export function researchHref(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const hash = value.startsWith('/#/') ? value.slice(1) : value
  if (!hash.startsWith('#/') || hash.startsWith('#//') || [...hash].some(char => char.charCodeAt(0) <= 32 || char === '\\')) return null
  const path = hash.slice(2).split('?')[0]!
  if (!publicRoots.has(path.split('/')[0]!) || path.split('/').some(part => ['.', '..'].includes(decodeURIComponentSafe(part)))) return null
  return hash
}
function decodeURIComponentSafe(value: string) { try { return decodeURIComponent(value) } catch { return '..' } }
