import type { ComparisonOut, ScreenResult, StandardOut, TickerError } from '../api'
import { checkByHandNotes, failReason } from './headline'
import { limitPercent, ratioName } from './ratios'
import { STANDARDS, type StandardName, parseStandard } from './standards'

// matches MAX_TICKERS in api/app.py, which refuses anything over it
export const MAX_TICKERS = 20
export const DEFAULT_TICKERS = ['AAPL', 'MSFT', 'JPM']

const COUNT_WORDS = ['no', 'one', 'two', 'three', 'four', 'five']

export interface ScreenerUrl {
  // null when the link has no tickers, so the page starts with the defaults unscreened
  tickers: string[] | null
  standard: StandardName | null
  compare: boolean
}

export type RowWord = 'Passes' | 'Passes, check by hand' | 'Fails' | "Couldn't be read"
export type ShortWord = 'Passes' | 'Check' | 'Fails'

/** Tidy one typed ticker, or null if there's nothing left of it. */
export function cleanTicker(text: string): string | null {
  const ticker = text.trim().toUpperCase()
  return ticker === '' ? null : ticker
}

/** Add typed tickers to the list, skipping repeats and stopping at the cap. */
export function addTickers(
  current: string[],
  text: string,
): { tickers: string[]; refused: number } {
  const tickers = [...current]
  let refused = 0
  // people paste lists with commas or spaces, and a ticker never has either in it
  for (const part of text.split(/[,\s]+/)) {
    const ticker = cleanTicker(part)
    if (ticker === null || tickers.includes(ticker)) continue
    if (tickers.length >= MAX_TICKERS) {
      refused += 1
      continue
    }
    tickers.push(ticker)
  }
  return { tickers, refused }
}

/** Read the screener's state from the address bar. */
export function parseScreenerUrl(params: URLSearchParams): ScreenerUrl {
  const raw = params.get('tickers')
  const tickers = raw === null ? null : addTickers([], raw).tickers
  return {
    // an empty tickers= is treated like none at all, there's nothing to screen
    tickers: tickers === null || tickers.length === 0 ? null : tickers,
    standard: parseStandard(params.get('standard')),
    compare: params.get('compare') === '1',
  }
}

/** Write the screener's state as a query string, e.g. "tickers=AAPL,MSFT&standard=ftse". */
export function screenerSearch(state: ScreenerUrl): string {
  const parts: string[] = []
  // built by hand so the commas stay readable instead of turning into %2C
  if (state.tickers !== null && state.tickers.length > 0) {
    parts.push(`tickers=${state.tickers.map(encodeURIComponent).join(',')}`)
  }
  if (state.standard !== null) parts.push(`standard=${state.standard}`)
  if (state.compare) parts.push('compare=1')
  return parts.join('&')
}

/** Where the Screener nav link goes, keeping the current screen when you're already on it. */
export function screenerLink(pathname: string, search: string): string {
  // the page keeps showing its results, so the link has to keep the URL that matches them
  return pathname === '/screener' ? `/screener${search}` : '/screener'
}

/** Whether two ticker lists are the same, in the same order. */
export function sameTickers(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((ticker, index) => ticker === b[index])
}

/** Find one stock's result under the given standard. */
export function standardFor(verdict: ComparisonOut, name: StandardName): StandardOut | null {
  return verdict.standards.find((s) => s.methodology.toLowerCase() === name) ?? null
}

/** Whether a result row gets through under the given standard. */
export function passesUnder(result: ScreenResult, name: StandardName): boolean {
  if (result.kind !== 'comparison') return false
  return standardFor(result, name)?.passes ?? false
}

/** Build the big sentence above the results, e.g. "2 of 3 get through." */
export function screenHeadline(results: ScreenResult[], name: StandardName): string {
  const total = results.length
  const passed = results.filter((r) => passesUnder(r, name)).length
  if (total === 1) {
    return `${results[0].ticker} ${passed === 1 ? 'gets' : "doesn't get"} through.`
  }
  if (passed === total) return total === 2 ? 'Both get through.' : `All ${total} get through.`
  if (passed === 0)
    return total === 2 ? 'Neither gets through.' : `None of the ${total} get through.`
  return `${passed} of ${total} ${passed === 1 ? 'gets' : 'get'} through.`
}

/** Say how many stocks pass under every standard, for the compare view. */
export function compareSummary(results: ScreenResult[]): string {
  const total = results.length
  // config.yaml decides how many standards there are, so count what came back
  const counts = results.map((r) => (r.kind === 'comparison' ? r.standards.length : 0))
  const standards = Math.max(...counts, 0) || STANDARDS.length
  const everywhere = results.filter(
    (r) => r.kind === 'comparison' && r.standards.length > 0 && r.standards.every((s) => s.passes),
  ).length
  const all = `all ${COUNT_WORDS[standards] ?? standards} standards`
  if (total === 1)
    return everywhere === 1 ? `It passes under ${all}.` : `It doesn't pass under ${all}.`
  return `${everywhere} of ${total} pass under ${all}.`
}

/** The result in words for one row, with a short reason under it. */
export function rowResult(
  result: ScreenResult,
  name: StandardName,
): { word: RowWord; reason: string } {
  if (result.kind !== 'comparison') return { word: "Couldn't be read", reason: errorReason(result) }
  const standard = standardFor(result, name)
  if (standard === null) {
    return { word: "Couldn't be read", reason: `No ${name.toUpperCase()} result came back` }
  }
  if (!standard.passes) return { word: 'Fails', reason: failReason(result, standard) }
  const notes = checkByHandNotes(result, standard)
  if (standard.status === 'doubtful' || notes.length > 0) {
    const note = notes[0] ?? 'something needs a closer look'
    return { word: 'Passes, check by hand', reason: sentence(note) }
  }
  if (result.details.is_fund) return { word: 'Passes', reason: 'On your approved list' }
  return { word: 'Passes', reason: 'Every figure is under its limit' }
}

/** One word for a standard's result, for the compare view. */
export function shortWord(standard: StandardOut): ShortWord {
  if (!standard.passes) return 'Fails'
  return standard.status === 'doubtful' ? 'Check' : 'Passes'
}

/** The column headings for the bars, e.g. "Debt, limit 30%", from the first company's checks. */
export function columnHeadings(results: ScreenResult[], name: StandardName): string[] {
  for (const result of results) {
    if (result.kind !== 'comparison' || result.details.is_fund) continue
    const standard = standardFor(result, name)
    // every company has the same checks under a standard, so the first one will do
    if (standard !== null && standard.checks.length > 0) {
      return standard.checks.map((c) => `${ratioName(c.name)}, limit ${limitPercent(c.limit)}`)
    }
  }
  return []
}

/** What the middle of a fund's row says instead of bars. */
export function fundText(result: ComparisonOut): string {
  return result.details.approved_fund ? 'Approved fund' : 'Fund not on your approved list'
}

function errorReason(result: TickerError | ScreenResult): string {
  // the page always asks for every standard, so any other kind is a mismatch with the API
  if (result.kind !== 'error') return "The result came back in a shape this page can't read"
  return sentence(result.message)
}

function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
