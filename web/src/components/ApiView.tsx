import type { ReactNode } from 'react'
import type { ApiState } from '../useApi'

/** Show loading or the error for an API call, or hand the data to children once it's in. */
export function ApiView<T>({
  state,
  children,
}: {
  state: ApiState<T>
  children: (data: T) => ReactNode
}) {
  if (state.state === 'loading') return <p role="status">Loading</p>
  if (state.state === 'error') {
    return (
      <div role="alert" className="rounded-md border border-line bg-failbg px-4 py-3">
        <p className="font-bold text-ink">{state.error.message}.</p>
        <p className="text-ink">{state.error.hint}</p>
      </div>
    )
  }
  return children(state.data)
}
