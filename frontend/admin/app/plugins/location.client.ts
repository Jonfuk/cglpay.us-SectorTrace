import { validLocation } from '~/lib/preferences'
export default defineNuxtPlugin((nuxt) => {
  nuxt.$router.afterEach((to) => {
    const value = validLocation(to.fullPath)
    if (value) {
      try {
        localStorage.setItem('st.admin.location', value)
      } catch {
        /* Optional preference. */
      }
    }
  })
})
