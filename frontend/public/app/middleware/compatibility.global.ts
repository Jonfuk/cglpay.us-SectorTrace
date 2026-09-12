import { canonicalResearchRoute } from '~/lib/route-compatibility'
export default defineNuxtRouteMiddleware(to => {
  const result = canonicalResearchRoute(to.path, to.query)
  const notice = useState('research-link-notice', () => ({ path: '', messages: [] as string[] }))
  if (result.messages.length) notice.value = { path: result.path, messages: result.messages }
  else if (notice.value.path !== result.path) notice.value = { path: '', messages: [] }
  if (result.changed) return navigateTo({ path: result.path, query: result.query }, { replace: true })
})
