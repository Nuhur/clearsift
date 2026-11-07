import type { ComparisonOut, CompanyOut, RatioCheckOut, StandardOut } from '../api'

// made-up results in the shape the API sends, for the tests

/** A ratio check, under its limit unless the test says otherwise. */
export function check(overrides: Partial<RatioCheckOut> = {}): RatioCheckOut {
  return {
    name: 'debt',
    value: 0.0167,
    limit: 0.3,
    base: 'market_cap',
    outcome: 'pass',
    year: null,
    ...overrides,
  }
}

/** One standard's result, passing unless the test says otherwise. */
export function standard(overrides: Partial<StandardOut> = {}): StandardOut {
  return {
    methodology: 'AAOIFI',
    status: 'compliant',
    passes: true,
    result: 'PASS (compliant)',
    colour: 'green',
    warning: null,
    reasons: [],
    ratios: [],
    checks: [
      check(),
      check({ name: 'cash', value: 0.05 }),
      check({ name: 'interest income', value: 0.0098, limit: 0.05, base: 'revenue' }),
    ],
    ...overrides,
  }
}

/** A stock's full result under every standard, a clean pass unless the test says otherwise. */
export function verdict(
  overrides: Partial<Omit<ComparisonOut, 'details'>> = {},
  details: Partial<CompanyOut> = {},
): ComparisonOut {
  return {
    kind: 'comparison',
    ticker: 'MSFT',
    methodology: 'AAOIFI',
    status: 'compliant',
    passes: true,
    result: 'PASS (compliant)',
    colour: 'green',
    company: ['Technology / Software - Infrastructure'],
    details: {
      name: 'Microsoft Corporation',
      sector: 'Technology',
      industry: 'Software - Infrastructure',
      is_fund: false,
      business_status: 'compliant',
      approved_fund: false,
      excluded_group: null,
      no_data: false,
      ...details,
    },
    warnings: [],
    purification: 'purify 0.98% of dividends',
    purification_ratio: 0.0098,
    purification_year: 2025,
    business_reasons: [],
    standards: [standard(), standard({ methodology: 'FTSE' }), standard({ methodology: 'MSCI' })],
    summary: 'passes under 3 of 3 standards',
    ...overrides,
  }
}
