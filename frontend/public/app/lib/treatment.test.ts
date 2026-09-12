import { describe, expect, it } from 'vitest'
import { fingertipsSlots, ndtmsCohort, treatmentObservation } from './treatment'

describe('published treatment observations', () => {
  it('keeps zero bounds, suppressed text and unusable paired-interval flags distinct', () => {
    const zero = treatmentObservation({ value: 1, lower: 0, upper: 2, has_interval: true }, 'estimates')
    expect(zero).toMatchObject({ value: 1, lower: 0, upper: 2, interval: true })
    const suppressed = treatmentObservation({ value: null, value_text: 'c', lower: 0, upper: null, has_interval: true }, 'estimates')
    expect(suppressed).toMatchObject({ value: null, lower: 0, upper: null, interval: false })
    expect(suppressed.row.value_text).toBe('c')
    expect(suppressed.intervalNote).toContain('marks a paired interval')
    expect(treatmentObservation({ value: 2, lower: 3, upper: 1 }, 'estimates').interval).toBe(false)
  })
  it('uses only supplied catalogue periods to leave an explicit gap in a local series', () => {
    const rows = ['2018/19', '2020/21'].map((time_period, index) => treatmentObservation({ time_period, value: index }, 'local'))
    const result = fingertipsSlots(rows, ['2018/19', '2019/20', '2020/21'])
    expect(result.connect).toBe(true)
    expect(result.slots[1]).toEqual({ label: '2019/20', observation: null })
    expect(result.slots[0]?.observation?.value).toBe(0)
    expect(fingertipsSlots(rows, null).slots).toHaveLength(2)
  })
  it('never collapses duplicate periods or invents their chronological order', () => {
    const rows = [1, 2].map(value => treatmentObservation({ time_period: '2020', time_period_sortable: 2020, value }, 'local'))
    const result = fingertipsSlots(rows, ['2020'])
    expect(result.connect).toBe(false)
    expect(result.slots.map(slot => slot.observation?.value)).toEqual([1, 2])
  })
  it('preserves observation period, publication edition and age as different identities', () => {
    const row = { table_ref: 'Table_2_1', measure: 'Point estimate', ons_code: 'E00000001', time_period: null, published_in: '2020/21', age_group: '15 to 64' }
    expect(treatmentObservation(row, 'estimates').period).toBe('Not supplied')
    expect(treatmentObservation(row, 'estimates').key).not.toBe(treatmentObservation({ ...row, published_in: '2021/22' }, 'estimates').key)
    expect(ndtmsCohort(row)).not.toBe(ndtmsCohort({ ...row, age_group: 'All ages' }))
  })
})
