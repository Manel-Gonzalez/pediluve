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

export type ServerMessage = EchoMessage | ErrorMessage
