import { type KeyboardEvent, useRef } from 'react'
import { STANDARDS, type StandardName } from '../lib/standards'

/** A segmented switch for picking the standard, working like a set of radio buttons. */
export function StandardSwitch({
  value,
  onChange,
}: {
  value: StandardName | null
  onChange: (standard: StandardName) => void
}) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  // arrow keys move between the options, the way radio buttons do
  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (step === undefined) return
    event.preventDefault()
    const next = (index + step + STANDARDS.length) % STANDARDS.length
    buttons.current[next]?.focus()
    onChange(STANDARDS[next])
  }

  return (
    <div
      role="radiogroup"
      aria-label="Standard"
      className="inline-flex shrink-0 rounded-lg border border-line bg-surface p-1"
    >
      {STANDARDS.map((standard, index) => {
        const checked = standard === value
        return (
          <button
            key={standard}
            ref={(element) => {
              buttons.current[index] = element
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            // only the picked one is a tab stop, or the first if none is picked yet
            tabIndex={checked || (value === null && index === 0) ? 0 : -1}
            onClick={() => onChange(standard)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`min-h-11 rounded-md px-4 text-sm font-bold ${
              checked ? 'bg-ink text-paper' : 'text-body hover:text-ink'
            }`}
          >
            {standard.toUpperCase()}
          </button>
        )
      })}
    </div>
  )
}
