import type { Base, Outcome, RatioCheckOut } from '../api'

export type OutcomeWord = 'Through' | 'Check' | 'Stopped'

const OUTCOME_WORDS: Record<Outcome, OutcomeWord> = {
  pass: 'Through',
  doubt: 'Check',
  fail: 'Stopped',
}

const BASE_TEXT: Record<Base, string> = {
  market_cap: 'of market value',
  total_assets: 'of total assets',
  revenue: 'of revenue',
}

// the names the API uses, put the way a person would say them
const RATIO_NAMES: Record<string, string> = {
  debt: 'Debt',
  cash: 'Cash',
  'receivables plus cash': 'Receivables and cash',
  'interest income': 'Interest income',
}

/** Put an outcome into the word the page shows. */
export function outcomeWord(outcome: Outcome): OutcomeWord {
  return OUTCOME_WORDS[outcome]
}

/** Say what a ratio is measured against, e.g. "of market value". */
export function baseText(base: Base): string {
  return BASE_TEXT[base]
}

/** Give a ratio its friendly name, e.g. "Receivables and cash". */
export function ratioName(name: string): string {
  // a ratio added to the Python later still gets a readable name
  return RATIO_NAMES[name] ?? name.charAt(0).toUpperCase() + name.slice(1)
}

/** Write a limit as a percentage the way the Python does, e.g. 0.33333 as "33.333%". */
export function limitPercent(limit: number): string {
  // 6 significant figures like Python's :g, which also hides 0.3 * 100 = 30.000000000000004
  return `${Number((limit * 100).toPrecision(6))}%`
}

/** Write a ratio as a percentage, never letting rounding make a pass look like a fail. */
export function valuePercent(value: number, limit: number): string {
  const shown = `${(value * 100).toFixed(2)}%`
  // same rules as the Python reasons, so the page and the CLI always say the same thing
  if (withinLimit(value, limit) && limit > 0 && Number(shown.slice(0, -1)) >= round6(limit * 100)) {
    return `just under ${limitPercent(limit)}`
  }
  if (value > 0 && value < 0.00005) return 'under 0.01%'
  return shown
}

/** Place a value on the bar, from 0 at the left to 1 at the right, or null with no figure. */
export function scalePosition(value: number | null, limit: number): number | null {
  if (value === null) return null
  // a zero limit has no width to scale by, so anything over nothing goes to the far end
  if (limit <= 0) return value <= 0 ? 0 : 1
  // the scale runs to twice the limit, so the limit always sits in the middle
  return Math.min(Math.max(value / (limit * 2), 0), 1)
}

/** Whether a value is at or past its limit, so it didn't get under. */
export function isOverLimit(value: number | null, limit: number): boolean {
  return value !== null && !withinLimit(value, limit)
}

/** Whether a value is past the right-hand end of the bar. */
export function isOffScale(value: number | null, limit: number): boolean {
  if (value === null) return false
  return limit <= 0 ? value > 0 : value > limit * 2
}

/** Describe a bar for screen readers, e.g. "Debt 1.67%, limit 30%". */
export function barLabel(check: RatioCheckOut): string {
  const name = ratioName(check.name)
  const limit = limitPercent(check.limit)
  if (check.value === null) return `${name}, no figure, limit ${limit}`
  return `${name} ${valuePercent(check.value, check.limit)}, limit ${limit}`
}

/** Say which report an older figure came from, or null when it's from the latest one. */
export function reportYearText(check: RatioCheckOut): string | null {
  return check.year === null ? null : `From the ${check.year} report`
}

/** The small line under a ratio's name, e.g. "of market value, limit 30%". */
export function ratioSubline(check: RatioCheckOut): string {
  return `${baseText(check.base)}, limit ${limitPercent(check.limit)}`
}

function withinLimit(value: number, limit: number): boolean {
  // a limit of 0 means none at all, matching _within_limit in ratios.py
  return limit === 0 ? value === 0 : value < limit
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6
}
