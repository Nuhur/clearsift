import type { RatioCheckOut } from '../api'
import { type OutcomeWord, barLabel, outcomeWord, scalePosition } from '../lib/ratios'
import type { SlidePhase } from '../useSlideIn'

const DOTS: Record<OutcomeWord, string> = {
  Through: 'bg-pass',
  Check: 'bg-warn',
  Stopped: 'bg-fail',
}

const SIZES = {
  // the stock page's sieve
  large: { box: 'h-6', track: 'top-2 h-2', wall: 'h-6', dot: 'top-1.5 size-3' },
  // a screener row, where several sit side by side
  small: { box: 'h-4', track: 'top-1.5 h-1', wall: 'h-4', dot: 'top-0.5 size-3' },
}

/** One ratio on a scale from 0 to twice its limit, with the limit as a line in the middle. */
export function RatioBar({
  check,
  phase,
  size = 'large',
}: {
  check: RatioCheckOut
  phase: SlidePhase
  size?: keyof typeof SIZES
}) {
  const position = scalePosition(check.value, check.limit)
  if (position === null) return <p className="text-sm font-medium text-muted">No figure</p>
  const style = SIZES[size]
  return (
    <div role="img" aria-label={barLabel(check)} className={`relative ${style.box}`}>
      {/* the left half is under the limit, the right half over it */}
      <div className={`absolute inset-x-0 flex overflow-hidden rounded-full ${style.track}`}>
        <div className="w-1/2 bg-passbg" />
        <div className="w-1/2 bg-failbg" />
      </div>
      <div className={`absolute top-0 left-1/2 w-0.5 -translate-x-1/2 bg-ink ${style.wall}`} />
      <div
        className={`absolute -translate-x-1/2 rounded-full ring-2 ring-surface ${style.dot} ${
          DOTS[outcomeWord(check.outcome)]
        } ${phase === 'sliding' ? 'transition-[left] duration-600 ease-out' : 'transition-none'}`}
        style={{ left: `${(phase === 'waiting' ? 0 : position) * 100}%` }}
      />
    </div>
  )
}
