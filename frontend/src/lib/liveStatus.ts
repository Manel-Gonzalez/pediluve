import type { RecordingStatus } from '../hooks/useMicrophone'
import type { ConnectionStatus } from './auth'

export type OwnerStatus = 'connecting' | 'ready' | 'recording' | 'paused' | 'disconnected' | 'mic_error'

// The one status pill on the owner's live page (KAN-81), replacing the raw
// "WebSocket status" / "Microphone status" debug lines. A closed socket
// wins over everything: nothing said now would reach the backend.
export function ownerStatus({
  status,
  isAuthenticated,
  joinStatus,
  micStatus,
  hasRecorded,
}: {
  status: ConnectionStatus
  isAuthenticated: boolean
  joinStatus: 'joining' | 'joined' | 'not_found'
  micStatus: RecordingStatus
  hasRecorded: boolean
}): OwnerStatus {
  if (status === 'closed') return 'disconnected'
  if (micStatus === 'recording') return 'recording'
  if (micStatus === 'error') return 'mic_error'
  if (status !== 'open' || !isAuthenticated || joinStatus !== 'joined') return 'connecting'
  return hasRecorded ? 'paused' : 'ready'
}
