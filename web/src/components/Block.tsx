// the big sentence at the top of the stock and screener pages
export const HEADLINE =
  'text-4xl leading-[1.05] font-extrabold tracking-tight break-words sm:text-[60px]'

/** A quiet placeholder in the track colour, shown where something is still loading. */
export function Block({ className }: { className: string }) {
  return <div className={`rounded-md bg-track ${className}`} />
}
