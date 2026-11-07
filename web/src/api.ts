// Types match src/clearsift/api/schemas.py. If you change one, change the other.

export type Status = 'compliant' | 'doubtful' | 'excluded'
export type Colour = 'green' | 'amber' | 'red'
export type Outcome = 'pass' | 'doubt' | 'fail'
// what a ratio is divided by
export type Base = 'market_cap' | 'total_assets' | 'revenue'

export interface RatioOut {
  name: string
  value: number
  limit: number
  passed: boolean
}

export interface RatioCheckOut {
  name: string
  // null when the figure was missing, so there's nothing to draw
  value: number | null
  limit: number
  base: Base
  outcome: Outcome
}

export interface CompanyOut {
  // falls back to the ticker when yfinance has no name
  name: string
  sector: string | null
  industry: string | null
  is_fund: boolean
  approved_fund: boolean
  // the config group that excluded the business, e.g. conventional_banking
  excluded_group: string | null
  // yfinance gave nothing at all
  no_data: boolean
}

export interface VerdictOut {
  kind: 'verdict'
  ticker: string
  methodology: string
  status: Status
  passes: boolean
  result: string
  colour: Colour
  company: string[]
  details: CompanyOut
  warnings: string[]
  purification: string | null
  purification_ratio: number | null
  purification_year: number | null
  reasons: string[]
  ratios: RatioOut[]
  checks: RatioCheckOut[]
}

export interface StandardOut {
  methodology: string
  status: Status
  passes: boolean
  result: string
  colour: Colour
  warning: string | null
  reasons: string[]
  ratios: RatioOut[]
  checks: RatioCheckOut[]
}

export interface ComparisonOut {
  kind: 'comparison'
  ticker: string
  // the standard picked in config.yaml, which decides status and passes
  methodology: string
  status: Status
  passes: boolean
  result: string
  colour: Colour
  company: string[]
  details: CompanyOut
  warnings: string[]
  purification: string | null
  // these follow the chosen standard, so a fail there means nothing to purify
  purification_ratio: number | null
  purification_year: number | null
  business_reasons: string[]
  standards: StandardOut[]
  summary: string
}

export interface TickerError {
  kind: 'error'
  ticker: string
  message: string
}

export type ScreenResult = VerdictOut | ComparisonOut | TickerError

export interface ScreenOut {
  results: ScreenResult[]
}

export interface PricePointOut {
  // YYYY-MM-DD
  date: string
  close: number
}

export interface StockDetailOut {
  ticker: string
  verdict: ComparisonOut
  prices: PricePointOut[]
}

export interface HoldingValuesOut {
  quantity: number | null
  average_price: number | null
  current_price: number | null
  currency: string | null
}

export interface HoldingOut {
  t212_ticker: string
  yahoo_ticker: string | null
  title: string
  // null when the ticker couldn't be converted, so it was never screened
  verdict: VerdictOut | ComparisonOut | null
  message: string | null
  // only filled in when show_values is asked for
  values: HoldingValuesOut | null
}

export interface PortfolioOut {
  holdings: HoldingOut[]
  summary: string
  review: string[]
}

export interface HealthOut {
  status: 'ok'
}

export interface ErrorOut {
  message: string
}

export const START_HINT = 'Start it with: clearsift serve'

/** An API failure, split into what went wrong and what to do about it. */
export class ApiError extends Error {
  readonly status: number | null
  readonly hint: string

  constructor(message: string, hint: string, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.hint = hint
  }
}

type Params = Record<string, string | boolean | undefined>

export interface ScreenOptions {
  compare?: boolean
  refresh?: boolean
}

export interface PortfolioOptions {
  compare?: boolean
  refresh?: boolean
  showValues?: boolean
}

/** Check the API is up. */
export function getHealth(signal?: AbortSignal): Promise<HealthOut> {
  return get('/api/health', {}, signal)
}

/** Screen one or more tickers. */
export function getScreen(
  tickers: string[],
  options: ScreenOptions = {},
  signal?: AbortSignal,
): Promise<ScreenOut> {
  return get(
    '/api/screen',
    { tickers: tickers.join(','), compare: options.compare, refresh: options.refresh },
    signal,
  )
}

export interface StockOptions {
  refresh?: boolean
  // aaoifi, ftse or msci. Left out, the API uses the one in config.yaml
  standard?: string
}

/** Get one stock's verdict under every standard, plus a year of closing prices. */
export function getStock(
  ticker: string,
  options: StockOptions = {},
  signal?: AbortSignal,
): Promise<StockDetailOut> {
  return get(
    `/api/stocks/${encodeURIComponent(ticker)}`,
    { refresh: options.refresh, standard: options.standard },
    signal,
  )
}

/** Screen the open Trading 212 positions. */
export function getPortfolio(
  options: PortfolioOptions = {},
  signal?: AbortSignal,
): Promise<PortfolioOut> {
  return get(
    '/api/portfolio',
    { compare: options.compare, refresh: options.refresh, show_values: options.showValues },
    signal,
  )
}

async function get<T>(path: string, params: Params, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    // leave out anything not set, so the API's own defaults apply
    if (value !== undefined) query.set(key, String(value))
  }
  const url = query.size ? `${path}?${query}` : path

  let response: Response
  try {
    // GET only, the API has nothing that changes anything and neither should this
    response = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, signal })
  } catch (error) {
    // let a cancelled request stay cancelled, it isn't a failure to show
    if (signal?.aborted) throw error
    throw new ApiError("Can't reach Clearsift", START_HINT)
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // not JSON, dealt with below
  }
  if (!response.ok) throw errorFor(response.status, body)
  if (body === null) {
    throw new ApiError(
      "Clearsift sent back something that isn't JSON",
      'Check the terminal running clearsift serve.',
      response.status,
    )
  }
  return body as T
}

/** Turn an error response into a message and a next step. */
export function errorFor(status: number, body: unknown): ApiError {
  const message = messageOf(body)
  // with clearsift serve down, the Vite proxy answers itself with an empty 5xx
  if (message === null) {
    if (status >= 500) return new ApiError("Can't reach Clearsift", START_HINT, status)
    return new ApiError(
      `Clearsift sent back an error (${status})`,
      'Check the terminal running clearsift serve.',
      status,
    )
  }
  // the API hides crash details on purpose, they're in the server's terminal instead
  if (message === 'something went wrong') {
    return new ApiError(
      'Clearsift hit an unexpected error',
      'Check the terminal running clearsift serve for the details.',
      status,
    )
  }
  return new ApiError(sentence(message), hintFor(status, message), status)
}

function hintFor(status: number, message: string): string {
  if (message.startsWith('Trading 212 error: missing')) {
    return 'Add your Trading 212 key and secret to .env (see .env.example), then restart clearsift serve.'
  }
  if (message.startsWith('Trading 212 error:')) {
    return 'Check your Trading 212 key in .env, or try again in a minute.'
  }
  if (message.startsWith('config error:')) return 'Fix config.yaml, then reload this page.'
  if (status === 400 || status === 422) return 'Check the ticker and try again.'
  return 'Try again, and if it keeps happening check the terminal running clearsift serve.'
}

function messageOf(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('message' in body)) return null
  const { message } = body as ErrorOut
  return typeof message === 'string' && message.trim() ? message : null
}

function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
