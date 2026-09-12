import { afterEach, describe, expect, it, vi } from 'vitest'
import { Transport, canonicalQuery, requestKey } from './transport'

describe('canonicalQuery', () => {
  it('sorts scalar keys so logically identical queries collapse', () => {
    expect(canonicalQuery({ b: '2', a: '1' })).toBe(canonicalQuery({ a: '1', b: '2' }))
    expect(canonicalQuery({ a: '1', b: '2' })).toBe('a=1&b=2')
  })

  it('preserves array order (repeated keys are semantically ordered)', () => {
    expect(canonicalQuery({ ons: ['b', 'a'] })).toBe('ons=b&ons=a')
  })

  it('drops null and undefined but keeps empty via caller', () => {
    expect(canonicalQuery({ a: undefined, b: null, c: '1' })).toBe('c=1')
  })

  it('encodes keys and values', () => {
    expect(canonicalQuery({ 'a b': 'c&d' })).toBe('a%20b=c%26d')
  })
})

describe('requestKey', () => {
  it('is stable regardless of scalar key order', () => {
    expect(requestKey('/x', { b: '2', a: '1' })).toBe(requestKey('/x', { a: '1', b: '2' }))
  })
})

describe('Transport dedup + cancellation', () => {
  afterEach(() => vi.restoreAllMocks())

  it('deduplicates identical in-flight requests into one fetch', async () => {
    let resolveFetch: (v: unknown) => void = () => {}
    const fetchMock = vi.fn(() =>
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const t = new Transport()

    const a = t.getJson('/api/v1/meta')
    const b = t.getJson('/api/v1/meta')
    expect(fetchMock).toHaveBeenCalledTimes(1) // one shared request

    resolveFetch({
      ok: true,
      json: async () => ({ ok: 1 }),
    })
    await expect(a).resolves.toEqual({ ok: 1 })
    await expect(b).resolves.toEqual({ ok: 1 })
  })

  it('different queries are separate requests', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) }))
    vi.stubGlobal('fetch', fetchMock)
    const t = new Transport()
    await Promise.all([
      t.getJson('/api/v1/x', { query: { a: '1' } }),
      t.getJson('/api/v1/x', { query: { a: '2' } }),
    ])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('a caller aborting rejects with AbortError but does not abort a shared request that still has waiters', async () => {
    let resolveFetch: (v: unknown) => void = () => {}
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const t = new Transport()

    const c1 = new AbortController()
    const first = t.getJson('/api/v1/meta', { signal: c1.signal })
    const second = t.getJson('/api/v1/meta') // second waiter, no signal

    c1.abort()
    await expect(first).rejects.toThrow(/abort/i)

    // The shared request still has the second waiter, so it resolves normally.
    resolveFetch({ ok: true, json: async () => ({ ok: 2 }) })
    await expect(second).resolves.toEqual({ ok: 2 })
  })

  it('throws TransportError on a non-ok response', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const t = new Transport()
    await expect(t.getJson('/api/v1/x')).rejects.toMatchObject({ status: 500 })
  })
})
