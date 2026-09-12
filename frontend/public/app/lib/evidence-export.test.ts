import { describe, expect, it } from 'vitest'
import { evidenceCsv } from './evidence-export'

describe('displayed evidence CSV', () => {
  it('preserves numeric negatives, zero, missing values, quotes and original text', () => {
    const csv = evidenceCsv([{ number: -2.5, zero: 0, missing: null, text: 'Published "offer", part-time', suppressed: '[suppressed]' }])
    expect(csv.split('\r\n')[1]).toBe('-2.5,0,,"Published ""offer"", part-time","[suppressed]"')
  })
  it('neutralises spreadsheet formulas in source text without altering original objects', () => {
    const row = { equals: '=1+1', whitespace: '  @SUM(A1:A2)', negativeText: '-2.5', tab: '\tvalue', multiline: 'first\nsecond' }
    const csv = evidenceCsv([row])
    expect(csv).toContain('"\'=1+1"')
    expect(csv).toContain('"\'  @SUM(A1:A2)"')
    expect(csv).toContain('"\'-2.5"')
    expect(csv).toContain('"\'\tvalue"')
    expect(csv).toContain('"first\nsecond"')
    expect(row.equals).toBe('=1+1')
  })
  it('includes fields present only in later rows without inventing missing cells', () => {
    expect(evidenceCsv([{ first: 'a' }, { later: 'b' }])).toBe('"first","later"\r\n"a",\r\n,"b"')
  })
})
