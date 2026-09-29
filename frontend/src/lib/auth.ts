import type { AuthenticateMessage, JoinSessionMessage } from './types'

export function buildAuthenticateMessage(accessToken: string): AuthenticateMessage {
  return { type: 'authenticate', access_token: accessToken }
}

export function buildJoinSessionMessage(sessionId: string): JoinSessionMessage {
  return { type: 'join_session', session_id: sessionId }
}

export type ConnectionStatus = 'connecting' | 'open' | 'closed'

// Combines the raw socket connection status with the separate
// authenticate-handshake result into the single line useWebSocket's caller
// displays: connecting -> open -> authenticated (or closed, whatever
// isAuthenticated was at the time - a closed socket is never "authenticated").
export function describeConnectionStatus(
  status: ConnectionStatus,
  isAuthenticated: boolean,
): string {
  if (status === 'open' && isAuthenticated) return 'authenticated'
  return status
}
