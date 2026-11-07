import type { ReactNode } from 'react'
import type { ComparisonOut, RatioCheckOut, StandardOut } from '../api'
import { businessRow, checkByHandNotes } from '../lib/headline'
import {
  type OutcomeWord,
  isOffScale,
  outcomeWord,
  ratioName,
  ratioSubline,
  reportYearText,
  valuePercent,
} from '../lib/ratios'
import { type SlidePhase, useSlideIn } from '../useSlideIn'
import { RatioBar } from './RatioBar'

const CIRCLES: Record<OutcomeWord, { mark: string; style: string }> = {
  Through: { mark: '✓', style: 'border-pass bg-passbg text-pass' },
  Check: { mark: '?', style: 'border-warn bg-warnbg text-warntext' },
  Stopped: { mark: '✕', style: 'border-fail bg-failbg text-fail' },
}

const WORDS: Record<OutcomeWord, string> = {
  Through: 'text-pass',
  Check: 'text-warntext',
  Stopped: 'text-fail',
}

/** Each rule as a gate, with where the stock sits against its limit. */
export function SievePanel({
  ticker,
  verdict,
  standard,
}: {
  ticker: string
  verdict: ComparisonOut
  standard: StandardOut
}) {
  const business = businessRow(verdict)
  const notes = checkByHandNotes(verdict, standard)
  const phase = useSlideIn(standard.methodology)
  return (
    <section
      className="rounded-lg border border-line bg-surface p-5 sm:p-6"
      aria-labelledby="sieve"
    >
      <h2 id="sieve" className="text-xl font-extrabold">
        How it went through the sieve
      </h2>
      <p className="mt-1 text-muted">
        Each rule is a gate. The dark line is the limit, and the dot is where {ticker} sits.
      </p>
      {/* the thread runs down through the middle of the circles */}
      <ol className="relative mt-6 space-y-6 before:absolute before:top-3 before:bottom-3 before:left-3 before:w-px before:bg-line3">
        <Row word={business.word}>
          <div className="min-w-0 sm:col-span-2">
            <p className="font-bold text-ink">{business.label}</p>
            <p>{business.text}</p>
          </div>
          <Word word={business.word} />
        </Row>
        {standard.checks.map((check) => (
          <RatioRow key={check.name} check={check} phase={phase} />
        ))}
      </ol>
      {notes.length > 0 && (
        <div className="mt-6 rounded-md bg-warnbg px-4 py-3 text-warntext">
          {notes.map((note) => (
            <p key={note}>
              <strong>Why check by hand:</strong> {note}.
            </p>
          ))}
        </div>
      )}
    </section>
  )
}

function RatioRow({ check, phase }: { check: RatioCheckOut; phase: SlidePhase }) {
  const word = outcomeWord(check.outcome)
  const offScale = isOffScale(check.value, check.limit)
  // an older figure still counts, the row just says how old it is
  const year = reportYearText(check)
  return (
    <Row word={word}>
      <div className="min-w-0">
        <p className="font-bold text-ink">{ratioName(check.name)}</p>
        <p className="text-sm text-muted">{ratioSubline(check)}</p>
      </div>
      {/* on phones the bar drops under the name and value, so it gets the full width */}
      <div className="order-last col-span-2 self-center sm:order-none sm:col-span-1">
        <RatioBar check={check} phase={phase} />
      </div>
      <div className="text-right">
        {check.value !== null && (
          <p className={`font-extrabold ${offScale ? 'text-fail' : 'text-ink'}`}>
            {valuePercent(check.value, check.limit)}
          </p>
        )}
        {year !== null && <p className="text-xs text-muted">{year}</p>}
        <Word word={word} />
      </div>
    </Row>
  )
}

function Row({ word, children }: { word: OutcomeWord; children: ReactNode }) {
  const circle = CIRCLES[word]
  return (
    <li className="relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-4">
      <span
        aria-hidden="true"
        className={`relative z-10 flex size-6 items-center justify-center rounded-full border text-xs font-extrabold ${circle.style}`}
      >
        {circle.mark}
      </span>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)_6rem]">
        {children}
      </div>
    </li>
  )
}

function Word({ word }: { word: OutcomeWord }) {
  return <p className={`text-right text-sm font-bold ${WORDS[word]}`}>{word}</p>
}
