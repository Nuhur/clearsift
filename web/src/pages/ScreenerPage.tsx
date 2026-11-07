import { getScreen } from '../api'
import { ApiView } from '../components/ApiView'
import { StatusBadge } from '../components/StatusBadge'
import { statusWord } from '../status'
import { useApi } from '../useApi'

const TICKERS = ['AAPL', 'MSFT', 'JPM']

const loadScreen = (signal: AbortSignal) => getScreen(TICKERS, {}, signal)

/** Placeholder screener page: a fixed few tickers and their status. */
export function ScreenerPage() {
  const state = useApi(TICKERS.join(','), loadScreen)
  return (
    <>
      <h1 className="mb-4 text-3xl font-extrabold">Screener</h1>
      <ApiView state={state}>
        {(screen) => (
          <ul className="divide-y divide-line2 rounded-md border border-line bg-surface">
            {screen.results.map((result) => (
              <li key={result.ticker} className="flex items-center justify-between gap-4 px-4 py-3">
                <span className="font-medium text-ink">{result.ticker}</span>
                <StatusBadge word={statusWord(result)} />
              </li>
            ))}
          </ul>
        )}
      </ApiView>
    </>
  )
}
