import { useCallback } from 'react'
import { useParams } from 'react-router'
import { getScreen, type ScreenResult } from '../api'
import { ApiView } from '../components/ApiView'
import { StatusBadge } from '../components/StatusBadge'
import { statusWord } from '../status'
import { useApi } from '../useApi'

/** Placeholder stock page: one ticker's status and reasons. */
export function StockPage() {
  const ticker = (useParams().ticker ?? '').trim().toUpperCase()
  const load = useCallback((signal: AbortSignal) => getScreen([ticker], {}, signal), [ticker])
  const state = useApi(ticker, load)
  return (
    <>
      <h1 className="mb-4 text-3xl font-extrabold break-words">{ticker}</h1>
      <ApiView state={state}>{(screen) => <Result result={screen.results[0]} />}</ApiView>
    </>
  )
}

function Result({ result }: { result: ScreenResult | undefined }) {
  // the API always sends one back for one ticker, but don't trust that blindly
  if (result === undefined) return <StatusBadge word="Couldn't be read" />
  const reasons =
    result.kind === 'error'
      ? [result.message]
      : result.kind === 'verdict'
        ? result.reasons
        : [...result.business_reasons, ...result.standards.flatMap((s) => s.reasons)]
  return (
    <>
      <p className="mb-4">
        <StatusBadge word={statusWord(result)} />
      </p>
      <h2 className="mb-2 text-lg font-bold">Reasons</h2>
      <ul className="list-disc space-y-1 pl-5">
        {/* two standards can give the same reason, so the text alone isn't a unique key */}
        {reasons.map((reason, index) => (
          <li key={`${index}-${reason}`}>{reason}</li>
        ))}
      </ul>
    </>
  )
}
