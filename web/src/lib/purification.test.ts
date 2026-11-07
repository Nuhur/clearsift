import { describe, expect, it } from 'vitest'
import { ceilTo, toDecimal } from './decimal'
import { verdict } from './fixtures'
import { pounds, purificationFor, purificationPence, purificationPercent } from './purification'

describe('purificationPence', () => {
  it('works out 0.98% of £50', () => {
    expect(pounds(purificationPence(50, 0.0098))).toBe('£0.49')
  })

  it('rounds up when it lands between pennies', () => {
    // 50 * 0.012345 = 0.61725
    expect(pounds(purificationPence(50, 0.012345))).toBe('£0.62')
    // 50 * 0.00001 = 0.0005, still a penny
    expect(pounds(purificationPence(50, 0.00001))).toBe('£0.01')
  })

  it("doesn't let float noise add a penny", () => {
    // 100 * 0.0098 is 0.9800000000000001 in floats
    expect(pounds(purificationPence(100, 0.0098))).toBe('£0.98')
  })

  it('gives nothing from nothing', () => {
    expect(pounds(purificationPence(50, 0))).toBe('£0.00')
    expect(pounds(purificationPence(0, 0.02))).toBe('£0.00')
  })

  it('refuses a bad dividend', () => {
    expect(() => purificationPence(-1, 0.02)).toThrow(RangeError)
    expect(() => purificationPence(Number.NaN, 0.02)).toThrow(RangeError)
  })
})

describe('purificationPercent', () => {
  it('rounds up to two places', () => {
    expect(purificationPercent(0.0098)).toBe('0.98%')
    expect(purificationPercent(0.012345)).toBe('1.24%')
    expect(purificationPercent(0.02)).toBe('2.00%')
  })
})

describe('toDecimal', () => {
  it('reads numbers written with an exponent', () => {
    expect(toDecimal(1e-7)).toEqual({ digits: 1n, scale: 7 })
    expect(toDecimal(1e21)).toEqual({ digits: 10n ** 21n, scale: 0 })
    expect(ceilTo(toDecimal(1.5e-7), 2)).toBe(1n)
  })
})

describe('purificationFor', () => {
  it('gives the percentage, the example and the year', () => {
    expect(purificationFor(verdict())).toEqual({
      kind: 'ratio',
      percent: '0.98%',
      example: '£0.49',
      year: 2025,
    })
  })

  it("doesn't apply when the stock fails", () => {
    expect(purificationFor(verdict({ passes: false }))).toEqual({ kind: 'fails' })
  })

  it('points funds to their own reports', () => {
    expect(purificationFor(verdict({ purification_ratio: null }, { is_fund: true }))).toEqual({
      kind: 'fund',
    })
  })

  it("says when it can't be worked out", () => {
    expect(purificationFor(verdict({ purification_ratio: null }))).toEqual({ kind: 'unknown' })
  })
})

describe('purification from an older year', () => {
  it('still uses the older figure and its year', () => {
    expect(purificationFor(verdict({ purification_year: 2023 }))).toEqual({
      kind: 'ratio',
      percent: '0.98%',
      example: '£0.49',
      year: 2023,
    })
  })
})
