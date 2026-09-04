// Minimal PMTiles v3 reader for the boundary map. Keeping this reader local
// avoids adding a second runtime dependency to the public app: MapLibre gets a
// normal vector-tile source, while this protocol only performs bounded HTTP
// Range requests against the content-addressed archive.

export interface BoundaryManifest {
  archive: string
  source_digest: string
  boundary_version: string
  generator_version: string
  feature_count: number
  bounds: [number, number, number, number]
  min_zoom: number
  max_zoom: number
  zoom_range: [number, number]
  output_digest: string
  tile_count: number
}

interface Header {
  rootOffset: number
  rootLength: number
  leafOffset: number
  leafLength: number
  tileOffset: number
  tileLength: number
}

interface Entry {
  tileId: number
  offset: number
  length: number
  runLength: number
}

interface ProtocolRequest {
  url: string
}

interface ProtocolResponse {
  data: ArrayBuffer
}

const HEADER_LENGTH = 127

function u64(view: DataView, offset: number): number {
  // PMTiles offsets are well below Number.MAX_SAFE_INTEGER for this archive;
  // two uint32 reads keep the client compatible with older TS lib targets.
  return view.getUint32(offset, true) + view.getUint32(offset + 4, true) * 0x100000000
}

function readVarint(bytes: Uint8Array, state: { offset: number }): number {
  let value = 0
  let shift = 0
  while (state.offset < bytes.length) {
    const byte = bytes[state.offset++]!
    value += (byte & 0x7f) * 2 ** shift
    if (!(byte & 0x80)) return value
    shift += 7
  }
  throw new Error('Truncated PMTiles directory varint')
}

async function gunzip(bytes: ArrayBuffer): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('This browser cannot decompress PMTiles directories')
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

function decodeDirectory(bytes: Uint8Array): Entry[] {
  const state = { offset: 0 }
  const count = readVarint(bytes, state)
  const entries = Array.from({ length: count }, () => ({
    tileId: 0,
    offset: 0,
    length: 0,
    runLength: 0,
  }))
  let previous = 0
  for (const entry of entries) {
    previous += readVarint(bytes, state)
    entry.tileId = previous
  }
  for (const entry of entries) entry.runLength = readVarint(bytes, state)
  for (const entry of entries) entry.length = readVarint(bytes, state)
  for (let index = 0; index < entries.length; index += 1) {
    const encoded = readVarint(bytes, state)
    const entry = entries[index]!
    const previousEntry = entries[index - 1]
    entry.offset = index > 0 && encoded === 0 && previousEntry
      ? previousEntry.offset + previousEntry.length
      : encoded - 1
  }
  return entries
}

function findEntry(entries: Entry[], tileId: number): Entry | null {
  let low = 0
  let high = entries.length - 1
  let candidate: Entry | null = null
  while (low <= high) {
    const middle = (low + high) >> 1
    const entry = entries[middle]!
    if (tileId < entry.tileId) {
      high = middle - 1
    } else {
      // A zero-run entry points at a leaf directory. It covers the range
      // until the next root entry, so retain the greatest preceding entry
      // instead of returning whichever midpoint the binary search visits.
      candidate = entry
      low = middle + 1
    }
  }
  if (!candidate) return null
  if (candidate.runLength === 0) return candidate
  return tileId - candidate.tileId < candidate.runLength ? candidate : null
}

function rotate(size: number, x: number, y: number, rx: number, ry: number): [number, number] {
  if (ry === 0) {
    if (rx !== 0) return [size - 1 - y, size - 1 - x]
    return [y, x]
  }
  return [x, y]
}

// Keep the arithmetic explicit so the implementation works with the ES2022
// target Nuxt emits and does not depend on a non-standard Number API.
function pmtilesTileId(z: number, x: number, y: number): number {
  let result = ((1 << (z * 2)) - 1) / 3
  let level = z - 1
  while (level >= 0) {
    const size = 1 << level
    const rx = size & x
    const ry = size & y
    result += ((3 * rx) ^ ry) * 2 ** level
    ;[x, y] = rotate(size, x, y, rx, ry)
    level -= 1
  }
  return result
}

class PmtilesReader {
  private header: Header | null = null
  private root: Entry[] | null = null
  private leaves = new Map<number, Entry[]>()

  constructor(private readonly archiveUrl: string) {}

  private async range(start: number, length: number, signal: AbortSignal): Promise<ArrayBuffer> {
    const end = start + length - 1
    const response = await fetch(this.archiveUrl, {
      headers: { Range: `bytes=${start}-${end}`, Accept: 'application/octet-stream' },
      credentials: 'same-origin',
      signal,
    })
    if (!response.ok && response.status !== 206) {
      throw new Error(`PMTiles range request failed: ${response.status}`)
    }
    return response.arrayBuffer()
  }

  private async loadHeader(signal: AbortSignal): Promise<Header> {
    if (this.header) return this.header
    const bytes = await this.range(0, HEADER_LENGTH, signal)
    const view = new DataView(bytes)
    const magic = new TextDecoder().decode(new Uint8Array(bytes, 0, 7))
    if (magic !== 'PMTiles' || view.getUint8(7) !== 3) throw new Error('Unsupported PMTiles archive')
    this.header = {
      rootOffset: u64(view, 8),
      rootLength: u64(view, 16),
      leafOffset: u64(view, 40),
      leafLength: u64(view, 48),
      tileOffset: u64(view, 56),
      tileLength: u64(view, 64),
    }
    return this.header
  }

  private async directory(offset: number, length: number, signal: AbortSignal): Promise<Entry[]> {
    const bytes = await this.range(offset, length, signal)
    return decodeDirectory(await gunzip(bytes))
  }

  private async entryFor(tile: number, signal: AbortSignal): Promise<Entry | null> {
    const header = await this.loadHeader(signal)
    this.root ??= await this.directory(header.rootOffset, header.rootLength, signal)
    let entry = findEntry(this.root, tile)
    if (entry?.runLength === 0) {
      let leaf = this.leaves.get(entry.offset)
      if (!leaf) {
        leaf = await this.directory(header.leafOffset + entry.offset, entry.length, signal)
        // A bounded cache prevents a long map session from retaining every
        // leaf directory while still avoiding duplicate visible-tile fetches.
        if (this.leaves.size >= 8) this.leaves.delete(this.leaves.keys().next().value as number)
        this.leaves.set(entry.offset, leaf)
      }
      entry = findEntry(leaf, tile)
    }
    return entry
  }

  async get(z: number, x: number, y: number, signal: AbortSignal): Promise<ArrayBuffer> {
    const entry = await this.entryFor(pmtilesTileId(z, x, y), signal)
    if (!entry) return new ArrayBuffer(0)
    const tile = pmtilesTileId(z, x, y)
    const offset = entry.offset + (entry.runLength ? tile - entry.tileId : 0)
    const header = await this.loadHeader(signal)
    return this.range(header.tileOffset + offset, entry.length, signal)
  }
}

export function createPmtilesProtocol(archiveUrl: string) {
  const reader = new PmtilesReader(archiveUrl)
  return async (request: ProtocolRequest, abortController: AbortController): Promise<ProtocolResponse> => {
    const match = request.url.match(/\/(\d+)\/(\d+)\/(\d+)\.pbf(?:\?.*)?$/)
    if (!match) throw new Error(`Invalid PMTiles tile URL: ${request.url}`)
    const [, z, x, y] = match
    return { data: await reader.get(Number(z), Number(x), Number(y), abortController.signal) }
  }
}
