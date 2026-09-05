import { adminNavigation, adminPath } from './navigation'

const plain = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
export function validLocation(raw: string): string | null {
  const value = adminPath(raw)
  const [path, query] = value.split('?')
  if (!adminNavigation.some((item) => item.to === path)) return null
  const params = new URLSearchParams(query)
  // These are acknowledgements, never preferences or bookmark permissions.
  for (const key of ['reveal', 'opened', 'read', 'selected']) params.delete(key)
  return path + (params.size ? `?${params}` : '')
}

export function migratePreferences(storage: Storage) {
  const copy = (key: string, value: unknown) => {
    if (value !== undefined && storage.getItem(key) === null)
      storage.setItem(key, JSON.stringify({ v: 1, data: value }))
  }
  const parse = (key: string): unknown => {
    try {
      return JSON.parse(storage.getItem(key) || 'null')
    } catch {
      return null
    }
  }
  const reviewer = storage.getItem('cglpay.reviewer')
  if (reviewer) copy('st.admin.reviewer', reviewer.trim())
  const density = storage.getItem('cglpay.dense')
  if (density === '0' || density === '1')
    copy('st.admin.preferences', {
      compact: density === '1',
      collapsed: false,
      groups: {},
    })
  const oldHistory = parse('cglpay.sql.history')
  if (Array.isArray(oldHistory))
    copy(
      'st.admin.sql.history',
      [
        ...new Set(
          oldHistory.filter((s): s is string => typeof s === 'string'),
        ),
      ].slice(0, 50),
    )
  const saved = parse('cglpay.sql.saved')
  if (plain(saved))
    copy(
      'st.admin.sql.saved',
      Object.fromEntries(
        Object.entries(saved).filter(([, v]) => typeof v === 'string'),
      ),
    )
  const presets = parse('cglpay.review.presets')
  if (plain(presets))
    copy(
      'st.admin.review.presets',
      Object.fromEntries(
        Object.entries(presets)
          .filter(([, v]) => plain(v))
          .map(([name, v]) => {
            const p = v as Record<string, unknown>
            const filters = Object.fromEntries(
              ['status', 'module', 'item_type']
                .filter((k) => typeof p[k] === 'string')
                .map((k) => [k, p[k]]),
            )
            if (typeof p.search === 'string') filters.q = p.search
            return [
              name,
              { filters, note: typeof p.note === 'string' ? p.note : '' },
            ]
          }),
      ),
    )
  const oldLocation = storage.getItem('cglpay.location')
  if (oldLocation && !storage.getItem('st.admin.location')) {
    const value = validLocation(oldLocation)
    if (value) storage.setItem('st.admin.location', value)
  }
}

export function prepareAdminLocation() {
  let saved: string | null = null
  try {
    migratePreferences(localStorage)
    saved = localStorage.getItem('st.admin.location')
  } catch {
    /* Storage is optional. */
  }
  const explicit =
    location.hash ||
    (location.pathname.replace(/^\/admin\/?/, '')
      ? location.pathname + location.search
      : '')
  const target = validLocation(explicit || saved || '/') || '/'
  history.replaceState(history.state, '', `/admin/#${target}`)
}
