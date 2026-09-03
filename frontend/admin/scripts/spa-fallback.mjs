// Emit explicit 200.html / 404.html SPA fallbacks from the generated entry so
// the Python server can answer any unprerendered /admin deep link with the
// client shell. Identical bytes to index.html by construction.
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
