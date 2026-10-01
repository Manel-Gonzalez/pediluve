import { describe, expect, it } from 'vitest'
import { buildAuthenticateMessage, buildJoinSessionMessage } from './auth'

describe('buildAuthenticateMessage', () => {
  it('builds the authenticate message shape', () => {
    expect(buildAuthenticateMessage('token-123')).toEqual({
      type: 'authenticate',
      access_token: 'token-123',
    })
  })
})

describe('buildJoinSessionMessage', () => {
  it('builds the join_session message shape', () => {
    expect(buildJoinSessionMessage('session-123')).toEqual({
      type: 'join_session',
      session_id: 'session-123',
    })
  })
})
