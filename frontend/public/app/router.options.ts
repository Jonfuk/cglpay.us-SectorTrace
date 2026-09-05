import type { RouterConfig } from '@nuxt/schema'
import type { RouteRecordRaw } from 'vue-router'

function flattenContractLifecycle(routes: readonly RouteRecordRaw[]): RouteRecordRaw[] {
  const contracts = routes.find((route) => route.name === 'contracts')
  const lifecycle = contracts?.children?.find((route) => route.name === 'contracts-process-ocid')
  if (!contracts || !lifecycle) return [...routes]

  const withoutNestedLifecycle: RouteRecordRaw[] = routes.map((route) => {
    if (route !== contracts) return route
    const { children: _children, ...withoutChildren } = route
    return withoutChildren as RouteRecordRaw
  })
  return [
    ...withoutNestedLifecycle,
    { ...lifecycle, path: '/contracts/process/:ocid' },
  ]
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
  routes: flattenContractLifecycle,
}

export default routerConfig
