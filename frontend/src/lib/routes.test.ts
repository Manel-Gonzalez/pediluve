import { describe, expect, it } from 'vitest'
import { liveSessionPath, liveViewPath, postLoginRedirect, sessionPath } from './routes'

describe('postLoginRedirect', () => {
  it('returns / when there is no state', () => {
    expect(postLoginRedirect(undefined)).toBe('/')
  })

  it('returns / when state has no from', () => {
    expect(postLoginRedirect({})).toBe('/')
  })

  it('returns the stored from path when present', () => {
    expect(postLoginRedirect({ from: { pathname: '/some-session' } })).toBe('/some-session')
  })

  it('never redirects back to /login, even if that was the stored from', () => {
    expect(postLoginRedirect({ from: { pathname: '/login' } })).toBe('/')
  })
})

describe('sessionPath', () => {
  it('builds the read-only session detail path', () => {
    expect(sessionPath('abc-123')).toBe('/sessions/abc-123')
  })
})

describe('liveSessionPath', () => {
  it('builds a distinct path from sessionPath', () => {
    expect(liveSessionPath('abc-123')).toBe('/sessions/abc-123/live')
    expect(liveSessionPath('abc-123')).not.toBe(sessionPath('abc-123'))
  })
})

describe('liveViewPath', () => {
  it('builds the anonymous QR/share-link path', () => {
    expect(liveViewPath('token-123')).toBe('/view/token-123')
  })
})
