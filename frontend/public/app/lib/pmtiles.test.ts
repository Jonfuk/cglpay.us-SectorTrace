// @vitest-environment node
import { gzipSync } from 'node:zlib'
import { afterEach, expect, it, vi } from 'vitest'
import { createPmtilesProtocol } from './pmtiles'

afterEach(() => vi.unstubAllGlobals())

it('reads the same payload for every tile in a PMTiles run', async () => {
  const root = gzipSync(Uint8Array.from([1, 1, 4, 3, 1]))
  const archive = new Uint8Array(127 + root.length + 3)
  archive.set(new TextEncoder().encode('PMTiles'))
  archive[7] = 3
  const header = new DataView(archive.buffer)
  header.setUint32(8, 127, true)
  header.setUint32(16, root.length, true)
  header.setUint32(56, 127 + root.length, true)
  header.setUint32(64, 3, true)
  archive.set(root, 127)
  archive.set([11, 22, 33], 127 + root.length)
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
    const range = new Headers(init.headers).get('range')!.match(/bytes=(\d+)-(\d+)/)!
    return new Response(archive.slice(Number(range[1]), Number(range[2]) + 1), { status: 206 })
  }))
  const protocol = createPmtilesProtocol('/map/synthetic.pmtiles')
  for (const [x, y] of [[0, 0], [0, 1], [1, 1], [1, 0]]) {
    const response = await protocol({ url: `pmtiles://boundaries/1/${x}/${y}.pbf` }, new AbortController())
    expect([...new Uint8Array(response.data)]).toEqual([11, 22, 33])
  }
})
