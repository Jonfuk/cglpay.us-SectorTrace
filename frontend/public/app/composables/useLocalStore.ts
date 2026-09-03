// Versioned browser-storage helper for the per-viewer conveniences the legacy
// portal persists: theme, notebook, saved searches, recent pages, reviewer
// preferences, scroll restoration. Phase 6 requires these structures to be
// versioned and to explicitly migrate or discard incompatible state rather
// than silently mis-reading an old shape.
//
// Every read and write is guarded: storage can be absent (private window,
// blocked site data) or throw on access. A failure degrades to the default,
// never to a broken page.

export interface VersionedStore<T> {
  read: () => T
  write: (value: T) => void
  clear: () => void
}

interface Envelope<T> {
  v: number
  data: T
}

function storage(): Storage | null {
  try {
    if (typeof window === 'undefined') return null
    const s = window.localStorage
    // Probe: some browsers expose the object but throw on use.
    const probe = '__st_probe__'
    s.setItem(probe, '1')
    s.removeItem(probe)
    return s
  } catch {
    return null
  }
}

/**
 * @param key      storage key, namespaced by the caller.
 * @param version  current structure version. A stored envelope with a
 *                 different version is discarded unless `migrate` upgrades it.
 * @param fallback produced fresh whenever nothing valid is stored.
 * @param migrate  optional upgrade from an older version's raw data.
 */
export function useLocalStore<T>(
  key: string,
  version: number,
  fallback: () => T,
  migrate?: (oldVersion: number, oldData: unknown) => T | undefined,
): VersionedStore<T> {
  const read = (): T => {
    const s = storage()
    if (!s) return fallback()
    try {
      const raw = s.getItem(key)
      if (!raw) return fallback()
      const env = JSON.parse(raw) as Envelope<T>
      if (env && typeof env === 'object' && env.v === version) return env.data
      if (env && migrate) {
        const upgraded = migrate(env.v, env.data)
        if (upgraded !== undefined) {
          write(upgraded)
          return upgraded
        }
      }
      // Incompatible and unmigratable: discard rather than trust it.
      return fallback()
    } catch {
      return fallback()
    }
  }

  const write = (value: T): void => {
    const s = storage()
    if (!s) return
    try {
      const env: Envelope<T> = { v: version, data: value }
      s.setItem(key, JSON.stringify(env))
    } catch {
      // Quota or blocked storage: a convenience, not a correctness path.
    }
  }

  const clear = (): void => {
    const s = storage()
    if (!s) return
    try {
      s.removeItem(key)
    } catch {
      /* ignore */
    }
  }

  return { read, write, clear }
}
