import { describe, expect, it } from 'vitest'
import {
  appendSessions,
  formatSessionTitle,
  initialViewLanguage,
  removeSessionFromList,
  renameSessionInList,
} from './sessions'
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
    role: 'owner',
    share_token: 'share-token-1',
    guest_language: null,
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

describe('renameSessionInList', () => {
  it('updates only the matching row\'s title', () => {
    const sessions = [makeSession({ id: 'a', title: 'Old' }), makeSession({ id: 'b', title: 'Other' })]
    const result = renameSessionInList(sessions, 'a', 'New')
    expect(result.find((s) => s.id === 'a')?.title).toBe('New')
    expect(result.find((s) => s.id === 'b')?.title).toBe('Other')
  })

  it('leaves the list unchanged when the id is not found', () => {
    const sessions = [makeSession({ id: 'a', title: 'Old' })]
    expect(renameSessionInList(sessions, 'missing', 'New')).toEqual(sessions)
  })

  it('does not mutate the existing array', () => {
    const sessions = [makeSession({ id: 'a', title: 'Old' })]
    renameSessionInList(sessions, 'a', 'New')
    expect(sessions[0].title).toBe('Old')
  })
})

describe('removeSessionFromList', () => {
  it('removes the matching row', () => {
    const sessions = [makeSession({ id: 'a' }), makeSession({ id: 'b' })]
    expect(removeSessionFromList(sessions, 'a').map((s) => s.id)).toEqual(['b'])
  })

  it('leaves the list unchanged when the id is not found', () => {
    const sessions = [makeSession({ id: 'a' })]
    expect(removeSessionFromList(sessions, 'missing')).toEqual(sessions)
  })

  it('does not mutate the existing array', () => {
    const sessions = [makeSession({ id: 'a' })]
    removeSessionFromList(sessions, 'a')
    expect(sessions).toHaveLength(1)
  })
})

describe('initialViewLanguage', () => {
  it("opens a guest's session in the language they picked, translating if it differs", () => {
    const session = makeSession({ role: 'guest', guest_language: 'fr', target_language: 'es' })
    expect(initialViewLanguage(session)).toEqual({ language: 'fr', needsTranslation: true })
  })

  it("needs no translation when the guest's language matches the stored one", () => {
    const session = makeSession({ role: 'guest', guest_language: 'es', target_language: 'es' })
    expect(initialViewLanguage(session)).toEqual({ language: 'es', needsTranslation: false })
  })

  it('opens a guest session without a picked language in the stored one', () => {
    const session = makeSession({ role: 'guest', guest_language: null, target_language: 'de' })
    expect(initialViewLanguage(session)).toEqual({ language: 'de', needsTranslation: false })
  })

  it("opens an owner's session in its stored language, never translating on landing", () => {
    const session = makeSession({ role: 'owner', guest_language: 'fr', target_language: 'es' })
    expect(initialViewLanguage(session)).toEqual({ language: 'es', needsTranslation: false })
  })

  it('falls back to the default language when nothing was ever stored', () => {
    const session = makeSession({ role: 'owner', target_language: null })
    expect(initialViewLanguage(session)).toEqual({ language: 'es', needsTranslation: false })
  })
})
