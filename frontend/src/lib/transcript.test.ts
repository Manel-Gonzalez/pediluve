import { describe, expect, it } from 'vitest'
import { describeTranslation, isTranslationPending } from './transcript'
import type { TranscriptMessage } from './types'

function row(overrides: Partial<TranscriptMessage> = {}): TranscriptMessage {
  return {
    type: 'transcript',
    original_text: 'hello',
    translated_text: null,
    target_language: null,
    ...overrides,
  }
}

describe('describeTranslation', () => {
  it('prompts to select a target language when none was ever chosen', () => {
    expect(describeTranslation(row({ target_language: null, translated_text: null }))).toBe(
      'Select a target language',
    )
  })

  it('shows the translated text when translation succeeded', () => {
    expect(describeTranslation(row({ target_language: 'es', translated_text: 'hola' }))).toBe('hola')
  })

  it('flags translation as unavailable when a target language was set but translation failed', () => {
    expect(describeTranslation(row({ target_language: 'es', translated_text: null }))).toBe(
      'Translation unavailable',
    )
  })
})

describe('isTranslationPending', () => {
  it('is true whenever translated_text is null, whatever target_language is', () => {
    expect(isTranslationPending(row({ target_language: null, translated_text: null }))).toBe(true)
    expect(isTranslationPending(row({ target_language: 'es', translated_text: null }))).toBe(true)
  })

  it('is false once translated_text is present', () => {
    expect(isTranslationPending(row({ target_language: 'es', translated_text: 'hola' }))).toBe(false)
  })
})
