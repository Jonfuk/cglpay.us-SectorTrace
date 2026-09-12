import { expect, it } from 'vitest'
import { authorityObservations, validLocation } from './places'
import type { GeographyFeature } from '~/types/api'
it('keeps repeated observations in the list without choosing a map value', () => {
  const rows = [{ ons_code: 'A', value: 1 }, { ons_code: 'A', value: 1 }, { ons_code: 'B', value: 0 }, { ons_code: 'C', value: null }] as GeographyFeature[]
  const result = authorityObservations(rows)
  expect(result.ambiguous).toEqual(['A'])
  expect(result.grouped.get('A')).toHaveLength(2)
  expect(result.mapped).toEqual(rows.slice(2))
})
it('requires finite published coordinates and a location identifier', () => {
  expect(validLocation({ location_id: 'x', latitude: 0, longitude: 0 })).toBe(true)
  expect(validLocation({ location_id: 'x', latitude: null, longitude: 0 })).toBe(false)
  expect(validLocation({ location_id: 'x', latitude: Infinity, longitude: 0 })).toBe(false)
  expect(validLocation({ location_id: 'x', latitude: 52, longitude: 181 })).toBe(false)
})
