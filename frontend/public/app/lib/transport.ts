// Low-level same-origin transport shared by the typed public API client.
//
// Phase 6 requires: canonical request keys, deduplication of identical
// in-flight requests, and cancellation of stale route/filter requests via
// AbortController. This module owns exactly that mechanism and nothing about
// evidence shapes — the typed client layers meaning on top.
//
// The Python standard-library server remains the only API authority. We never
// introduce a Nuxt server route as a second backend, so every request here is
// a same-origin fetch against `/api/v1/*`.

export interface TransportOptions {
  /** Query parameters. Serialized in a canonical (sorted) order so that two
   *  logically identical requests produce the same dedup key. */
  query?: Record<string, string | number | boolean | Array<string | number> | undefined | null>
  /** Abort signal from the caller (route/filter lifecycle). Merged with the
   *  transport's own dedup handling. */
  signal?: AbortSignal
  /** Bypass the in-flight dedup map (rarely needed; default false). */
  noDedup?: boolean
}

export class TransportError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly url: string,
    readonly body?: unknown,
  ) {
    super(message)
    this.name = 'TransportError'
  }
}

/** Canonical, order-independent serialization of query parameters. Arrays keep
 *  insertion order (they are semantically ordered, e.g. `ons=a&ons=b`); scalar
 *  keys are sorted so `{a,b}` and `{b,a}` collapse to one key. */
export function canonicalQuery(
  query: TransportOptions['query'],
): string {
  if (!query) return ''
  const parts: string[] = []
  for (const key of Object.keys(query).sort()) {
    const value = query[key]
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      for (const item of value) parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(item))}`)
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    }
  }
  return parts.join('&')
}

/** The dedup key: method + path + canonical query. Two callers asking for the
 *  same thing at the same time share one network request. */
export function requestKey(path: string, query?: TransportOptions['query']): string {
  const q = canonicalQuery(query)
  return q ? `GET ${path}?${q}` : `GET ${path}`
}

interface InFlight {
  promise: Promise<unknown>
  controller: AbortController
  waiters: number
}

export class Transport {
  private inflight = new Map<string, InFlight>()

  constructor(private readonly base: string = '') {}

  private url(path: string, query?: TransportOptions['query']): string {
    const q = canonicalQuery(query)
    const full = `${this.base}${path}`
    return q ? `${full}?${q}` : full
  }

  /** GET JSON. Deduplicates identical concurrent requests and links the
   *  caller's abort signal to the shared request; the underlying fetch is
   *  aborted only when the last waiter cancels. */
  async getJson<T>(path: string, options: TransportOptions = {}): Promise<T> {
    const key = requestKey(path, options.query)

    if (!options.noDedup) {
      const existing = this.inflight.get(key)
      if (existing) {
        existing.waiters += 1
        return this.attach<T>(existing, options.signal, key)
      }
    }

    const controller = new AbortController()
    const entry: InFlight = { controller, waiters: 1, promise: undefined as unknown as Promise<unknown> }
    entry.promise = this.fetchJson<T>(path, options.query, controller.signal)
      .finally(() => {
        // Only clear if this is still the mapped entry (a later identical
        // request may have replaced it after this one settled).
        if (this.inflight.get(key) === entry) this.inflight.delete(key)
      })

    if (!options.noDedup) this.inflight.set(key, entry)
    return this.attach<T>(entry, options.signal, key)
  }

  private attach<T>(entry: InFlight, signal: AbortSignal | undefined, key: string): Promise<T> {
    if (!signal) return entry.promise as Promise<T>
    if (signal.aborted) return Promise.reject(this.abortError())

    return new Promise<T>((resolve, reject) => {
      const onAbort = () => {
        entry.waiters -= 1
        // Abort the shared request only when nobody is still waiting on it.
        if (entry.waiters <= 0) {
          entry.controller.abort()
          this.inflight.delete(key)
        }
        reject(this.abortError())
      }
      signal.addEventListener('abort', onAbort, { once: true })
      ;(entry.promise as Promise<T>).then(
        (value) => {
          signal.removeEventListener('abort', onAbort)
          resolve(value)
        },
        (err) => {
          signal.removeEventListener('abort', onAbort)
          reject(err)
        },
      )
    })
  }

  private abortError(): DOMException {
    return new DOMException('Request aborted', 'AbortError')
  }

  private async fetchJson<T>(
    path: string,
    query: TransportOptions['query'],
    signal: AbortSignal,
  ): Promise<T> {
    const url = this.url(path, query)
    const res = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      signal,
    })
    if (!res.ok) {
      let body: unknown
      try {
        body = await res.json()
      } catch {
        body = undefined
      }
      throw new TransportError(`GET ${url} failed: ${res.status}`, res.status, url, body)
    }
    return (await res.json()) as T
  }
}
