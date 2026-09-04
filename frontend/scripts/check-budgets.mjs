// Phase 6 frontend budget + isolation gate.
//
// Measures the built static output of both Nuxt apps against the compressed-size
// budgets in performance.md, and enforces the structural rules that protect the
// migration: the public bundle must contain no admin/privileged code, and no
// specialist library (MapLibre, PMTiles, Tabulator, ECharts) may appear on a
// route that does not use it. Exits non-zero on any violation so CI can gate on
// it. Run after `npm run build` in each app.
//
// "Shared JS" is measured precisely: the chunks the entry `index.html` itself
// loads (its module script + modulepreload links), i.e. what every route pays
// on first load — not the sum of all chunks (which includes lazy per-route
// code).
import { gzipSync } from 'node:zlib'
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const KiB = 1024
const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

function gzipBytes(path) {
  return gzipSync(readFileSync(path)).length
}

/** Chunks referenced directly by index.html — the shared/initial JS. */
function sharedChunks(distPublic) {
  const html = readFileSync(join(distPublic, 'index.html'), 'utf8')
  const refs = new Set()
  for (const m of html.matchAll(/\/_nuxt\/([A-Za-z0-9_-]+\.js)/g)) refs.add(m[1])
  return [...refs].map((name) => join(distPublic, '_nuxt', name)).filter(existsSync)
}

function allFiles(dir, ext) {
  if (!existsSync(dir)) return []
  return readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => join(dir, f))
}

function sum(paths) {
  return paths.reduce((n, p) => n + gzipBytes(p), 0)
}

const failures = []
const report = []

function check(label, actualBytes, budgetKiB, { enforced = true } = {}) {
  const actualKiB = actualBytes / KiB
  const ok = actualKiB <= budgetKiB
  report.push(
    `${ok ? 'PASS' : enforced ? 'FAIL' : 'WARN'}  ${label.padEnd(42)} ` +
      `${actualKiB.toFixed(1).padStart(7)} KiB / ${budgetKiB} KiB`,
  )
  if (!ok && enforced) failures.push(`${label}: ${actualKiB.toFixed(1)} KiB > ${budgetKiB} KiB`)
}

// --- Size budgets -------------------------------------------------------------
const publicDist = join(root, 'public', '.output', 'public')
const adminDist = join(root, 'admin', '.output', 'public')

if (existsSync(publicDist)) {
  const nuxtDir = join(publicDist, '_nuxt')
  const sharedJs = sum(sharedChunks(publicDist))
  const css = sum(allFiles(nuxtDir, '.css'))
  check('public shared JS', sharedJs, 120)
  check('public shared CSS', css, 50)
  // Overview is the default route; its JS+CSS before data must fit 375 KiB.
  // Shared JS + all CSS is a safe upper bound (the overview page chunk is tiny).
  check('public overview route JS+CSS', sharedJs + css, 375)
  // Incremental map payload: the lazy chunks that carry MapLibre, on top of the
  // shared bundle. Budget 400 KiB gzip. Zero until the map chunk exists.
  const mapChunks = allFiles(nuxtDir, '.js').filter((p) =>
    readFileSync(p, 'utf8').toLowerCase().includes('maplibre'),
  )
  if (mapChunks.length) check('public map route incremental (MapLibre)', sum(mapChunks), 400)
} else {
  failures.push('public build missing — run `npm run build` in frontend/public')
}

if (existsSync(adminDist)) {
  const nuxtDir = join(adminDist, '_nuxt')
  const sharedJs = sum(sharedChunks(adminDist))
  const css = sum(allFiles(nuxtDir, '.css'))
  check('admin initial route JS+CSS', sharedJs + css, 200)
} else {
  failures.push('admin build missing — run `npm run build` in frontend/admin')
}

// --- Structural rules ---------------------------------------------------------

/** Concatenated text of every JS file under an app's _nuxt dir. */
function jsText(dist) {
  return allFiles(join(dist, '_nuxt'), '.js')
    .map((p) => readFileSync(p, 'utf8'))
    .join('\n')
}

// Portal isolation: the public bundle must not carry admin API paths or
// operator-only client code. These strings are distinctive to the admin client
// and would only appear if admin code leaked into the public build.
if (existsSync(publicDist)) {
  const text = jsText(publicDist)
  const forbidden = ['/api/admin/', 'useAdminApi', 'promoteCandidate', 'decideReview']
  for (const needle of forbidden) {
    if (text.includes(needle)) {
      failures.push(`public bundle contains admin marker "${needle}" — isolation breach`)
      report.push(`FAIL  public bundle isolation (${needle})`)
    }
  }
  if (!forbidden.some((n) => text.includes(n))) {
    report.push('PASS  public bundle contains no admin code')
  }
}

// Specialist-library route boundaries: MapLibre/PMTiles/Tabulator/ECharts may
// only ever appear in a LAZY route chunk, never in the shared chunks the entry
// HTML loads — no route should pay for a library it does not use. A library in a
// shared chunk fails the gate; a library confined to a lazy chunk passes and is
// reported so the boundary stays visible.
const SPECIALIST = ['maplibre', 'pmtiles', 'tabulator', 'echarts']
for (const [name, dist] of [['public', publicDist], ['admin', adminDist]]) {
  if (!existsSync(dist)) continue
  const sharedNames = new Set(sharedChunks(dist).map((p) => p.split('/').pop()))
  const nuxtDir = join(dist, '_nuxt')
  for (const lib of SPECIALIST) {
    let inShared = false
    let inLazy = false
    for (const file of allFiles(nuxtDir, '.js')) {
      if (!readFileSync(file, 'utf8').toLowerCase().includes(lib)) continue
      if (sharedNames.has(file.split('/').pop())) inShared = true
      else inLazy = true
    }
    if (inShared) {
      failures.push(`${name}: "${lib}" is in a SHARED chunk — it must be lazy-loaded per route`)
      report.push(`FAIL  ${name}: "${lib}" in shared chunk`)
    } else if (inLazy) {
      report.push(`PASS  ${name}: "${lib}" confined to a lazy route chunk`)
    }
  }
}

// --- Result -------------------------------------------------------------------
console.log('\nFrontend budget report (gzip):\n')
console.log(report.join('\n'))
console.log('')
if (failures.length) {
  console.error(`Budget gate FAILED (${failures.length}):`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exit(1)
}
console.log('Budget gate passed.')
