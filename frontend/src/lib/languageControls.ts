import type { RecordingStatus } from '../hooks/useMicrophone'
import type { SetTargetLanguageMessage, StartTranscriptionMessage } from './types'

// DeepL-supported candidate set (see CLAUDE.md), matching the backend's
// deepl.SUPPORTED_TARGET_LANGUAGES.
export const SUPPORTED_LANGUAGES = ['es', 'ca', 'en', 'fr', 'de'] as const

export function buildStartTranscriptionMessage(
  audioFormat: string,
  sourceLanguage: string | null,
): StartTranscriptionMessage {
  return {
    type: 'start_transcription',
    audio_format: audioFormat,
    ...(sourceLanguage ? { source_language: sourceLanguage } : {}),
  }
}

export function buildSetTargetLanguageMessage(targetLanguage: string): SetTargetLanguageMessage {
  return { type: 'set_target_language', target_language: targetLanguage }
}

// The source language is fixed for the duration of an active recording -
// changing it requires stopping first (see docs/decisions.md and KAN-4's
// message contract). The target language has no such restriction.
export function canChangeSourceLanguage(micStatus: RecordingStatus): boolean {
  return micStatus !== 'recording'
}
