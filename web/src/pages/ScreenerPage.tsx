import { type FormEvent, type ReactNode, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { type ApiError, type ComparisonOut, type ScreenResult, getScreen } from '../api'
import { ApiErrorBox } from '../components/ApiView'
import { Block, HEADLINE } from '../components/Block'
import { RatioBar } from '../components/RatioBar'
import { StandardSwitch } from '../components/StandardSwitch'
import { Switch } from '../components/Switch'
import { TickerTags } from '../components/TickerTags'
import { isOverLimit, ratioName, valuePercent } from '../lib/ratios'
import {
  DEFAULT_TICKERS,
  type RowWord,
  type ScreenerUrl,
  type ShortWord,
  columnHeadings,
  compareSummary,
  fundText,
  parseScreenerUrl,
  rowResult,
  sameTickers,
  screenHeadline,
  screenerSearch,
  shortWord,
  standardFor,
} from '../lib/screener'
import { STANDARDS, type StandardName, parseStandard } from '../lib/standards'
import { asApiError } from '../useApi'
import { type SlidePhase, useSlideIn } from '../useSlideIn'

const ROW_WORDS: Record<RowWord, string> = {
  Passes: 'text-pass',
  'Passes, check by hand': 'text-warntext',
  Fails: 'text-fail',
  "Couldn't be read": 'text-body',
}

const SHORT_WORDS: Record<ShortWord, string> = {
  Passes: 'text-pass',
  Check: 'text-warntext',
  Fails: 'text-fail',
}

// ticker on the left, bars in the middle, result on the right. On phones the bars drop below
const ROW_GRID =
  'grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-3 sm:grid-cols-[10rem_minmax(0,1fr)_13rem]'

interface Request {
  tickers: string[]
  fresh: boolean
  standard: StandardName | null
}

interface Screened {
  tickers: string[]
  results: ScreenResult[]
  // bumped on every new result, so the dots slide in for that and nothing else
  id: number
}

/** Screen a list of tickers under one standard, or compare them under all three. */
export function ScreenerPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const url = parseScreenerUrl(params)

  const [tags, setTags] = useState<string[]>(() => url.tickers ?? DEFAULT_TICKERS)
  const [fresh, setFresh] = useState(false)
  // a shared link with tickers in it screens straight away
  const [request, setRequest] = useState<Request | null>(() =>
    url.tickers === null ? null : { tickers: url.tickers, fresh: false, standard: url.standard },
  )
  const [screened, setScreened] = useState<Screened | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    if (request === null) return
    const controller = new AbortController()
    // the page always asks for every standard, so switching later needs no new request
    getScreen(
      request.tickers,
      { compare: true, refresh: request.fresh, standard: request.standard ?? undefined },
      controller.signal,
    ).then(
      (data) => {
        if (controller.signal.aborted) return
        setScreened((last) => ({
          tickers: request.tickers,
          results: data.results,
          id: (last?.id ?? 0) + 1,
        }))
        setError(null)
        setRequest(null)
      },
      (failure: unknown) => {
        if (controller.signal.aborted) return
        setError(asApiError(failure))
        setRequest(null)
      },
    )
    // pressing Screen again, or leaving the page, drops the old request
    return () => controller.abort()
  }, [request])

  const loading = request !== null
  const phase = useSlideIn(screened?.id ?? 0)
  // with nothing in the URL the API used the config's standard, so show that one
  const shown: StandardName | null = url.standard ?? (screened ? configStandard(screened) : null)
  const viewing = shown ?? STANDARDS[0]

  // replace, so flicking switches doesn't fill up the back button
  const setUrl = (next: Partial<ScreenerUrl>) => {
    const search = screenerSearch({ ...url, ...next })
    navigate({ search: search ? `?${search}` : '' }, { replace: true })
  }

  const screen = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (loading || tags.length === 0) return
    setRequest({ tickers: tags, fresh, standard: url.standard })
    setUrl({ tickers: tags })
  }

  return (
    <>
      <Heading loading={loading} screened={screened} standard={viewing} compare={url.compare} />

      <form
        onSubmit={screen}
        className="mt-8 rounded-lg border border-line bg-surface p-4 sm:p-5"
        aria-label="Screen stocks"
      >
        <TickerTags tickers={tags} onChange={setTags} />
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Switch
            label="Compare standards"
            checked={url.compare}
            onChange={(compare) => setUrl({ compare })}
          />
          <Switch label="Fresh data" checked={fresh} onChange={setFresh} />
          <StandardSwitch value={shown} onChange={(standard) => setUrl({ standard })} />
          <button
            type="submit"
            disabled={loading || tags.length === 0}
            className="min-h-11 rounded-md bg-action px-6 font-bold text-white disabled:opacity-60 sm:ml-auto"
          >
            {loading ? 'Screening' : 'Screen'}
          </button>
        </div>
        {request?.fresh && (
          <p role="status" className="mt-3 text-sm text-muted">
            Getting fresh figures from Yahoo Finance
          </p>
        )}
      </form>

      <div className="mt-6">
        {error !== null && !loading && <ApiErrorBox error={error} />}
        {request !== null && <LoadingRows tickers={request.tickers} />}
        {!loading && error === null && screened !== null && (
          <>
            {!sameTickers(tags, screened.tickers) && (
              <p className="mb-3 text-sm text-muted">Tickers changed. Press Screen to update.</p>
            )}
            <Results
              results={screened.results}
              standard={viewing}
              compare={url.compare}
              phase={phase}
            />
          </>
        )}
      </div>
    </>
  )
}

