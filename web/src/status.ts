import type { ComparisonOut, ScreenResult, VerdictOut } from './api'

export type StatusWord = 'Passes' | 'Check by hand' | 'Fails' | "Couldn't be read"

/** Put a screening result into words, so status never relies on colour alone. */
export function statusWord(result: ScreenResult | VerdictOut | ComparisonOut | null): StatusWord {
  // no verdict at all means the ticker couldn't be converted or screened
  if (result === null || result.kind === 'error') return "Couldn't be read"
  // in strict mode a doubtful stock doesn't pass, so go on passes, not status alone
  if (!result.passes) return 'Fails'
  return result.status === 'doubtful' ? 'Check by hand' : 'Passes'
}
