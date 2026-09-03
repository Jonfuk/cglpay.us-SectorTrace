import type { RouterConfig } from '@nuxt/schema'
import { createWebHashHistory } from 'vue-router'

// The legacy portal addressed every route as `#/route?filters`, and those are
// live bookmarks and shared links. Hash history keeps them resolving through
// the cutover: one static `index.html` answers every deep link, and the
// fragment never reaches the Python server, so no server-side rewrite is
// needed. An explicit history-mode redirect layer is the alternative the plan
// allows; hash history is chosen because it preserves the exact existing URLs
// byte-for-byte.
export default <RouterConfig>{
  history: (base) => createWebHashHistory(base),
}
