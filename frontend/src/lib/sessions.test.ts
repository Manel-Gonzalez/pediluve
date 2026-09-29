import { describe, expect, it } from 'vitest'
import { appendSessions, formatSessionTitle } from './sessions'
import type { SessionSummary } from './types'

function makeSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: 'session-1',
    created_at: '2026-01-15T10:00:00Z',
    ended_at: null,
    source_language: null,
    target_language: null,
    title: null,
    message_count: 0,
    ...overrides,
  }
}

describe('formatSessionTitle', () => {
  it('returns the title when present', () => {
    expect(formatSessionTitle(makeSession({ title: 'Standup' }))).toBe('Standup')
  })

  it('falls back to "Untitled - <date>" when there is no title', () => {
    const session = makeSession({ title: null, created_at: '2026-01-15T10:00:00Z' })
    const formatted = formatSessionTitle(session)
    expect(formatted.startsWith('Untitled - ')).toBe(true)
  })
})

describe('appendSessions', () => {
  it('appends the loaded page after the existing rows', () => {
    const existing = [makeSession({ id: 'a' })]
    const loaded = [makeSession({ id: 'b' }), makeSession({ id: 'c' })]
    expect(appendSessions(existing, loaded).map((s) => s.id)).toEqual(['a', 'b', 'c'])
  })

  it('does not mutate the existing array', () => {
    const existing = [makeSession({ id: 'a' })]
    appendSessions(existing, [makeSession({ id: 'b' })])
    expect(existing.map((s) => s.id)).toEqual(['a'])
  })

  it('returns the loaded page unchanged when there are no existing rows', () => {
    const loaded = [makeSession({ id: 'a' })]
    expect(appendSessions([], loaded).map((s) => s.id)).toEqual(['a'])
  })
})
