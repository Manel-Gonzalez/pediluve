import { describe, expect, it } from 'vitest'
import { validateSessionTitle } from './sessionTitle'

describe('validateSessionTitle', () => {
  it('rejects an empty title', () => {
    expect(validateSessionTitle('')).toEqual({ ok: false, error: expect.any(String) })
  })

  it('rejects a whitespace-only title', () => {
    expect(validateSessionTitle('   ')).toEqual({ ok: false, error: expect.any(String) })
  })

  it('rejects a title over 120 characters', () => {
    expect(validateSessionTitle('x'.repeat(121))).toEqual({ ok: false, error: expect.any(String) })
  })

  it('accepts a title at exactly 120 characters', () => {
    const title = 'x'.repeat(120)
    expect(validateSessionTitle(title)).toEqual({ ok: true, title })
  })

  it('accepts and trims surrounding whitespace', () => {
    expect(validateSessionTitle(' Standup ')).toEqual({ ok: true, title: 'Standup' })
  })
})
