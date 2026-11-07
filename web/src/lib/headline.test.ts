import { describe, expect, it } from 'vitest'
import { check, standard, verdict } from './fixtures'
import {
  aboutLine,
  businessRow,
  checkByHandNotes,
  groupWords,
  headline,
  industryWords,
} from './headline'

const UNDISCLOSED = check({
  name: 'interest income',
  value: null,
  limit: 0.05,
  base: 'revenue',
  outcome: 'doubt',
})

describe('headline', () => {
  it('passes cleanly', () => {
    const v = verdict()
    expect(headline('MSFT', v, v.standards[0])).toBe('MSFT passes.')
  })

  it('passes with one figure to check', () => {
    const s = standard({ status: 'doubtful', checks: [check(), UNDISCLOSED] })
    expect(headline('AAPL', verdict({ status: 'doubtful' }), s)).toBe(
      'AAPL passes, with one figure to check.',
    )
  })

  it('fails on an excluded group', () => {
    const v = verdict(
      { passes: false, status: 'excluded' },
      { business_status: 'excluded', excluded_group: 'conventional_banking' },
    )
    expect(headline('JPM', v, standard({ passes: false }))).toBe(
      'JPM fails. Conventional banking is excluded.',
    )
  })

  it('fails with no data', () => {
    const v = verdict(
      { passes: false, status: 'excluded' },
      { no_data: true, sector: null, industry: null, business_status: 'excluded' },
    )
    expect(headline('XYZ', v, standard({ passes: false }))).toBe(
      'XYZ fails. Yahoo Finance has no figures for it.',
    )
  })

  it('passes as an approved fund', () => {
    const v = verdict({}, { is_fund: true, approved_fund: true })
    expect(headline('IGDA.L', v, standard({ checks: [] }))).toBe(
      'IGDA.L passes as an approved fund.',
    )
  })

  it("passes a fund that isn't approved, with a check", () => {
    const v = verdict({ status: 'doubtful' }, { is_fund: true, business_status: 'doubtful' })
    expect(headline('OTHER.L', v, standard({ checks: [] }))).toBe(
      'OTHER.L passes, but the fund needs checking by hand.',
    )
  })

  it('names the one figure that stopped it', () => {
    const s = standard({ passes: false, checks: [check({ value: 0.4, outcome: 'fail' })] })
    expect(headline('X', verdict({ passes: false }), s)).toBe('X fails. Debt is over the limit.')
  })

  it('says when a figure is missing', () => {
    const s = standard({ passes: false, checks: [check({ value: null, outcome: 'fail' })] })
    expect(headline('X', verdict({ passes: false }), s)).toBe(
      "X fails. There's no figure for debt.",
    )
  })

  it('counts several figures that stopped it', () => {
    const fail = check({ value: 0.4, outcome: 'fail' })
    const s = standard({ passes: false, checks: [fail, { ...fail, name: 'cash' }] })
    expect(headline('X', verdict({ passes: false }), s)).toBe('X fails on two figures.')
  })

  it('blames strict mode when only a check stopped it', () => {
    const s = standard({ passes: false, status: 'doubtful', checks: [check(), UNDISCLOSED] })
    expect(headline('X', verdict({ passes: false, status: 'doubtful' }), s)).toBe(
      'X fails. Strict mode only lets fully compliant stocks through.',
    )
  })

  it('mentions the business when that needs a check', () => {
    const v = verdict({ status: 'doubtful' }, { business_status: 'doubtful' })
    expect(headline('KR', v, v.standards[0])).toBe('KR passes, with its business to check.')
  })
})

describe('groupWords', () => {
  it('puts groups into plain words', () => {
    expect(groupWords('conventional_banking')).toBe('Conventional banking')
    expect(groupWords('weapons_and_defence')).toBe('Weapons and defence')
    expect(groupWords('new_group')).toBe('New group')
  })
})

describe('industryWords', () => {
  it('reads like a sentence but keeps short forms', () => {
    expect(industryWords('Consumer Electronics')).toBe('Consumer electronics')
    expect(industryWords('REIT - Hotel & Motel')).toBe('REIT - hotel & motel')
  })
})

describe('businessRow', () => {
  it('says a fine industry is through', () => {
    expect(businessRow(verdict({}, { industry: 'Consumer Electronics' }))).toEqual({
      label: 'What it does',
      text: "Consumer electronics isn't an excluded industry",
      word: 'Through',
    })
  })

  it('says which group stopped it', () => {
    const v = verdict(
      {},
      {
        industry: 'Banks - Diversified',
        business_status: 'excluded',
        excluded_group: 'conventional_banking',
      },
    )
    expect(businessRow(v)).toEqual({
      label: 'What it does',
      text: 'Banks - diversified counts as conventional banking, which is excluded',
      word: 'Stopped',
    })
  })

  it('uses the API reason for any other exclusion', () => {
    const v = verdict(
      { business_reasons: ['MSFT is on the always-exclude list'] },
      { business_status: 'excluded' },
    )
    expect(businessRow(v).text).toBe('MSFT is on the always-exclude list')
  })

  it('describes a fund', () => {
    expect(businessRow(verdict({}, { is_fund: true, approved_fund: true }))).toEqual({
      label: 'What it is',
      text: "It's on your approved list of Sharia-certified funds",
      word: 'Through',
    })
    expect(businessRow(verdict({}, { is_fund: true, business_status: 'doubtful' })).word).toBe(
      'Check',
    )
  })
})

describe('checkByHandNotes', () => {
  it('collects the business and standard warnings without the prefix', () => {
    const v = verdict({
      warnings: ["check by hand: the industry label alone can't confirm this business is halal"],
    })
    const s = standard({ warning: "check by hand: interest income isn't in the latest report" })
    expect(checkByHandNotes(v, s)).toEqual([
      "the industry label alone can't confirm this business is halal",
      "interest income isn't in the latest report",
    ])
  })

  it('is empty when nothing needs checking', () => {
    const v = verdict()
    expect(checkByHandNotes(v, v.standards[0])).toEqual([])
  })
})

describe('an older interest income figure that passes', () => {
  const older = check({
    name: 'interest income',
    value: 0.0098,
    limit: 0.05,
    base: 'revenue',
    outcome: 'pass',
    year: 2023,
  })
  const s = standard({ checks: [check(), older] })
  const v = verdict({ purification_year: 2023 })

  it('just passes, with nothing to check', () => {
    expect(headline('AAPL', v, s)).toBe('AAPL passes.')
  })

  it('leaves out the check-by-hand note', () => {
    expect(checkByHandNotes(v, s)).toEqual([])
  })
})

describe('aboutLine', () => {
  it('puts the industry in lowercase after a comma', () => {
    const v = verdict({}, { name: 'Apple Inc.', industry: 'Consumer Electronics' })
    expect(aboutLine(v.details)).toBe('Apple Inc., consumer electronics')
  })

  it('keeps short forms in capitals', () => {
    const v = verdict({}, { name: 'Host Hotels', industry: 'REIT - Hotel & Motel' })
    expect(aboutLine(v.details)).toBe('Host Hotels, REIT - hotel & motel')
  })

  it('calls a fund a fund', () => {
    const v = verdict({}, { name: 'iShares MSCI World Islamic', is_fund: true, industry: null })
    expect(aboutLine(v.details)).toBe('iShares MSCI World Islamic, fund')
  })

  it('shows just the name when the industry is missing', () => {
    const v = verdict({}, { name: 'XYZ', industry: null })
    expect(aboutLine(v.details)).toBe('XYZ')
  })
})
