import { describe, expect, it } from 'vitest'
import { validateRegistration } from './authForm'

describe('validateRegistration', () => {
  it('passes when both passwords match', () => {
    expect(validateRegistration({ password: 'secret123', confirmPassword: 'secret123' })).toEqual({ ok: true })
  })

  it('flags the confirmation field when they differ', () => {
    expect(validateRegistration({ password: 'secret123', confirmPassword: 'secret124' })).toEqual({
      ok: false,
      field: 'confirmPassword',
      error: "Passwords don't match.",
    })
  })

  it('asks for the confirmation when it was left empty', () => {
    expect(validateRegistration({ password: 'secret123', confirmPassword: '' })).toEqual({
      ok: false,
      field: 'confirmPassword',
      error: 'Type your password again to confirm it.',
    })
  })

  it('checks the length before the match', () => {
    expect(validateRegistration({ password: 'abc', confirmPassword: 'abc' })).toEqual({
      ok: false,
      field: 'password',
      error: 'Use at least 6 characters.',
    })
  })
})
