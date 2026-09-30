// Light/dark theme (KAN-74). The page follows the OS setting until the
// user picks one with the toggle; that choice is remembered per browser.
// index.html runs the same logic inline before first paint (no flash of
// the wrong theme), so keep THEME_STORAGE_KEY in sync with it.
export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'pediluve-theme'

export function parseStoredTheme(value: string | null): Theme | null {
  return value === 'light' || value === 'dark' ? value : null
}

export function resolveTheme(stored: Theme | null, systemPrefersDark: boolean): Theme {
  return stored ?? (systemPrefersDark ? 'dark' : 'light')
}

export function toggleTheme(current: Theme): Theme {
  return current === 'dark' ? 'light' : 'dark'
}
