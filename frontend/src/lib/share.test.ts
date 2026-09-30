import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildShareUrl } from './share'

describe('buildShareUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('combines the page origin with the viewer path', () => {
    expect(buildShareUrl('token-123', { origin: 'http://192.168.1.42:5173' })).toBe(
      'http://192.168.1.42:5173/view/token-123',
    )
  })

  it('falls back to an empty origin when none is available', () => {
    expect(buildShareUrl('token-123', undefined)).toBe('/view/token-123')
  })

  it('VITE_SHARE_BASE_URL overrides the page origin when set', () => {
    vi.stubEnv('VITE_SHARE_BASE_URL', 'http://192.168.1.42:5173')
    expect(buildShareUrl('token-123', { origin: 'http://localhost:5173' })).toBe(
      'http://192.168.1.42:5173/view/token-123',
    )
  })
})
