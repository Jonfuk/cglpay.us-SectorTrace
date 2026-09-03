// Public evidence-atlas application — Nuxt 4, Vue 3.6 (Vapor-enabled), static
// generation with client-side data loading. This config encodes several
// Phase 6 delivery constraints that are easy to regress:
//
//   * ssr:false  — the production Python image must not run a Node/Nitro
//     server. We ship a client-rendered SPA generated at build time.
//   * vue.vapor  — Vapor is enabled from the first prototype. Components opt in
//     with `<script setup vapor>`; everything else stays VDOM under interop.
//     If the pinned Vue 3.6 RC / Vapor combination proves unstable, the
//     completion gate is still the Nuxt 4 *VDOM* migration — turn Vapor off
//     here and the app keeps working.
//   * hash history — existing `#/route?filters` bookmarks must keep resolving
//     during cutover (see app/router.options.ts).
//   * origin-only assets, one build target per surface. No CDN.
export default defineNuxtConfig({
  ssr: false,
  compatibilityDate: '2025-01-01',

  modules: ['@nuxt/ui'],

  // Public surface is served from the site root. Admin is a separate app.
  app: {
    baseURL: '/',
    head: {
      htmlAttrs: { lang: 'en' },
      title: 'SectorTrace',
    },
  },

  // Vue 3.6 Vapor interop. Nuxt stays the application root (no createVaporApp);
  // the VDOM runtime is retained wherever interop requires it.
  vue: {
    // `vapor` is valid at runtime (Vue 3.6 / Nuxt Vapor interop) and the build
    // honours it, but the Nuxt config types still lag the RC and do not declare
    // the key yet. Remove this suppression once the typings include it.
    // @ts-expect-error vapor config typing lags the Vue 3.6 RC runtime
    vapor: true,
  },

  css: ['~/assets/css/main.css'],

  // Prerender the stable shell so first paint does not wait on JS to draw the
  // frame. Mutable warehouse data is always fetched in the browser — never
  // baked into a static asset.
  nitro: {
    prerender: {
      crawlLinks: false,
      routes: ['/'],
    },
  },

  // Immutable, content-hashed build assets. The Python server sets the
  // one-year cache header for `/_nuxt/**` and `no-cache` for HTML entry points.
  experimental: {
    payloadExtraction: false,
  },

  typescript: {
    strict: true,
    typeCheck: false,
  },

  // No runtime env of its own: the public API is same-origin. A build-time
  // override of the API base is available for isolated fixture testing only.
  runtimeConfig: {
    public: {
      apiBase: '',
    },
  },
})
