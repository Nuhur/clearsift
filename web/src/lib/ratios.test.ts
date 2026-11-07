import { describe, expect, it } from 'vitest'
import { check } from './fixtures'
import {
  barLabel,
  baseText,
  isOffScale,
  isOverLimit,
  limitPercent,
  outcomeWord,
  ratioName,
  ratioSubline,
  reportYearText,
  scalePosition,
  valuePercent,
} from './ratios'

describe('scalePosition', () => {
  it('puts zero at the left', () => {
    expect(scalePosition(0, 0.3)).toBe(0)
  })

  it('puts the limit in the middle', () => {
    expect(scalePosition(0.3, 0.3)).toBe(0.5)
    expect(scalePosition(0.33333, 0.33333)).toBe(0.5)
  })

  it('scales between zero and twice the limit', () => {
    expect(scalePosition(0.15, 0.3)).toBeCloseTo(0.25)
    expect(scalePosition(0.45, 0.3)).toBeCloseTo(0.75)
  })

  it('pins anything past twice the limit to the right', () => {
    expect(scalePosition(0.6, 0.3)).toBe(1)
    expect(scalePosition(2, 0.3)).toBe(1)
  })

  it('gives nothing for a missing figure', () => {
    expect(scalePosition(null, 0.3)).toBeNull()
  })

  it('copes with a zero limit', () => {
    expect(scalePosition(0, 0)).toBe(0)
    expect(scalePosition(0.01, 0)).toBe(1)
  })
})

describe('isOverLimit', () => {
  it('is true at or past the limit', () => {
    expect(isOverLimit(0.29, 0.3)).toBe(false)
    expect(isOverLimit(0.3, 0.3)).toBe(true)
    expect(isOverLimit(0.01, 0)).toBe(true)
    expect(isOverLimit(0, 0)).toBe(false)
    expect(isOverLimit(null, 0.3)).toBe(false)
  })
})

describe('isOffScale', () => {
  it('is only true past twice the limit', () => {
    expect(isOffScale(0.6, 0.3)).toBe(false)
    expect(isOffScale(0.61, 0.3)).toBe(true)
    expect(isOffScale(null, 0.3)).toBe(false)
    expect(isOffScale(0.01, 0)).toBe(true)
  })
})

describe('outcomeWord', () => {
  it('puts each outcome into words', () => {
    expect(outcomeWord('pass')).toBe('Through')
    expect(outcomeWord('doubt')).toBe('Check')
    expect(outcomeWord('fail')).toBe('Stopped')
  })
})

describe('names and bases', () => {
  it('gives friendly names', () => {
    expect(ratioName('debt')).toBe('Debt')
    expect(ratioName('receivables plus cash')).toBe('Receivables and cash')
    expect(ratioName('interest income')).toBe('Interest income')
    expect(ratioName('something new')).toBe('Something new')
  })

  it('says what each ratio is measured against', () => {
    expect(baseText('market_cap')).toBe('of market value')
    expect(baseText('total_assets')).toBe('of total assets')
    expect(baseText('revenue')).toBe('of revenue')
  })

  it('builds the small line under the name', () => {
    expect(ratioSubline(check())).toBe('of market value, limit 30%')
    expect(ratioSubline(check({ base: 'total_assets', limit: 0.33333 }))).toBe(
      'of total assets, limit 33.333%',
    )
  })
})

describe('percentages', () => {
  it('writes limits like the Python', () => {
    expect(limitPercent(0.3)).toBe('30%')
    expect(limitPercent(0.33333)).toBe('33.333%')
    expect(limitPercent(0.3333)).toBe('33.33%')
    expect(limitPercent(0.05)).toBe('5%')
  })

  it('writes values to two places', () => {
    expect(valuePercent(0.0167, 0.3)).toBe('1.67%')
    expect(valuePercent(0.2746, 0.33333)).toBe('27.46%')
    expect(valuePercent(0.4, 0.3)).toBe('40.00%')
  })

  it("doesn't let rounding turn a pass into the limit", () => {
    expect(valuePercent(0.29999, 0.3)).toBe('just under 30%')
    expect(valuePercent(0.3, 0.3)).toBe('30.00%')
  })

  it("doesn't show a tiny amount as nothing", () => {
    expect(valuePercent(0.00001, 0)).toBe('under 0.01%')
    expect(valuePercent(0, 0)).toBe('0.00%')
  })
})

describe('barLabel', () => {
  it('names the value and the limit', () => {
    expect(barLabel(check())).toBe('Debt 1.67%, limit 30%')
  })

  it('says when there is no figure', () => {
    expect(barLabel(check({ value: null }))).toBe('Debt, no figure, limit 30%')
  })
})

describe('reportYearText', () => {
  it('names the report an older figure came from', () => {
    expect(reportYearText(check({ name: 'interest income', year: 2023 }))).toBe(
      'From the 2023 report',
    )
  })

  it('says nothing for a figure from the latest report', () => {
    expect(reportYearText(check())).toBeNull()
  })
})
