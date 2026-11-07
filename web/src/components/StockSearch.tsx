import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

/** The "Look up a stock" box in the header. Enter goes to that stock's page. */
export function StockSearch() {
  const [text, setText] = useState('')
  const navigate = useNavigate()

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const ticker = text.trim().toUpperCase()
    if (!ticker) return
    navigate(`/stock/${encodeURIComponent(ticker)}`)
    setText('')
  }

  return (
    <form role="search" onSubmit={submit} className="min-w-0 flex-1 sm:flex-none">
      <label htmlFor="stock-search" className="sr-only">
        Look up a stock
      </label>
      <input
        id="stock-search"
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Look up a stock"
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        enterKeyHint="search"
        className="min-h-11 w-full rounded-md border border-line3 bg-paper px-3 text-ink placeholder:text-muted sm:w-56"
      />
    </form>
  )
}
