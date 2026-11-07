import { describe, expect, it } from 'vitest'
import { priceSummary } from './prices'

describe('priceSummary', () => {
  it('names the first and last close', () => {
    const prices = [
      { date: '2025-11-07', close: 228.4 },
      { date: '2026-03-02', close: 210 },
      { date: '2026-11-06', close: 230.1 },
    ]
    expect(priceSummary(prices)).toBe(
      'Closing price went from 228.40 on 7 Nov 2025 to 230.10 on 6 Nov 2026',
    )
  })

  it('copes with no prices', () => {
    expect(priceSummary([])).toBe('No price history')
  })
})
