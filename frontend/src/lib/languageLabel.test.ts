import { describe, expect, it } from 'vitest'
import { languageName } from './languageLabel'

describe('languageName', () => {
  it('gives the English name of a supported language code', () => {
    expect(languageName('es')).toBe('Spanish')
    expect(languageName('ca')).toBe('Catalan')
    expect(languageName('en')).toBe('English')
    expect(languageName('fr')).toBe('French')
    expect(languageName('de')).toBe('German')
  })

  it('falls back to the code itself when it isn\'t a language', () => {
    expect(languageName('zz-not-a-language')).toBe('zz-not-a-language')
    expect(languageName('')).toBe('')
  })
})
