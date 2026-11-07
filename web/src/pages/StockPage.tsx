import { type ReactNode, Suspense, lazy, useCallback } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { ApiError, type StockDetailOut, getStock } from '../api'
import { ApiErrorBox } from '../components/ApiView'
import { Block, HEADLINE } from '../components/Block'
import { PurificationPanel } from '../components/PurificationPanel'
import { SievePanel } from '../components/SievePanel'
import { StandardSwitch } from '../components/StandardSwitch'
import { aboutLine, headline } from '../lib/headline'
import {
  type StandardName,
  chosenStandard,
  otherStandardLines,
  parseStandard,
} from '../lib/standards'
import { useApi } from '../useApi'

// the chart library is most of the bundle, so only the stock page loads it
const PriceChart = lazy(() =>
  import('../components/PriceChart').then((module) => ({ default: module.PriceChart })),
)

const PANEL = 'rounded-lg border border-line bg-surface p-5 sm:p-6'

/** One stock's result under the picked standard, with purification, prices and the others. */
export function StockPage() {
  const ticker = (useParams().ticker ?? '').trim().toUpperCase()
  const [params, setParams] = useSearchParams()
  const asked = parseStandard(params.get('standard'))
  const load = useCallback(
    (signal: AbortSignal) => getStock(ticker, { standard: asked ?? undefined }, signal),
    [ticker, asked],
  )
  const state = useApi(`${ticker}|${asked ?? ''}`, load)
  const data = state.state === 'done' ? state.data : null
  // with nothing in the URL the API picks the standard from config.yaml, so show that one
  const selected = asked ?? (data === null ? null : parseStandard(data.verdict.methodology))

  const pick = (standard: StandardName) => {
    // replace, so flicking between standards doesn't fill up the back button
    setParams(
      (current) => {
        current.set('standard', standard)
        return current
      },
      { replace: true },
    )
  }

  return (
    <>
      <Link
        to="/screener"
        className="inline-flex min-h-11 items-center gap-1.5 font-medium text-action"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          className="size-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10 3 5 8l5 5" />
        </svg>
        Back to screener
      </Link>
      {state.state === 'loading' && <Loading ticker={ticker} selected={selected} onPick={pick} />}
      {state.state === 'error' && (
        <Failed ticker={ticker} error={state.error} selected={selected} onPick={pick} />
      )}
      {data !== null && <Result data={data} selected={selected} onPick={pick} />}
    </>
  )
}

interface SwitchProps {
  selected: StandardName | null
  onPick: (standard: StandardName) => void
}

function Result({ data, selected, onPick }: { data: StockDetailOut } & SwitchProps) {
  const { verdict } = data
  const standard = chosenStandard(verdict)
  if (standard === null) {
    // the API always includes the chosen standard, but don't trust that blindly
    const error = new ApiError(
      'Clearsift sent back a result without the chosen standard',
      'Check the terminal running clearsift serve.',
    )
    return <Failed ticker={data.ticker} error={error} selected={selected} onPick={onPick} />
  }
  const others = otherStandardLines(verdict)
  return (
    <>
      <Top selected={selected} onPick={onPick}>
        <p className="text-muted">{aboutLine(verdict.details)}</p>
        <h1 className={`mt-1 ${HEADLINE}`}>{headline(data.ticker, verdict, standard)}</h1>
      </Top>
      <Columns>
        {/* keyed so a new result mounts afresh and the dots slide in again */}
        <SievePanel
          key={`${data.ticker}-${standard.methodology}`}
          ticker={data.ticker}
          verdict={verdict}
          standard={standard}
        />
        <div className="space-y-6">
          <PurificationPanel verdict={verdict} />
          <section className={PANEL} aria-labelledby="prices">
            <h2 id="prices" className="font-extrabold">
              Price over the last year
            </h2>
            {data.prices.length > 0 ? (
              <div className="mt-3">
                <Suspense fallback={<Block className="h-52 w-full" />}>
                  <PriceChart prices={data.prices} />
                </Suspense>
                {/* the logo is switched off in the chart, so the licence credit lives here */}
                <p className="mt-2 text-xs text-muted">
                  Chart by{' '}
                  <a
                    href="https://www.tradingview.com/lightweight-charts/"
                    className="underline hover:text-ink"
                  >
                    TradingView Lightweight Charts
                  </a>
                </p>
              </div>
            ) : (
              <p className="mt-1">The price history couldn't be loaded.</p>
            )}
          </section>
          {others.length > 0 && (
            <section className={PANEL} aria-labelledby="others">
              <h2 id="others" className="font-extrabold">
                Under the other standards
              </h2>
              <ul className="mt-2 space-y-2">
                {others.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </Columns>
    </>
  )
}

function Loading({ ticker, selected, onPick }: { ticker: string } & SwitchProps) {
  return (
    <>
      <Top selected={selected} onPick={onPick}>
        <p role="status" className="sr-only">
          Loading {ticker}
        </p>
        {/* the same shapes as the real page, so nothing jumps when it lands */}
        <div aria-hidden="true">
          <Block className="h-5 w-56" />
          <Block className="mt-3 h-10 w-[min(42rem,80vw)] sm:h-16" />
        </div>
      </Top>
      <div aria-hidden="true">
        <Columns>
          <div className={PANEL}>
            <Block className="h-6 w-72 max-w-full" />
            <Block className="mt-3 h-4 w-full max-w-md" />
            <div className="mt-8 space-y-7">
              {[0, 1, 2, 3].map((row) => (
                <Block key={row} className="h-8 w-full" />
              ))}
            </div>
          </div>
          <div className="space-y-6">
            <Block className="h-44 w-full rounded-lg" />
            <Block className="h-64 w-full rounded-lg" />
            <Block className="h-28 w-full rounded-lg" />
          </div>
        </Columns>
      </div>
    </>
  )
}

function Failed({
  ticker,
  error,
  selected,
  onPick,
}: { ticker: string; error: ApiError } & SwitchProps) {
  return (
    <>
      <Top selected={selected} onPick={onPick}>
        <h1 className={HEADLINE}>{ticker}</h1>
      </Top>
      <div className="mt-8">
        <ApiErrorBox error={error}>
          <Link to="/screener" className="mt-2 inline-block font-medium text-action underline">
            Back to the screener
          </Link>
        </ApiErrorBox>
      </div>
    </>
  )
}

function Top({ selected, onPick, children }: SwitchProps & { children: ReactNode }) {
  return (
    <div className="mt-4 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">{children}</div>
      <StandardSwitch value={selected} onChange={onPick} />
    </div>
  )
}

function Columns({ children }: { children: ReactNode }) {
  return (
    <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
      {children}
    </div>
  )
}
