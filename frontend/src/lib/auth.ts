import type { AuthenticateMessage, JoinSessionMessage } from './types'

export function buildAuthenticateMessage(accessToken: string): AuthenticateMessage {
  return { type: 'authenticate', access_token: accessToken }
}

export function buildJoinSessionMessage(sessionId: string): JoinSessionMessage {
  return { type: 'join_session', session_id: sessionId }
}

export type ConnectionStatus = 'connecting' | 'open' | 'closed'
