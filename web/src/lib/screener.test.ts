import { describe, expect, it } from 'vitest'
import type { ScreenResult, TickerError } from '../api'
import { check, standard, verdict } from './fixtures'
import {
  MAX_TICKERS,
  addTickers,
  cleanTicker,
  columnHeadings,
  compareSummary,
  fundText,
  parseScreenerUrl,
  passesUnder,
  rowResult,
  sameTickers,
  screenHeadline,
  screenerLink,
  screenerSearch,
  shortWord,
} from './screener'

const FAILING = verdict(
  { ticker: 'JPM', passes: false, status: 'excluded' },
  { business_status: 'excluded', excluded_group: 'conventional_banking' },
)
const failingEverywhere = {
  ...FAILING,
  standards: FAILING.standards.map((s) => ({ ...s, passes: false, status: 'excluded' as const })),
}
const ERROR: TickerError = {
  kind: 'error',
  ticker: 'BAD',
  message: "that doesn't look like a ticker",
}

describe('cleanTicker', () => {
  it('trims and uppercases', () => {
    expect(cleanTicker('  aapl ')).toBe('AAPL')
    expect(cleanTicker('vod.l')).toBe('VOD.L')
  })

  it('gives nothing for blank text', () => {
    expect(cleanTicker('   ')).toBeNull()
  })
})

describe('addTickers', () => {
  it('adds new tickers in order and skips repeats', () => {
    expect(addTickers(['AAPL'], 'msft, aapl jpm')).toEqual({
      tickers: ['AAPL', 'MSFT', 'JPM'],
      refused: 0,
    })
  })

  it('stops at the cap and says how many it left out', () => {
    const full = Array.from({ length: MAX_TICKERS - 1 }, (_, i) => `T${i}`)
    expect(addTickers(full, 'A B C')).toEqual({ tickers: [...full, 'A'], refused: 2 })
  })

  it("doesn't count a repeat as refused when full", () => {
    const full = Array.from({ length: MAX_TICKERS }, (_, i) => `T${i}`)
    expect(addTickers(full, 'T0').refused).toBe(0)
  })
})

describe('parseScreenerUrl', () => {
  it('reads tickers, standard and compare', () => {
    const params = new URLSearchParams('tickers=aapl,MSFT,,jpm,msft&standard=FTSE&compare=1')
    expect(parseScreenerUrl(params)).toEqual({
      tickers: ['AAPL', 'MSFT', 'JPM'],
      standard: 'ftse',
      compare: true,
    })
  })

  it('gives null tickers when there are none', () => {
    expect(parseScreenerUrl(new URLSearchParams('')).tickers).toBeNull()
    expect(parseScreenerUrl(new URLSearchParams('tickers=')).tickers).toBeNull()
  })

  it("ignores a standard it doesn't know and any compare that isn't 1", () => {
    const params = new URLSearchParams('tickers=AAPL&standard=nope&compare=yes')
    expect(parseScreenerUrl(params)).toEqual({ tickers: ['AAPL'], standard: null, compare: false })
  })

  it('caps a long link at the limit', () => {
    const tickers = Array.from({ length: 30 }, (_, i) => `T${i}`).join(',')
    expect(parseScreenerUrl(new URLSearchParams(`tickers=${tickers}`)).tickers).toHaveLength(
      MAX_TICKERS,
    )
  })
})

describe('screenerSearch', () => {
  it('builds a readable link', () => {
    expect(screenerSearch({ tickers: ['AAPL', 'MSFT'], standard: 'ftse', compare: true })).toBe(
      'tickers=AAPL,MSFT&standard=ftse&compare=1',
    )
  })

  it("leaves out what isn't set", () => {
    expect(screenerSearch({ tickers: null, standard: null, compare: false })).toBe('')
  })

  it('encodes characters a ticker can have', () => {
    const search = screenerSearch({
      tickers: ['^GSPC', 'GBPUSD=X'],
      standard: null,
      compare: false,
    })
    expect(parseScreenerUrl(new URLSearchParams(search)).tickers).toEqual(['^GSPC', 'GBPUSD=X'])
  })
})

describe('sameTickers', () => {
  it('compares lists in order', () => {
    expect(sameTickers(['A', 'B'], ['A', 'B'])).toBe(true)
    expect(sameTickers(['A', 'B'], ['A'])).toBe(false)
    expect(sameTickers(['A', 'B'], ['B', 'A'])).toBe(false)
  })
})

describe('screenHeadline', () => {
  const pass = verdict({ ticker: 'MSFT' })

  it('counts some getting through', () => {
    expect(screenHeadline([pass, failingEverywhere, verdict({ ticker: 'AAPL' })], 'aaoifi')).toBe(
      '2 of 3 get through.',
    )
    expect(screenHeadline([pass, failingEverywhere, ERROR], 'aaoifi')).toBe('1 of 3 gets through.')
  })

  it('says when all get through', () => {
    expect(screenHeadline([pass, pass, pass], 'aaoifi')).toBe('All 3 get through.')
  })

  it('says when none get through', () => {
    expect(screenHeadline([failingEverywhere, ERROR, failingEverywhere], 'aaoifi')).toBe(
      'None of the 3 get through.',
    )
  })

  it('reads well for one or two', () => {
    expect(screenHeadline([pass], 'aaoifi')).toBe('MSFT gets through.')
    expect(screenHeadline([ERROR], 'aaoifi')).toBe("BAD doesn't get through.")
    expect(screenHeadline([pass, pass], 'aaoifi')).toBe('Both get through.')
    expect(screenHeadline([ERROR, failingEverywhere], 'aaoifi')).toBe('Neither gets through.')
  })

  it('follows the picked standard', () => {
    const split = verdict({}, {})
    split.standards[1] = { ...split.standards[1], passes: false }
    expect(screenHeadline([split, pass], 'aaoifi')).toBe('Both get through.')
    expect(screenHeadline([split, pass], 'ftse')).toBe('1 of 2 gets through.')
  })
})

