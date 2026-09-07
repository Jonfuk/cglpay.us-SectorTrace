import type { Ref } from 'vue'

// Standard data-loading wiring for a filtered public route. It keys the fetch
// on the route (so each route caches independently) and refetches whenever the
// URL query changes — because URL query is the authoritative filter state, a
// filter change is a data change. The fetcher receives the current filters as a
// plain object read from the URL.
//
// Nuxt supplies the cancellation signal for a superseded load. Fetchers pass
// it into PublicApi so the shared transport releases that request's waiter.
// Deduplication alone cannot cancel requests with different query keys.

export interface DataRoute<T> {
  data: Ref<T | null>
  pending: Ref<boolean>
  error: Ref<unknown>
  refresh: () => Promise<void>
}

export async function useDataRoute<T>(
  key: string,
  fetcher: (filters: Record<string, string | string[] | undefined>, signal: AbortSignal) => Promise<T>,
): Promise<DataRoute<T>> {
  const route = useRoute()
  const filters = useFilterState()

  const { data, pending, error, refresh } = await useAsyncData<T | null>(
    key,
    (_app, { signal }) => fetcher(filters.all(), signal),
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
