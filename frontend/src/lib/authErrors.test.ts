import { describe, expect, it } from 'vitest'
import { describeAuthError } from './authErrors'

describe('describeAuthError', () => {
  it('rephrases invalid credentials into a plain-language message', () => {
    expect(describeAuthError({ message: 'Invalid login credentials' })).toBe(
      'Incorrect email or password.',
    )
  })

  it('rephrases a duplicate registration into a plain-language message', () => {
    expect(describeAuthError({ message: 'User already registered' })).toBe(
      'An account with this email already exists.',
    )
  })

  it('falls back to the raw message for anything else Supabase returns', () => {
    expect(describeAuthError({ message: 'Password should be at least 6 characters' })).toBe(
      'Password should be at least 6 characters',
    )
  })

  it('falls back to a generic message when Supabase gives no message', () => {
    expect(describeAuthError({ message: '' })).toBe('Something went wrong. Please try again.')
  })
})
