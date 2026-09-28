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

export type AudioAckMessage = {
  type: 'audio_chunk_received'
  bytes: number
}

export type ServerMessage = EchoMessage | ErrorMessage | AudioAckMessage
