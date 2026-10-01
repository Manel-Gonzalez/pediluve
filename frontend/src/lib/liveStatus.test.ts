import { describe, expect, it } from 'vitest'
import { ownerStatus } from './liveStatus'

const ready = {
  status: 'open' as const,
  isAuthenticated: true,
  joinStatus: 'joined' as const,
  micStatus: 'idle' as const,
  hasRecorded: false,
}

describe('ownerStatus', () => {
  it('is "ready" once connected and joined, before the first recording', () => {
    expect(ownerStatus(ready)).toBe('ready')
  })

  it('is "recording" while the mic is capturing', () => {
    expect(ownerStatus({ ...ready, micStatus: 'recording', hasRecorded: true })).toBe('recording')
  })

  it('is "paused" when idle after having recorded', () => {
    expect(ownerStatus({ ...ready, hasRecorded: true })).toBe('paused')
  })

  it('is "connecting" until authenticated and joined', () => {
    expect(ownerStatus({ ...ready, status: 'connecting' })).toBe('connecting')
    expect(ownerStatus({ ...ready, isAuthenticated: false })).toBe('connecting')
    expect(ownerStatus({ ...ready, joinStatus: 'joining' })).toBe('connecting')
  })

  it('is "disconnected" once the socket closed, whatever else is true', () => {
    expect(ownerStatus({ ...ready, status: 'closed', micStatus: 'recording' })).toBe('disconnected')
  })

  it('reports a microphone failure', () => {
    expect(ownerStatus({ ...ready, micStatus: 'error' })).toBe('mic_error')
  })
})
