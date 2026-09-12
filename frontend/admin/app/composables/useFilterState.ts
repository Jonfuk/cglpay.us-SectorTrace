import { computed } from 'vue'

// URL query parameters are the authoritative source for shareable filters
// (Phase 6). A filtered view is a link: the same `#/route?filters` bookmark
// must reproduce the same view. This composable reads and writes filters
// through the router's query, preserving the legacy names, normalization,
// defaults, ordering, and reset behavior — never a private reactive store that
// could drift from the URL.
//
// Arrays are supported for repeated keys (e.g. `?ons=a&ons=b`), matching the
// legacy portal's multi-select filters.

export type FilterValue = string | string[] | undefined

export interface UseFilterState {
  /** Reactive read of one filter key. Repeated keys resolve to string[]. */
  get: (key: string) => FilterValue
  /** Replace one key. `undefined`/`[]` removes it (reset semantics). Others
   *  are preserved. Navigation uses `replace` so filter churn does not spam
   *  browser history. */
  set: (key: string, value: FilterValue) => Promise<void>
  /** Replace the whole filter set at once (used by reset-all and deep links). */
  setAll: (values: Record<string, FilterValue>) => Promise<void>
  /** All current filters as a plain object; array-valued where repeated. */
  all: () => Record<string, FilterValue>
}

function normalizeQueryValue(raw: unknown): FilterValue {
  if (raw === undefined || raw === null) return undefined
  if (Array.isArray(raw)) {
    const items = raw.filter((v): v is string => typeof v === 'string')
    return items.length > 1 ? items : items[0]
  }
  return typeof raw === 'string' ? raw : String(raw)
}

export function useFilterState(): UseFilterState {
  const route = useRoute()
  const router = useRouter()

  const currentQuery = computed(() => route.query)

  const all = (): Record<string, FilterValue> => {
    const out: Record<string, FilterValue> = {}
    for (const key of Object.keys(currentQuery.value)) {
      out[key] = normalizeQueryValue(currentQuery.value[key])
    }
    return out
  }

  const get = (key: string): FilterValue => normalizeQueryValue(currentQuery.value[key])

  const writeQuery = async (next: Record<string, FilterValue>): Promise<void> => {
    // Drop empties so a reset produces a clean URL, and keep key order stable
    // by sorting — a filtered view and its bookmark stay byte-identical
    // regardless of the order filters were set.
    const query: Record<string, string | string[]> = {}
    for (const key of Object.keys(next).sort()) {
      const value = next[key]
      if (value === undefined) continue
      if (Array.isArray(value)) {
        if (value.length === 0) continue
        query[key] = value
      } else if (value !== '') {
        query[key] = value
      }
    }
    await router.replace({ query })
  }

  const set = async (key: string, value: FilterValue): Promise<void> => {
    await writeQuery({ ...all(), [key]: value })
  }

  const setAll = async (values: Record<string, FilterValue>): Promise<void> => {
    await writeQuery(values)
  }

  return { get, set, setAll, all }
}
