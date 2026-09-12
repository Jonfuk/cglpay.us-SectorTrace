// Small dependency-free static server for the Lighthouse gate. It mirrors the
// production asset layout closely enough to exercise both generated apps while
// keeping the benchmark independent of PostgreSQL and the Python web process.
import { createServer } from 'node:http'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { extname, isAbsolute, join, normalize, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const publicRoot = resolve(join(root, 'public', '.output', 'public'))
const adminRoot = resolve(join(root, 'admin', '.output', 'public'))
const port = Number(process.env.PORT || 4173)

const types = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

function inside(candidate, base) {
  // `resolve` returns platform-native separators. Comparing its result with
  // a URL-style slash made the Windows preview server reject every nested
  // asset, leaving the otherwise healthy admin shell blank locally.
  const fromBase = relative(base, candidate)
  return fromBase === '' || (!fromBase.startsWith('..') && !isAbsolute(fromBase))
}

function resolveFile(urlPath) {
  const isAdmin = urlPath === '/admin' || urlPath.startsWith('/admin/')
  const base = isAdmin ? adminRoot : publicRoot
  const relative = isAdmin ? urlPath.slice('/admin'.length) : urlPath
  const requested = resolve(base, `.${normalize(relative || '/')}`)
  if (!inside(requested, base)) return null
  if (existsSync(requested) && statSync(requested).isFile()) return requested
  if (extname(relative)) return null
  const fallback = join(base, '200.html')
  return existsSync(fallback) ? fallback : join(base, 'index.html')
}

const server = createServer((request, response) => {
  const url = new URL(request.url || '/', `http://${request.headers.host || '127.0.0.1'}`)
  if (url.pathname === '/health') {
    response.writeHead(200, { 'Content-Type': 'text/plain', 'Content-Length': '3' })
    response.end('ok\n')
    return
  }
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
    const body = JSON.stringify({ error: 'API unavailable in the static Lighthouse harness' })
    response.writeHead(404, { 'Content-Type': 'application/json', 'Content-Length': String(Buffer.byteLength(body)) })
    response.end(body)
    return
  }
  const file = resolveFile(url.pathname)
  if (!file) {
    response.writeHead(404)
    response.end()
    return
  }
  const body = readFileSync(file)
  const immutable = file.includes(`${join('public', '.output', 'public')}${'/_nuxt'}`)
    || file.includes(`${join('admin', '.output', 'public')}${'/_nuxt'}`)
  response.writeHead(200, {
    'Content-Type': types[extname(file).toLowerCase()] || 'application/octet-stream',
    'Content-Length': String(body.length),
    'Cache-Control': immutable ? 'public, max-age=31536000, immutable' : 'no-cache',
  })
  if (request.method !== 'HEAD') response.end(body)
  else response.end()
})

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`static frontend listening on http://127.0.0.1:${port}\n`)
})
