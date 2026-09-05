import type { RouterConfig } from '@nuxt/schema'
import { createWebHashHistory } from 'vue-router'
import { prepareAdminLocation } from './lib/preferences'

// The legacy operator UI used hash routing under /admin. Hash history keeps
// existing operator bookmarks resolving through the cutover and lets one static
// entry document answer every deep link without a server-side rewrite.
export default <RouterConfig>{
  history: (base) => {
    prepareAdminLocation()
    return createWebHashHistory(base)
  },
}
