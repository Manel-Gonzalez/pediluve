export type ClientMessage = {
  type: 'message'
  text: string
}

export type EchoMessage = {
  type: 'echo'
  text: string
}

export type ErrorMessage = {
  type: 'error'
  message: string
}

export type PartialTranscriptMessage = {
  type: 'partial_transcript'
  text: string
}

// TranscriptMessage still uses Phase 1's `text` field - the backend's rename to
// original_text/translated_text/target_language (KAN-5) is picked up here by
// KAN-8, which also updates how this message is rendered.
export type TranscriptMessage = {
  type: 'transcript'
  text: string
}

export type StartTranscriptionMessage = {
  type: 'start_transcription'
  audio_format: string
  source_language?: string
}

export type SetTargetLanguageMessage = {
  type: 'set_target_language'
  target_language: string
}

export type LogMessage = EchoMessage | ErrorMessage

export type ServerMessage = LogMessage | PartialTranscriptMessage | TranscriptMessage