describe('passesUnder', () => {
  it('never passes an error row', () => {
    expect(passesUnder(ERROR, 'aaoifi')).toBe(false)
  })
})

describe('compareSummary', () => {
  it('counts the ones that pass everywhere', () => {
    const split = verdict()
    split.standards[2] = { ...split.standards[2], passes: false }
    const results: ScreenResult[] = [verdict(), split, ERROR]
    expect(compareSummary(results)).toBe('1 of 3 pass under all three standards.')
  })

  it('reads well for one stock', () => {
    expect(compareSummary([verdict()])).toBe('It passes under all three standards.')
    expect(compareSummary([ERROR])).toBe("It doesn't pass under all three standards.")
  })
})

describe('rowResult', () => {
  it('passes cleanly', () => {
    expect(rowResult(verdict(), 'aaoifi')).toEqual({
      word: 'Passes',
      reason: 'Every figure is under its limit',
    })
  })

  it('passes with what to check', () => {
    const doubtful = verdict({ status: 'doubtful' })
    doubtful.standards[0] = standard({
      status: 'doubtful',
      warning: "check by hand: interest income isn't in the latest report",
    })
    expect(rowResult(doubtful, 'aaoifi')).toEqual({
      word: 'Passes, check by hand',
      reason: "Interest income isn't in the latest report",
    })
  })

  it('fails with the same reason as the stock page', () => {
    expect(rowResult(failingEverywhere, 'aaoifi')).toEqual({
      word: 'Fails',
      reason: 'Conventional banking is excluded',
    })
  })

  it('names the failing figure', () => {
    const v = verdict()
    v.standards[1] = standard({
      methodology: 'FTSE',
      passes: false,
      checks: [check({ value: 0.4, outcome: 'fail' })],
    })
    expect(rowResult(v, 'ftse')).toEqual({ word: 'Fails', reason: 'Debt is over the limit' })
    expect(rowResult(v, 'aaoifi').word).toBe('Passes')
  })

  it("couldn't read an error row", () => {
    expect(rowResult(ERROR, 'aaoifi')).toEqual({
      word: "Couldn't be read",
      reason: "That doesn't look like a ticker",
    })
  })

  it('passes an approved fund', () => {
    expect(rowResult(verdict({}, { is_fund: true, approved_fund: true }), 'aaoifi')).toEqual({
      word: 'Passes',
      reason: 'On your approved list',
    })
  })
})

describe('shortWord', () => {
  it('puts each standard into one word', () => {
    expect(shortWord(standard())).toBe('Passes')
    expect(shortWord(standard({ status: 'doubtful' }))).toBe('Check')
    expect(shortWord(standard({ passes: false, status: 'doubtful' }))).toBe('Fails')
  })
})

describe('columnHeadings', () => {
  it('comes from the picked standard', () => {
    const v = verdict()
    v.standards[1] = standard({
      methodology: 'FTSE',
      checks: [
        check({ limit: 0.33333, base: 'total_assets' }),
        check({ name: 'receivables plus cash', limit: 0.5, base: 'total_assets' }),
      ],
    })
    expect(columnHeadings([v], 'ftse')).toEqual([
      'Debt, limit 33.333%',
      'Receivables and cash, limit 50%',
    ])
    expect(columnHeadings([v], 'aaoifi')).toEqual([
      'Debt, limit 30%',
      'Cash, limit 30%',
      'Interest income, limit 5%',
    ])
  })

  it('skips funds and errors', () => {
    const fund = verdict({}, { is_fund: true })
    fund.standards = fund.standards.map((s) => ({ ...s, checks: [] }))
    expect(columnHeadings([ERROR, fund], 'aaoifi')).toEqual([])
    expect(columnHeadings([ERROR, fund, verdict()], 'aaoifi')).toHaveLength(3)
  })
})

describe('fundText', () => {
  it('says whether the fund is approved', () => {
    expect(fundText(verdict({}, { is_fund: true, approved_fund: true }))).toBe('Approved fund')
    expect(fundText(verdict({}, { is_fund: true }))).toBe('Fund not on your approved list')
  })
})

describe('screenerLink', () => {
  it('keeps the current screen when already on the screener', () => {
    expect(screenerLink('/screener', '?tickers=AAPL,MSFT&standard=ftse')).toBe(
      '/screener?tickers=AAPL,MSFT&standard=ftse',
    )
  })

  it('is just the screener with nothing to keep', () => {
    expect(screenerLink('/screener', '')).toBe('/screener')
  })

  it('starts fresh from any other page', () => {
    expect(screenerLink('/stock/AAPL', '?standard=ftse')).toBe('/screener')
    expect(screenerLink('/', '')).toBe('/screener')
  })
})
