import { useEffect, useState } from 'react'

// waiting: dots drawn at 0. sliding: moving to their place. still: in place, no transition
export type SlidePhase = 'waiting' | 'sliding' | 'still'

// a little longer than the 600ms slide, so it's finished before the transition comes off
const SLIDE_MS = 650

function lessMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Slide the dots in once each time the key changes, and keep them still otherwise. */
export function useSlideIn(key: unknown): SlidePhase {
  // with less motion asked for, the dots just start where they belong
  const [phase, setPhase] = useState<SlidePhase>(() => (lessMotion() ? 'still' : 'waiting'))
  const [seen, setSeen] = useState(key)
  // a new result came in, so start the slide again. Done during render so it never flashes
  if (seen !== key) {
    setSeen(key)
    setPhase(lessMotion() ? 'still' : 'waiting')
  }

  useEffect(() => {
    if (phase === 'waiting') {
      // two frames, so the browser has drawn the dots at 0 before they move
      let frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => setPhase('sliding'))
      })
      return () => cancelAnimationFrame(frame)
    }
    if (phase === 'sliding') {
      // take the transition off afterwards, so switching standards just moves them
      const timer = setTimeout(() => setPhase('still'), SLIDE_MS)
      return () => clearTimeout(timer)
    }
  }, [phase])

  return phase
}
