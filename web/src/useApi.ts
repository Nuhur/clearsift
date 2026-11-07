import { useEffect, useState } from 'react'
import { ApiError, START_HINT } from './api'

export type ApiState<T> =
  | { state: 'loading' }
  | { state: 'error'; error: ApiError }
  | { state: 'done'; data: T }

type Settled<T> = { key: string; result: ApiState<T> }

/** Load data from the API, reloading whenever the key changes. */
export function useApi<T>(key: string, load: (signal: AbortSignal) => Promise<T>): ApiState<T> {
  const [settled, setSettled] = useState<Settled<T> | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({ key, result: { state: 'done', data } })
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        setSettled({ key, result: { state: 'error', error: asApiError(error) } })
      },
    )
    // a page left before its data arrives shouldn't update anything
    return () => controller.abort()
  }, [key, load])

  // an answer for an older key is out of date, so show loading until the new one lands
  if (settled === null || settled.key !== key) return { state: 'loading' }
  return settled.result
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  // anything else is a bug on this side, but it still needs a way forward
  return new ApiError("Couldn't load this page", `Reload the page. ${START_HINT} if it isn't running.`)
}
