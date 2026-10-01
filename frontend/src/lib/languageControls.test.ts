import { describe, expect, it } from 'vitest'
import {
  buildSetTargetLanguageMessage,
  buildStartTranscriptionMessage,
  canChangeSourceLanguage,
  DEFAULT_TARGET_LANGUAGE,
  SUPPORTED_LANGUAGES,
} from './languageControls'

describe('SUPPORTED_LANGUAGES', () => {
  it('matches the DeepL-supported candidate set from CLAUDE.md', () => {
    expect(SUPPORTED_LANGUAGES).toEqual(['es', 'ca', 'en', 'fr', 'de', 'ro', 'nl'])
  })
})

describe('DEFAULT_TARGET_LANGUAGE', () => {
  it('is a supported language, so the initial selection is always valid', () => {
    expect(SUPPORTED_LANGUAGES).toContain(DEFAULT_TARGET_LANGUAGE)
  })

  it('is es', () => {
    expect(DEFAULT_TARGET_LANGUAGE).toBe('es')
  })
})

describe('buildStartTranscriptionMessage', () => {
  it('omits source_language when none was chosen (auto-detect)', () => {
    const message = buildStartTranscriptionMessage('pcm_16000', null)
    expect(message).toEqual({ type: 'start_transcription', audio_format: 'pcm_16000' })
    expect('source_language' in message).toBe(false)
  })

  it('includes source_language when one was chosen', () => {
    const message = buildStartTranscriptionMessage('pcm_16000', 'es')
    expect(message).toEqual({
      type: 'start_transcription',
      audio_format: 'pcm_16000',
      source_language: 'es',
    })
  })
})

describe('buildSetTargetLanguageMessage', () => {
  it('builds the set_target_language message shape', () => {
    expect(buildSetTargetLanguageMessage('fr')).toEqual({
      type: 'set_target_language',
      target_language: 'fr',
    })
  })
})

describe('canChangeSourceLanguage', () => {
  it('is true while idle', () => {
    expect(canChangeSourceLanguage('idle')).toBe(true)
  })

  it('is true after an error', () => {
    expect(canChangeSourceLanguage('error')).toBe(true)
  })

  it('is false while recording', () => {
    expect(canChangeSourceLanguage('recording')).toBe(false)
  })
})
