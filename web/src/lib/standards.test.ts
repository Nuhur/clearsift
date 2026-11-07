import { describe, expect, it } from 'vitest'
import { check, standard, verdict } from './fixtures'
import { chosenStandard, otherStandardLine, otherStandardLines, parseStandard } from './standards'

const FTSE_CHECKS = [
  check({ value: 0.2746, limit: 0.33333, base: 'total_assets' }),
  check({ name: 'cash', value: 0.35, limit: 0.33333, base: 'total_assets', outcome: 'fail' }),
]

describe('parseStandard', () => {
  it('reads known standards in any case', () => {
    expect(parseStandard('ftse')).toBe('ftse')
    expect(parseStandard(' MSCI ')).toBe('msci')
  })

  it('ignores anything else', () => {
    expect(parseStandard('nope')).toBeNull()
    expect(parseStandard(null)).toBeNull()
  })
})

describe('chosenStandard', () => {
  it('finds the standard the verdict went by', () => {
    expect(chosenStandard(verdict({ methodology: 'FTSE' }))?.methodology).toBe('FTSE')
  })
})

describe('otherStandardLine', () => {
  it('names debt when it passes', () => {
    const s = standard({ methodology: 'FTSE', checks: FTSE_CHECKS.slice(0, 1) })
    expect(otherStandardLine(s, verdict())).toBe(
      'FTSE passes, with debt at 27.46% of total assets against a 33.333% limit.',
    )
  })

  it('names the failing figure when it fails', () => {
    const s = standard({ methodology: 'FTSE', passes: false, checks: FTSE_CHECKS })
    expect(otherStandardLine(s, verdict())).toBe(
      'FTSE fails, with cash at 35.00% of total assets against a 33.333% limit.',
    )
  })

  it('says when the failing figure is missing', () => {
    const s = standard({ passes: false, checks: [check({ value: null, outcome: 'fail' })] })
    expect(otherStandardLine(s, verdict())).toBe('AAOIFI fails, with no figure for debt.')
  })

  it('points to the business when no figure failed', () => {
    const s = standard({ methodology: 'MSCI', passes: false })
    const v = verdict({ passes: false }, { business_status: 'excluded' })
    expect(otherStandardLine(s, v)).toBe('MSCI fails on the business, the same as here.')
  })

  it('keeps funds simple', () => {
    const s = standard({ methodology: 'FTSE', checks: [] })
    expect(otherStandardLine(s, verdict({}, { is_fund: true }))).toBe(
      'FTSE passes, funds get the same check under every standard.',
    )
  })
})

describe('otherStandardLines', () => {
  it('leaves out the chosen standard', () => {
    const lines = otherStandardLines(verdict({ methodology: 'FTSE' }))
    expect(lines.map((line) => line.split(' ')[0])).toEqual(['AAOIFI', 'MSCI'])
  })
})
