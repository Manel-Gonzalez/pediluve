import { describe, expect, it } from 'vitest'
import { parseStoredTheme, resolveTheme, toggleTheme } from './theme'

describe('parseStoredTheme', () => {
  it('accepts an explicit light or dark choice', () => {
    expect(parseStoredTheme('light')).toBe('light')
    expect(parseStoredTheme('dark')).toBe('dark')
  })

  it('treats a missing or unexpected value as no choice', () => {
    expect(parseStoredTheme(null)).toBeNull()
    expect(parseStoredTheme('')).toBeNull()
    expect(parseStoredTheme('purple')).toBeNull()
  })
})

describe('resolveTheme', () => {
  it('an explicit choice wins over the system preference', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })

  it('follows the system preference when nothing was chosen', () => {
    expect(resolveTheme(null, true)).toBe('dark')
    expect(resolveTheme(null, false)).toBe('light')
  })
})

describe('toggleTheme', () => {
  it('returns the opposite of the theme currently shown', () => {
    expect(toggleTheme('light')).toBe('dark')
    expect(toggleTheme('dark')).toBe('light')
  })
})
