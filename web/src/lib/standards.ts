import type { ComparisonOut, RatioCheckOut, StandardOut } from '../api'
import { baseText, limitPercent, ratioName, valuePercent } from './ratios'

// the names config.yaml uses, in the order the switch shows them
export const STANDARDS = ['aaoifi', 'ftse', 'msci'] as const
export type StandardName = (typeof STANDARDS)[number]

/** Read the standard from the URL, or null if it isn't one we know. */
export function parseStandard(text: string | null): StandardName | null {
  const name = text?.trim().toLowerCase()
  return STANDARDS.find((standard) => standard === name) ?? null
}

/** Find the result for the standard the verdict was judged by. */
export function chosenStandard(verdict: ComparisonOut): StandardOut | null {
  return verdict.standards.find((s) => s.methodology === verdict.methodology) ?? null
}

/** One sentence for each standard that isn't the chosen one, naming the figure that decided it. */
export function otherStandardLines(verdict: ComparisonOut): string[] {
  return verdict.standards
    .filter((s) => s.methodology !== verdict.methodology)
    .map((s) => otherStandardLine(s, verdict))
}

/** Sum up one standard's result in a sentence. */
export function otherStandardLine(standard: StandardOut, verdict: ComparisonOut): string {
  const result = `${standard.methodology} ${standard.passes ? 'passes' : 'fails'}`
  if (verdict.details.is_fund) return `${result}, funds get the same check under every standard.`
  // the failing figure decided it, otherwise debt is the one people look at first
  const deciding = standard.passes
    ? (standard.checks.find((c) => c.name === 'debt') ?? standard.checks[0])
    : standard.checks.find((c) => c.outcome === 'fail')
  if (deciding !== undefined) return `${result}, ${figureText(deciding)}.`
  if (!standard.passes && verdict.details.business_status === 'excluded') {
    return `${result} on the business, the same as here.`
  }
  // nothing failed outright, so it's strict mode turning a check into a fail
  if (!standard.passes) return `${result}, as strict mode only lets fully compliant stocks through.`
  return `${result}.`
}

function figureText(check: RatioCheckOut): string {
  const name = ratioName(check.name).toLowerCase()
  if (check.value === null) return `with no figure for ${name}`
  const value = valuePercent(check.value, check.limit)
  const limit = limitPercent(check.limit)
  return `with ${name} at ${value} ${baseText(check.base)} against a ${limit} limit`
}
