import { describe, expect, it } from 'vitest'
import { buildShareUrl } from './share'

describe('buildShareUrl', () => {
  it('combines the page origin with the viewer path', () => {
    expect(buildShareUrl('token-123', { origin: 'http://192.168.1.42:5173' })).toBe(
      'http://192.168.1.42:5173/view/token-123',
    )
  })

  it('falls back to an empty origin when none is available', () => {
    expect(buildShareUrl('token-123', undefined)).toBe('/view/token-123')
  })
})
