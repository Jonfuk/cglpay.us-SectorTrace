// Nuxt `generate` with ssr:false emits `dist/index.html` as the single-page
// entry. The Phase 6 delivery contract additionally requires explicit
// `200.html` and `404.html` SPA fallbacks so the Python server (and Railway)
// can answer any unprerendered deep link with the client shell rather than a
// hard 404. We derive both from the generated entry deterministically — no
// separate build — so the three files are guaranteed identical bytes.
import { copyFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, '..', 'dist')
const entry = join(dist, 'index.html')

if (!existsSync(entry)) {
  console.error(`[spa-fallback] expected ${entry} to exist after nuxt generate`)
  process.exit(1)
}

for (const name of ['200.html', '404.html']) {
  copyFileSync(entry, join(dist, name))
  console.log(`[spa-fallback] wrote dist/${name}`)
}