function Heading({
  loading,
  screened,
  standard,
  compare,
}: {
  loading: boolean
  screened: Screened | null
  standard: StandardName
  compare: boolean
}) {
  if (loading) {
    return (
      <div>
        <p role="status" className="sr-only">
          Screening
        </p>
        <div aria-hidden="true">
          <Block className="h-10 w-[min(36rem,80vw)] sm:h-16" />
          <Block className="mt-4 h-5 w-[min(28rem,70vw)]" />
        </div>
      </div>
    )
  }
  if (screened === null) {
    return (
      <div>
        <h1 className={HEADLINE}>Screen any stock.</h1>
        <p className="mt-3 text-muted">Add tickers below and press Screen.</p>
      </div>
    )
  }
  return (
    <div>
      <h1 className={HEADLINE}>{screenHeadline(screened.results, standard)}</h1>
      <p className="mt-3 text-muted">
        Screened against {standard.toUpperCase()} with figures from Yahoo Finance.
      </p>
      {compare && <p className="mt-1 text-muted">{compareSummary(screened.results)}</p>}
    </div>
  )
}

function Results({
  results,
  standard,
  compare,
  phase,
}: {
  results: ScreenResult[]
  standard: StandardName
  compare: boolean
  phase: SlidePhase
}) {
  const headings = compare ? [] : columnHeadings(results, standard)
  return (
    <div className="rounded-lg border border-line bg-surface">
      {headings.length > 0 && (
        // on phones each bar carries its own label instead
        <div
          aria-hidden="true"
          className={`hidden border-b border-line2 px-5 py-3 text-sm font-bold text-muted sm:grid ${ROW_GRID}`}
        >
          <span>Stock</span>
          <Bars count={headings.length}>
            {headings.map((heading) => (
              <span key={heading}>{heading}</span>
            ))}
          </Bars>
          <span>Result</span>
        </div>
      )}
      <ul className="divide-y divide-line2">
        {results.map((result) => (
          <Row
            key={result.ticker}
            result={result}
            standard={standard}
            compare={compare}
            phase={phase}
          />
        ))}
      </ul>
    </div>
  )
}

