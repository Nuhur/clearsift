import type { StatusWord } from '../status'

const STYLES: Record<StatusWord, string> = {
  Passes: 'bg-passbg text-pass',
  'Check by hand': 'bg-warnbg text-warntext',
  Fails: 'bg-failbg text-fail',
  "Couldn't be read": 'bg-track text-body',
}

/** A status in words, with colour only as an extra. */
export function StatusBadge({ word }: { word: StatusWord }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-sm font-bold ${STYLES[word]}`}>
      {word}
    </span>
  )
}
