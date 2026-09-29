import { describe, expect, it } from 'vitest'
import { postLoginRedirect } from './routes'

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
