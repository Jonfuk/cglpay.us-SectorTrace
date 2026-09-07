export type CollectionKind = 'saved' | 'notebook'
export interface CollectionEntry { id: string; href: string; at: number; label?: string; title?: string; note?: string }

export function collectionHref(value: unknown): string | null {
  if (typeof value !== 'string' || [...value].some(character => character === '\\' || character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) return null
  const path = value.startsWith('#') ? value.slice(1) : value
  if (!path.startsWith('/') || path.startsWith('//')) return null
  const url = new URL(path, 'https://sectortrace.invalid')
  if (url.origin !== 'https://sectortrace.invalid' || /^\/(admin|api)(\/|$)/u.test(url.pathname)) return null
  return `#${path}`
}

export function validCollectionEntry(value: unknown, kind: CollectionKind): value is CollectionEntry {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const entry = value as Record<string, unknown>
  return typeof entry.id === 'string' && entry.id.length > 0 && collectionHref(entry.href) !== null
    && typeof entry.at === 'number' && Number.isFinite(entry.at) && entry.at >= 0
    && typeof entry[kind === 'saved' ? 'label' : 'title'] === 'string'
    && (entry.note === undefined || typeof entry.note === 'string')
}

export function parseCollection(text: string, kind: CollectionKind): CollectionEntry[] {
  const input = JSON.parse(text)
  const entries = input?.format === 'sectortrace-collection' && input.version === 1 && input.kind === kind
    ? input.entries : input?.format === undefined && input?.v === 1 && Array.isArray(input.data) ? input.data : null
  if (!Array.isArray(entries) || !entries.every(entry => validCollectionEntry(entry, kind))) {
    throw new Error('This file is not a valid version-one collection of the selected type. No entries were imported.')
  }
  return entries
}

export function mergeCollection<T extends CollectionEntry>(existing: T[], incoming: T[], makeId: () => string) {
  const merged = [...existing]
  let added = 0
  let skipped = 0
  for (const entry of incoming) {
    if (merged.some(item => JSON.stringify(item) === JSON.stringify(entry))) { skipped++; continue }
    // An ID collision is not permission to overwrite somebody's note. Keep
    // both records, assigning only the imported copy a new local identifier.
    const copy = { ...entry }
    if (merged.some(item => item?.id === copy.id)) {
      do { copy.id = makeId() } while (merged.some(item => item?.id === copy.id))
    }
    merged.push(copy)
    added++
  }
  return { entries: merged, added, skipped }
}
