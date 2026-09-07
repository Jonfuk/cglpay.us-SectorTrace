import type { RouterConfig } from '@nuxt/schema'
import type { RouteRecordRaw } from 'vue-router'

function flattenStandaloneReaders(routes: readonly RouteRecordRaw[]): RouteRecordRaw[] {
  let result = [...routes]
  for (const [parentName, childName, path] of [
    ['contracts', 'contracts-process-ocid', '/contracts/process/:ocid'],
    ['documents', 'documents-id', '/documents/:id'],
  ]) {
    const parent = result.find(route => route.name === parentName)
    const child = parent?.children?.find(route => route.name === childName)
    if (!parent || !child) continue
    result = result.map(route => {
      if (route !== parent) return route
      const { children, ...base } = route
      const remaining = children?.filter(item => item !== child)
      return { ...base, ...(remaining?.length ? { children: remaining } : {}) } as RouteRecordRaw
    })
    result.push({ ...child, path: path! })
  }
  return result
}

// The legacy portal addressed every route as `#/route?filters`, and those are
// live bookmarks and shared links. Hash history keeps them resolving through
// the cutover: one static `index.html` answers every deep link, and the
// fragment never reaches the Python server, so no server-side rewrite is
// needed. An explicit history-mode redirect layer is the alternative the plan
// allows; hash history is chosen because it preserves the exact existing URLs
// byte-for-byte.
const routerConfig: RouterConfig = {
  // Nuxt owns hash-history setup here. Supplying a second history factory
  // makes Nuxt's `/#` base get encoded as part of the route path on a fresh
  // deep link; hashMode preserves the legacy `#/route` bookmarks directly.
  hashMode: true,
  routes: flattenStandaloneReaders,
}

export default routerConfig
