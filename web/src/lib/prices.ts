import type { PricePointOut } from '../api'

const DAY = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

/** Sum up the price line in words, for people who can't see the chart. */
export function priceSummary(prices: PricePointOut[]): string {
  if (prices.length === 0) return 'No price history'
  const first = prices[0]
  const last = prices[prices.length - 1]
  // prices come in the stock's own currency, which the API doesn't name, so leave it off
  const from = `${first.close.toFixed(2)} on ${day(first.date)}`
  const to = `${last.close.toFixed(2)} on ${day(last.date)}`
  return `Closing price went from ${from} to ${to}`
}

function day(date: string): string {
  // read as UTC so the date never slips a day in a timezone west of London
  return DAY.format(new Date(`${date}T00:00:00Z`))
}
