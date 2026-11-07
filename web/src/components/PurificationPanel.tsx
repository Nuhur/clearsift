import type { ComparisonOut } from '../api'
import { EXAMPLE_DIVIDEND, purificationFor } from '../lib/purification'

const PLAIN: Record<'fails' | 'fund' | 'unknown', string> = {
  fails: "Purification doesn't apply, because it doesn't pass under this standard.",
  fund: "Funds usually purify their own income. Check the fund's annual report to be sure.",
  unknown:
    "Purification can't be worked out because interest income isn't disclosed. " +
    "Check the company's annual report.",
}

/** How much of each dividend to give away, or why there's no number. */
export function PurificationPanel({ verdict }: { verdict: ComparisonOut }) {
  const purification = purificationFor(verdict)
  if (purification.kind !== 'ratio') {
    return (
      <section className="rounded-lg border border-line bg-surface p-5" aria-labelledby="purify">
        <h2 id="purify" className="font-extrabold">
          Purification
        </h2>
        <p className="mt-1">{PLAIN[purification.kind]}</p>
      </section>
    )
  }
  return (
    <section className="rounded-lg bg-ink p-5 text-paper sm:p-6" aria-labelledby="purify">
      <h2 id="purify" className="font-bold text-paper">
        Give to charity from each dividend
      </h2>
      <p className="mt-1 text-[56px] leading-none font-extrabold tracking-tight">
        {purification.percent}
      </p>
      <p className="mt-3">
        On a £{EXAMPLE_DIVIDEND} dividend, that's {purification.example}.{' '}
        {purification.year === null
          ? 'Always rounded up.'
          : `Based on ${purification.year} interest income, always rounded up.`}
      </p>
    </section>
  )
}
