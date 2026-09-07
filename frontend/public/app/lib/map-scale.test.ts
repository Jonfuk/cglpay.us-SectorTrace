import { describe, expect, it } from 'vitest'
import { mapScale } from './map-scale'
describe('map classification', () => {
  it('keeps constant and missing distributions valid', () => {
    expect(mapScale([7, 7, 7]).breaks).toEqual([])
    expect(mapScale([NaN, Infinity]).breaks).toEqual([])
  })
  it('deduplicates quantiles while keeping the lowest band', () => {
    const scale = mapScale([0, 0, 0, 0, 1, 1, 1, 8, 8, 100])
    expect(scale.breaks).toEqual([1, 8])
    expect(scale.colours).toHaveLength(3)
  })
})
