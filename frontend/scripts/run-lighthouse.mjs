// Run the pinned Lighthouse profile against the dependency-free generated-app
// server. The separate assertion script keeps raw reports available for later
// comparison while making the thresholds explicit and reviewable.
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const reports = resolve(root, '.lighthouse')
mkdirSync(reports, { recursive: true })
const base = process.env.LIGHTHOUSE_BASE_URL || 'http://127.0.0.1:4173'
const routes = [
  ['public-overview', '/'],
  ['public-places', '/#/geography?view=table'],
  ['admin-overview', '/admin/'],
]

for (const [name, route] of routes) {
  const output = resolve(reports, `${name}.json`)
  const result = spawnSync('npx', [
    '--yes', 'lighthouse@12.8.2', `${base}${route}`,
    '--config-path=./lighthouse.config.json',
    '--only-categories=performance',
    '--output=json', `--output-path=${output}`,
    '--chrome-flags=--headless --no-sandbox',
    '--quiet',
  ], { cwd: root, stdio: 'inherit', shell: process.platform === 'win32' })
  if (result.status !== 0) process.exit(result.status ?? 1)
}
