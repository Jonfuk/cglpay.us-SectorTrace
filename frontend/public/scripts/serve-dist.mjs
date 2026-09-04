// A tiny static server for the generated `dist/`, used only by the Playwright
// smoke test. It mirrors the production serving contract closely enough to
// exercise the shell: content-hashed assets are served as files, and any
// unresolved route falls back to the SPA entry (200.html). It intentionally has
// NO /api — the smoke test verifies the app BOOTS in a real browser without JS
// errors; data routes render their "unavailable" states, which is correct
// behaviour when the API is absent and exactly what we want to prove is safe.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, '..', 'dist')
const port = Number(process.env.PORT || 4173)

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
}

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || '/', `http://localhost:${port}`)
    let rel = decodeURIComponent(url.pathname).replace(/^\/+/, '')
    const candidate = join(dist, normalize(rel))
    if (rel && candidate.startsWith(dist) && existsSync(candidate) && extname(candidate)) {
      res.writeHead(200, { 'Content-Type': TYPES[extname(candidate)] || 'application/octet-stream' })
      res.end(await readFile(candidate))
      return
    }
    // SPA fallback.
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
    res.end(await readFile(join(dist, '200.html')))
  } catch {
    res.writeHead(500)
    res.end('error')
  }
}).listen(port, () => console.log(`[serve-dist] http://localhost:${port}`))
