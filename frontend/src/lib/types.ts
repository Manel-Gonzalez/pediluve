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
  text: string
}

export type LogMessage = EchoMessage | ErrorMessage

export type ServerMessage = LogMessage | PartialTranscriptMessage | TranscriptMessage
