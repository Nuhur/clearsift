import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

// the inline script in index.html reads the same key, keep them in step
const STORAGE_KEY = 'clearsift-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

/** Read the theme the user picked, or null if they never flipped the switch. */
export function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    // storage can be blocked, e.g. in a private window
    return null
  }
}

/** Remember the user's pick for next time. */
export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // not being able to remember it is fine, the switch still works for this visit
  }
}

/** Get the theme the page is showing right now. */
export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

/** Show the given theme. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

/** Track the theme, following the system until the user flips the switch. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(currentTheme)

  useEffect(() => {
    // once they've picked, the system setting no longer gets a say
    if (savedTheme() !== null) return
    const query = window.matchMedia(DARK_QUERY)
    const follow = (event: MediaQueryListEvent) => {
      if (savedTheme() !== null) return
      const next = event.matches ? 'dark' : 'light'
      applyTheme(next)
      setThemeState(next)
    }
    query.addEventListener('change', follow)
    return () => query.removeEventListener('change', follow)
  }, [])

  const setTheme = (next: Theme) => {
    applyTheme(next)
    saveTheme(next)
    setThemeState(next)
  }
  return [theme, setTheme]
}
