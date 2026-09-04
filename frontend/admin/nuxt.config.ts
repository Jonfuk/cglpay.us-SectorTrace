// Admin operations-control-room application — a separate Nuxt 4 app from the
// public atlas, with its own config, entry, pages, and dependency graph.
//
// Isolation (Phase 6 portal isolation, unchanged): this app is served under
// `/admin/` and is the ONLY place operator routes, restricted schemas, and
// privileged clients live. The public bundle must never contain any of it.
// Keeping admin a physically separate build makes that isolation structural,
// not a matter of discipline.
export default defineNuxtConfig({
  ssr: false,
  compatibilityDate: '2025-01-01',

  modules: ['@nuxt/ui'],

  app: {
    // Served from /admin/. Build assets resolve to /admin/_nuxt/ by default.
    baseURL: '/admin/',
    head: {
      htmlAttrs: { lang: 'en' },
      title: 'SectorTrace — Operations',
    },
  },

  vue: {
    // See public/nuxt.config.ts: valid at runtime, config typing lags the RC.
    // @ts-expect-error vapor config typing lags the Vue 3.6 RC runtime
    // Keep the Nuxt application root on the stable VDOM runtime. The public
    // app's deployed static smoke test exposed a mount failure with global
    // Vapor interop, so this app follows the same cutover-safe path.
    vapor: false,
  },

  css: ['~/assets/css/main.css'],

  // Hermetic, origin-only builds — see public/nuxt.config.ts. Disable remote
  // font providers so the build never reaches a font CDN.
  fonts: {
    providers: {
      google: false,
      bunny: false,
      fontshare: false,
      fontsource: false,
      googleicons: false,
      adobe: false,
    },
  },

  nitro: {
    prerender: {
      crawlLinks: false,
      routes: ['/'],
    },
  },

  experimental: {
    payloadExtraction: false,
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },

  runtimeConfig: {
    public: {
      apiBase: '',
    },
  },
})
