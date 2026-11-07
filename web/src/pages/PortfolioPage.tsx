import { getPortfolio } from '../api'
import { ApiView } from '../components/ApiView'
import { StatusBadge } from '../components/StatusBadge'
import { statusWord } from '../status'
import { useApi } from '../useApi'

// never asks for values, so no prices or quantities ever reach this page
const loadPortfolio = (signal: AbortSignal) => getPortfolio({}, signal)

/** Placeholder portfolio page: each holding and its status. */
export function PortfolioPage() {
  const state = useApi('portfolio', loadPortfolio)
  return (
    <>
      <h1 className="mb-4 text-3xl font-extrabold">Portfolio</h1>
      <ApiView state={state}>
        {(portfolio) => (
          <>
            <p className="mb-3">
              {portfolio.holdings.length} {portfolio.holdings.length === 1 ? 'holding' : 'holdings'}
            </p>
            <ul className="divide-y divide-line2 rounded-md border border-line bg-surface">
              {portfolio.holdings.map((holding) => (
                <li
                  key={holding.t212_ticker}
                  className="flex items-center justify-between gap-4 px-4 py-3"
                >
                  <span className="font-medium text-ink">{holding.title}</span>
                  <StatusBadge word={statusWord(holding.verdict)} />
                </li>
              ))}
            </ul>
          </>
        )}
      </ApiView>
    </>
  )
}
