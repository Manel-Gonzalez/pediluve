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

export type TranscriptMessage = {
  type: 'transcript'
  original_text: string
  translated_text: string | null
  target_language: string | null
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
