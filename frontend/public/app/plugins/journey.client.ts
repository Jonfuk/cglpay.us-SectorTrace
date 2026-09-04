// Records each visited page into the reader's journey (recent pages). Client
// only — there is no server, and the journey is a per-browser convenience. It
// derives a readable label from the route's document title after navigation
// settles, and skips the journey/library management routes themselves so the
// list stays about evidence pages, not the tools for managing it.
const SKIP = new Set(['/notebook', '/saved', '/journey'])

export default defineNuxtPlugin((nuxtApp) => {
  const router = useRouter()
  const journey = useJourney()

  router.afterEach((to) => {
    if (SKIP.has(to.path)) return
    // Let the page set its title first, then record.
    nuxtApp.hook('page:finish', () => {
      const label = (typeof document !== 'undefined' && document.title)
        ? document.title.replace(/\s*·\s*SectorTrace.*/, '').replace(/^SectorTrace\s*[—-]\s*/, '')
        : to.path
      const href = `#${to.fullPath}`
      journey.record(href, label || to.path)
    })
  })
})
