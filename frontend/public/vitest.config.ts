import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Vitest for the public app's framework-agnostic units: the transport
// (dedup + cancellation) and the presentational components whose invariants
// matter (StLink's http(s)-only validation, StStat's null→"—"). These do not
// need a running Nuxt, so the config is a plain Vite/Vue + happy-dom setup,
// kept separate from nuxt.config. Composables that depend on Nuxt auto-imports
// (useRoute, useAsyncData) are covered by the browser/e2e gate, not here.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['app/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '~': fileURLToPath(new URL('./app', import.meta.url)),
    },
  },
})
