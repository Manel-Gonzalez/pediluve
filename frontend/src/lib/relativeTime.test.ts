import { describe, expect, it } from 'vitest'
import { relativeTime } from './relativeTime'

const now = new Date('2026-09-30T12:00:00Z')
const ago = (ms: number) => new Date(now.getTime() - ms).toISOString()

describe('relativeTime', () => {
  it('says "just now" under a minute', () => {
    expect(relativeTime(ago(30_000), now)).toBe('just now')
  })

  it('counts minutes, hours and days', () => {
    expect(relativeTime(ago(5 * 60_000), now)).toBe('5 minutes ago')
    expect(relativeTime(ago(3 * 3600_000), now)).toBe('3 hours ago')
    expect(relativeTime(ago(26 * 3600_000), now)).toBe('yesterday')
    expect(relativeTime(ago(4 * 86400_000), now)).toBe('4 days ago')
  })

  it('falls back to a date after a week', () => {
    expect(relativeTime('2026-08-01T10:00:00Z', now)).toBe(new Date('2026-08-01T10:00:00Z').toLocaleDateString())
  })
})
