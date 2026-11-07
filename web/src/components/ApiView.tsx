import type { ReactNode } from 'react'
import type { ApiError } from '../api'
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
  if (state.state === 'error') return <ApiErrorBox error={state.error} />
  return children(state.data)
}

/** What went wrong with an API call and what to do next, with room for an extra link. */
export function ApiErrorBox({ error, children }: { error: ApiError; children?: ReactNode }) {
  return (
    <div role="alert" className="rounded-md border border-line bg-failbg px-4 py-3">
      <p className="font-bold text-ink">{error.message}.</p>
      <p className="text-ink">{error.hint}</p>
      {children}
    </div>
  )
}
