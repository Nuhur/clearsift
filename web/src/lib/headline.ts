import type { ComparisonOut, CompanyOut, StandardOut } from '../api'
import { type OutcomeWord, outcomeWord, ratioName } from './ratios'

// the excluded groups from config.yaml, in plain words
const GROUP_WORDS: Record<string, string> = {
  conventional_banking: 'Conventional banking',
  conventional_insurance: 'Conventional insurance',
  lending: 'Lending',
  alcohol: 'Alcohol',
  pork: 'Pork',
  tobacco: 'Tobacco',
  gambling: 'Gambling',
  adult_entertainment: 'Adult entertainment',
  weapons_and_defence: 'Weapons and defence',
}

const COUNT_WORDS = ['no', 'one', 'two', 'three', 'four']

/** Put an excluded group into plain words, e.g. "Conventional banking". */
export function groupWords(group: string): string {
  // a group added to config.yaml later still reads as words
  const fallback = group.replaceAll('_', ' ')
  return GROUP_WORDS[group] ?? fallback.charAt(0).toUpperCase() + fallback.slice(1)
}

/** Build the big sentence at the top of the stock page. */
export function headline(ticker: string, verdict: ComparisonOut, standard: StandardOut): string {
  const { details } = verdict
  if (details.no_data) return `${ticker} fails. Yahoo Finance has no figures for it.`
  if (details.is_fund) return fundHeadline(ticker, verdict)
  if (details.excluded_group !== null) {
    return `${ticker} fails. ${groupWords(details.excluded_group)} is excluded.`
  }
  if (!standard.passes) return failHeadline(ticker, verdict, standard)

  const figures = standard.checks.filter((c) => c.outcome === 'doubt').length
  const business = details.business_status === 'doubtful'
  if (business && figures > 0) {
    return `${ticker} passes, with its business and ${figureCount(figures)} to check.`
  }
  if (business) return `${ticker} passes, with its business to check.`
  if (figures > 0) return `${ticker} passes, with ${figureCount(figures)} to check.`
  return `${ticker} passes.`
}

/** What the first gate says about the business, and how it went. */
export function businessRow(verdict: ComparisonOut): {
  label: string
  text: string
  word: OutcomeWord
} {
  const { details } = verdict
  const word = outcomeWord(
    details.business_status === 'compliant'
      ? 'pass'
      : details.business_status === 'doubtful'
        ? 'doubt'
        : 'fail',
  )
  if (details.is_fund) {
    const text = details.approved_fund
      ? "It's on your approved list of Sharia-certified funds"
      : details.business_status === 'excluded'
        ? "It's on your always-exclude list"
        : "It isn't on your approved list of Sharia-certified funds"
    return { label: 'What it is', text, word }
  }
  return { label: 'What it does', text: businessText(verdict), word }
}

/** The reasons to check by hand, each without the "check by hand:" the API starts it with. */
export function checkByHandNotes(verdict: ComparisonOut, standard: StandardOut): string[] {
  const notes = [...verdict.warnings, ...(standard.warning === null ? [] : [standard.warning])]
  if (verdict.details.is_fund && verdict.details.business_status === 'doubtful') {
    notes.push('look up its Sharia certification, then add it to approved_funds in config.yaml')
  }
  return notes.map((note) => note.replace(/^check by hand:\s*/i, ''))
}

/** Put an industry label into a sentence, keeping short forms like REIT in capitals. */
export function industryWords(industry: string): string {
  const words = industry.split(' ').map((word, index) => {
    if (/^[A-Z&]{2,}$/.test(word)) return word
    return index === 0 ? word : word.toLowerCase()
  })
  return words.join(' ')
}

/** Name the company and what it does, e.g. "Apple Inc., consumer electronics". */
export function aboutLine(details: CompanyOut): string {
  const what = details.is_fund ? 'fund' : details.industry
  if (what === null) return details.name
  // after a comma it's mid-sentence, so even the first word goes lowercase unless it's a short form
  const [first, ...rest] = industryWords(what).split(' ')
  const lead = /^[A-Z&]{2,}$/.test(first) ? first : first.toLowerCase()
  return `${details.name}, ${[lead, ...rest].join(' ')}`
}

function businessText(verdict: ComparisonOut): string {
  const { details } = verdict
  const industry = details.industry === null ? null : industryWords(details.industry)
  if (details.no_data) return 'Yahoo Finance has no figures for it'
  if (details.excluded_group !== null && industry !== null) {
    const group = groupWords(details.excluded_group).toLowerCase()
    return `${industry} counts as ${group}, which is excluded`
  }
  if (details.sector === null || details.industry === null) {
    return "Yahoo Finance doesn't say what the business does"
  }
  if (details.business_status === 'compliant') return `${industry} isn't an excluded industry`
  if (details.business_status === 'doubtful') {
    return `${industry} can't be judged from the label alone`
  }
  // excluded for some other reason, like the always-exclude list. The API's own words say which
  const reason = verdict.business_reasons[0] ?? "the business didn't get through"
  return reason.charAt(0).toUpperCase() + reason.slice(1)
}

function fundHeadline(ticker: string, verdict: ComparisonOut): string {
  const { details } = verdict
  if (details.approved_fund) return `${ticker} passes as an approved fund.`
  if (details.business_status === 'excluded') {
    return `${ticker} fails. It's on your always-exclude list.`
  }
  if (verdict.passes) return `${ticker} passes, but the fund needs checking by hand.`
  return `${ticker} fails. It isn't on your approved list of funds.`
}

function failHeadline(ticker: string, verdict: ComparisonOut, standard: StandardOut): string {
  const stopped = standard.checks.filter((c) => c.outcome === 'fail')
  if (stopped.length === 1) {
    const [check] = stopped
    const name = ratioName(check.name)
    if (check.value === null) return `${ticker} fails. There's no figure for ${name.toLowerCase()}.`
    return `${ticker} fails. ${name} is over the limit.`
  }
  if (stopped.length > 1) return `${ticker} fails on ${figureCount(stopped.length)}.`
  if (verdict.details.business_status === 'excluded') {
    return `${ticker} fails. Its business didn't get through.`
  }
  // nothing failed outright, so strict mode turned a check into a fail
  return `${ticker} fails. Strict mode only lets fully compliant stocks through.`
}

function figureCount(count: number): string {
  const word = COUNT_WORDS[count] ?? String(count)
  return `${word} figure${count === 1 ? '' : 's'}`
}
