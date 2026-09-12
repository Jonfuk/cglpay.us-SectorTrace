import type { Ref } from 'vue'

// Standard data-loading wiring for a filtered public route. It keys the fetch
// on the route (so each route caches independently) and refetches whenever the
// URL query changes — because URL query is the authoritative filter state, a
// filter change is a data change. The fetcher receives the current filters as a
// plain object read from the URL.
//
// Cancellation of superseded requests is handled one layer down by the shared
// Transport (dedup by canonical key); this composable does not need its own
// AbortController for the common case.

export interface DataRoute<T> {
  data: Ref<T | null>
  pending: Ref<boolean>
  error: Ref<unknown>
  refresh: () => Promise<void>
}

export async function useDataRoute<T>(
  key: string,
  fetcher: (filters: Record<string, string | string[] | undefined>) => Promise<T>,
): Promise<DataRoute<T>> {
  const route = useRoute()
  const filters = useFilterState()

  const { data, pending, error, refresh } = await useAsyncData<T | null>(
    key,
    () => fetcher(filters.all()),
    {
      default: () => null,
      // A filter change is a data change: refetch when the query object shifts.
      watch: [() => route.query],
    },
  )

  return {
    data: data as Ref<T | null>,
    pending: pending as Ref<boolean>,
    error: error as Ref<unknown>,
    refresh,
  }
}
