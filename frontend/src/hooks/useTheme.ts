import { useCallback, useEffect, useState } from 'react'
import { THEME_STORAGE_KEY, parseStoredTheme, resolveTheme, toggleTheme, type Theme } from '../lib/theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

function readStored(): Theme | null {
  // localStorage can throw (blocked storage, some private modes): treat
  // that the same as "no choice made".
  try {
    return parseStoredTheme(localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    return null
  }
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

// The theme currently on <html> (index.html already applied it before
// first paint) plus a toggle that remembers the choice. Until the user
// toggles, it keeps following the OS setting live.
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  )

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY)
    const onChange = () => {
      const next = resolveTheme(readStored(), media.matches)
      apply(next)
      setTheme(next)
    }
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = toggleTheme(current)
      apply(next)
      try {
        localStorage.setItem(THEME_STORAGE_KEY, next)
      } catch {
        // Not persisted - still switches for this page view.
      }
      return next
    })
  }, [])

  return { theme, toggle }
}