function Row({
  result,
  standard,
  compare,
  phase,
}: {
  result: ScreenResult
  standard: StandardName
  compare: boolean
  phase: SlidePhase
}) {
  const { word, reason } = rowResult(result, standard)
  const name = result.kind === 'comparison' ? result.details.name : null
  const to = `/stock/${encodeURIComponent(result.ticker)}?standard=${standard}`
  return (
    <li>
      <Link to={to} className={`${ROW_GRID} px-5 py-4 hover:bg-paper`}>
        <div className="min-w-0">
          <p className="font-extrabold break-words text-ink">{result.ticker}</p>
          {name !== null && name !== result.ticker && (
            <p className="truncate text-sm text-muted">{name}</p>
          )}
        </div>
        <div className="order-last col-span-2 min-w-0 self-center sm:order-none sm:col-span-1">
          {result.kind === 'comparison' && (
            <Middle result={result} standard={standard} compare={compare} phase={phase} />
          )}
        </div>
        <div className="text-right sm:text-left">
          <p className={`font-bold ${ROW_WORDS[word]}`}>{word}</p>
          <p className="text-sm text-muted">{reason}</p>
        </div>
      </Link>
    </li>
  )
}

function Middle({
  result,
  standard,
  compare,
  phase,
}: {
  result: ComparisonOut
  standard: StandardName
  compare: boolean
  phase: SlidePhase
}) {
  if (compare) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {result.standards.map((s) => {
          const word = shortWord(s)
          return (
            <div key={s.methodology}>
              <p className="text-xs font-bold text-muted">{s.methodology}</p>
              <p className={`font-bold ${SHORT_WORDS[word]}`}>{word}</p>
            </div>
          )
        })}
      </div>
    )
  }
  if (result.details.is_fund) return <p className="font-medium text-body">{fundText(result)}</p>
  const checks = standardFor(result, standard)?.checks ?? []
  return (
    <Bars count={checks.length}>
      {checks.map((check) => {
        const year = check.year === null ? null : String(check.year)
        return (
          <div key={check.name} className="min-w-0">
            <p className="truncate text-xs text-muted sm:hidden">{ratioName(check.name)}</p>
            {check.value !== null && (
              <p
                className={`text-sm font-extrabold ${
                  isOverLimit(check.value, check.limit) ? 'text-fail' : 'text-ink'
                }`}
              >
                {valuePercent(check.value, check.limit)}
              </p>
            )}
            <div className="mt-1">
              <RatioBar check={check} phase={phase} size="small" />
            </div>
            {year !== null && (
              // the stock page spells it out, here there's only room for the year
              <p className="mt-1 text-xs text-muted">{year}</p>
            )}
          </div>
        )
      })}
    </Bars>
  )
}

function Bars({ count, children }: { count: number; children: ReactNode }) {
  return (
    <div
      className="grid gap-4"
      // the number of ratios depends on the standard, so the columns can't be fixed in CSS
      style={{ gridTemplateColumns: `repeat(${Math.max(count, 1)}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  )
}

function LoadingRows({ tickers }: { tickers: string[] }) {
  return (
    <ul
      aria-hidden="true"
      className="divide-y divide-line2 rounded-lg border border-line bg-surface"
    >
      {tickers.map((ticker) => (
        <li key={ticker} className={`${ROW_GRID} px-5 py-4`}>
          <div>
            <p className="font-extrabold text-ink">{ticker}</p>
            <Block className="mt-1 h-4 w-24" />
          </div>
          <div className="order-last col-span-2 self-center sm:order-none sm:col-span-1">
            <Block className="h-8 w-full" />
          </div>
          <div>
            <Block className="h-5 w-20" />
            <Block className="mt-1 h-4 w-32" />
          </div>
        </li>
      ))}
    </ul>
  )
}

function configStandard(screened: Screened): StandardName | null {
  // every row was judged by the same standard, so the first real one says which
  const first = screened.results.find((r) => r.kind === 'comparison')
  return first?.kind === 'comparison' ? parseStandard(first.methodology) : null
}
