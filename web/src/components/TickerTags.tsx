import { type KeyboardEvent, useState } from 'react'
import { MAX_TICKERS, addTickers } from '../lib/screener'

/** A box that turns typed tickers into tags, each with its own remove button. */
export function TickerTags({
  tickers,
  onChange,
}: {
  tickers: string[]
  onChange: (tickers: string[]) => void
}) {
  const [text, setText] = useState('')
  const [full, setFull] = useState(false)

  const add = (value: string) => {
    const { tickers: next, refused } = addTickers(tickers, value)
    setFull(refused > 0)
    if (next.length !== tickers.length) onChange(next)
  }

  const onType = (value: string) => {
    // a comma or space finishes a ticker, which also covers pasting a whole list
    const parts = value.split(/[,\s]/)
    const last = parts.pop() ?? ''
    if (parts.length > 0) add(parts.join(' '))
    setText(last)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && text.trim() !== '') {
      // with text in the box, Enter adds it. An empty box lets Enter submit the form
      event.preventDefault()
      add(text)
      setText('')
    } else if (event.key === 'Backspace' && text === '' && tickers.length > 0) {
      setFull(false)
      onChange(tickers.slice(0, -1))
    }
  }

  const remove = (ticker: string) => {
    setFull(false)
    onChange(tickers.filter((t) => t !== ticker))
  }

  return (
    <div className="min-w-0 flex-1">
      <label htmlFor="screener-tickers" className="sr-only">
        Tickers to screen
      </label>
      <div className="flex min-h-11 flex-wrap items-center gap-2 rounded-md border border-line3 bg-paper p-1 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-lapis">
        <ul className="contents">
          {tickers.map((ticker) => (
            <li
              key={ticker}
              className="flex min-h-11 items-center rounded-md bg-track pl-3 font-bold text-ink"
            >
              {ticker}
              <button
                type="button"
                aria-label={`Remove ${ticker}`}
                onClick={() => remove(ticker)}
                className="flex size-11 items-center justify-center rounded-md text-muted hover:text-ink"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 16 16"
                  className="size-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                >
                  <path d="m4 4 8 8M12 4l-8 8" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
        <input
          id="screener-tickers"
          value={text}
          onChange={(event) => onType(event.target.value)}
          onKeyDown={onKeyDown}
          // a tag left half-typed still counts when the box loses focus
          onBlur={() => {
            if (text.trim() !== '') {
              add(text)
              setText('')
            }
          }}
          placeholder={tickers.length === 0 ? 'Type a ticker, e.g. AAPL' : 'Add a ticker'}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          enterKeyHint="done"
          className="min-h-11 min-w-32 flex-1 bg-transparent px-2 text-ink placeholder:text-muted focus:outline-none"
        />
      </div>
      <p aria-live="polite" className="mt-1 text-sm text-warntext empty:hidden">
        {full ? `That's the most at once. Remove one to add another (${MAX_TICKERS} max).` : ''}
      </p>
    </div>
  )
}
