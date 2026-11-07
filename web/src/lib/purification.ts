import type { ComparisonOut } from '../api'
import { ceilTo, hundredths, multiply, toDecimal } from './decimal'

// just an example to make the percentage real, never anything from the account
export const EXAMPLE_DIVIDEND = 50

export type Purification =
  | { kind: 'fails' }
  | { kind: 'fund' }
  | { kind: 'unknown' }
  | { kind: 'ratio'; percent: string; example: string; year: number | null }

/** Work out how much of a dividend to give away, in pence, always rounded up. */
export function purificationPence(dividend: number, ratio: number): bigint {
  if (!Number.isFinite(dividend) || dividend < 0) {
    throw new RangeError(`dividend must be zero or more, got ${dividend}`)
  }
  // same as the Python: exact decimals, then round up so we never give less than we should
  return ceilTo(multiply(toDecimal(dividend), toDecimal(ratio)), 2)
}

/** Write the share of each dividend as a percentage, rounded up to two places like the CLI. */
export function purificationPercent(ratio: number): string {
  return `${hundredths(ceilTo(multiply(toDecimal(ratio), toDecimal(100)), 2))}%`
}

/** Write an amount in pence as pounds, e.g. 49n as "£0.49". */
export function pounds(pence: bigint): string {
  return `£${hundredths(pence)}`
}

/** Decide what the purification panel says for the chosen standard. */
export function purificationFor(verdict: ComparisonOut): Purification {
  // a stock that doesn't pass shouldn't be held, so there's nothing to purify
  if (!verdict.passes) return { kind: 'fails' }
  if (verdict.details.is_fund) return { kind: 'fund' }
  const ratio = verdict.purification_ratio
  if (ratio === null) return { kind: 'unknown' }
  return {
    kind: 'ratio',
    percent: purificationPercent(ratio),
    example: pounds(purificationPence(EXAMPLE_DIVIDEND, ratio)),
    year: verdict.purification_year,
  }
}
